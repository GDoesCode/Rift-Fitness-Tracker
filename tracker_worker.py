import time
import socket
import json
import threading
from riot_api import RiotAPIClient
from database import DatabaseManager

class LiveTrackerWorker:
    def __init__(self, puuid, riot_id, api_client: RiotAPIClient, db_manager: DatabaseManager):
        self.puuid = puuid
        self.riot_id = riot_id
        self.api = api_client
        self.db = db_manager
        self.stop_event = threading.Event()

    def send_data_to_overlay(self, data):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(('127.0.0.1', 5555))
                s.sendall(json.dumps(data).encode('utf-8'))
        except Exception:
            pass # Overlay window overlay.py isn't actively running

    def run_tracking_loop(self):
        self.db.init_db()
        print(f"\n[WORKER] 🚀 Adaptive background tracker active for {self.riot_id}.")
        
        game_active = None
        rank_before = None
        game_id = None
        last_kda = None

        self.send_data_to_overlay({"status": "SCANNING..."})

        while not self.stop_event.is_set():
            sleep_duration = 5 # default heartbeat fallback
            
            # Check the live game engine first
            live_data = self.api.get_live_client_data()

            # --- CASE A: Inside an active match ---
            if live_data:
                sleep_duration = 1 # Speed up polling when live in game
                
                if game_active in [None, False]:
                    game_active = True
                    rank_before = self.api.get_rank(self.puuid)
                    game_id = live_data.get("gameData", {}).get("gameId")
                    
                    game_time = live_data.get("gameData", {}).get("gameTime", 0)
                    if game_time == 0:
                        self.send_data_to_overlay({"status": "LOADING..."})
                    else:
                        self.send_data_to_overlay({"status": "LIVE"})
                    print(f"\n[WORKER] 🎮 Match Found! (ID: {game_id})")

                # Track live KDA stats
                your_data = None
                for player in live_data.get("allPlayers", []):
                    if player.get("riotId", "").lower() == self.riot_id.lower():
                        your_data = player
                        break

                if your_data:
                    scores = your_data.get("scores", {})
                    k, d, a = scores.get("kills", 0), scores.get("deaths", 0), scores.get("assists", 0)
                    game_time_sec = int(live_data.get("gameData", {}).get("gameTime", 0))
                    game_mins = max(1, (game_time_sec + 30) // 60)
                    cs_per_min = (scores.get("creepScore", 0) + (game_mins // 2)) // game_mins
                    
                    self.send_data_to_overlay({
                        "status": "LIVE",
                        "deaths": d,
                        "cs_min": cs_per_min
                    })

                    current_kda = (k, d, a)
                    if current_kda != last_kda:
                        print(f"\r[LIVE STATS] KDA: {k}/{d}/{a} | CS/M: {cs_per_min}", end="", flush=True)
                        self.db.store_live_snapshot(game_id, self.puuid, k, d, a)
                        last_kda = current_kda

            # --- CASE B: Not inside a match (Lobby, Post-Game, or Closed) ---
            else:
                # Fallback to check what the client window is doing
                lcu_phase = self.api.get_lcu_gameflow_phase()

                # The game just closed out, transition out of match execution state
                if game_active:
                    game_active = False # Flip immediately to prevent double execution
                    
                    print("\n[WORKER] 🏁 Game closed. Transitioning to processing...")
                    self.send_data_to_overlay({"status": "PROCESSING..."})
                    last_kda = None
                    
                    time.sleep(5) 
                    try:
                        m_ids = self.api.get_match_ids(self.puuid, count=1)
                        if m_ids:
                            self.process_finished_game(m_ids[0], rank_before)
                    except Exception as e:
                        print(f"[ERROR] Post-game routine failure: {e}")
                    
                    rank_before = None
                    game_id = None
                elif game_active is None:
                    game_active = False # Initial state set after first check

                # Evaluate LCU specific positions to send clean updates to your Tkinter file
                if lcu_phase in ["Lobby", "Matchmaking", "ChampSelect"]:
                    self.send_data_to_overlay({"status": "IN LOBBY"})
                    sleep_duration = 4  # moderate check rate during menus
                    
                elif lcu_phase in ["WaitingForStats", "EndOfGame"]:
                    self.send_data_to_overlay({"status": "POST GAME"})
                    sleep_duration = 5
                    
                elif lcu_phase == "CLOSED":
                    self.send_data_to_overlay({"status": "CLIENT CLOSED"})
                    sleep_duration = 12 # check very slowly if league is shut down
                    
                else:
                    self.send_data_to_overlay({"status": "SCANNING..."})
                    sleep_duration = 8

            self.stop_event.wait(timeout=sleep_duration)

    def process_finished_game(self, match_id, rank_before):
        match = self.api.get_match(match_id)
        info = match["info"]
        rank_after = self.api.get_rank(self.puuid)

        with self.db.get_connection() as conn:
            self.db.store_match(conn, match_id, info.get("gameStartTimestamp"), info.get("gameMode"), info.get("gameDuration"), info.get("mapId"), info.get("queueId"))
            
            your_part = None
            for p in info["participants"]:
                p_puuid = p.get("puuid")
                self.db.upsert_summoner(conn, p_puuid, p.get("riotIdGameName"), p.get("profileIcon"))
                
                k, d, a = p.get("kills", 0), p.get("deaths", 0), p.get("assists", 0)
                kda = (k + a) / max(1, d)
                team = "RED" if p.get("teamId") == 200 else "BLUE"
                
                self.db.store_participant(
                    conn, match_id, p_puuid, p.get("championName"), k, d, a, kda, team,
                    p.get("individualPosition"), p.get("lane"), p.get("goldEarned"), p.get("totalDamageDealt"), p.get("totalMinionsKilled")
                )
                if p_puuid == self.puuid:
                    your_part = p

            if your_part:
                punishments = self.db.calculate_and_store_punishments(
                    conn, match_id, self.puuid, your_part, info.get("gameDuration"), your_part.get("win"), rank_before, rank_after
                )
                print(f"\n[WORKOUT WORKBOOK REQUIRED]:\n -> 🏃 Push-ups: {punishments['deaths_pushups']}\n -> 🏋️ Sit-ups: {punishments['cs_situps']}\n -> 🪵 Planks: {punishments['loss_planks']} min\n -> 👟 Penalty Runs: {punishments['demotion_runs']} km")
            conn.commit()