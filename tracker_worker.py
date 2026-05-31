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
        
        game_active = False
        rank_before = None
        game_id = None
        last_kda = None

        self.send_data_to_overlay("Searching for game...")

        while not self.stop_event.is_set():
            # Adaptive throttle: Default wait time when sitting on client home screen
            sleep_duration = 15 

            live_data = self.api.get_live_client_data()

            # State Switch: Entering a match
            if live_data and not game_active:
                game_active = True
                rank_before = self.api.get_rank(self.puuid)
                game_id = live_data.get("gameData", {}).get("gameId")
                self.send_data_to_overlay("Game Active!")
                print(f"\n[WORKER] 🎮 Match Found! (ID: {game_id})")
                sleep_duration = 1

            # State Execution: Actively updating within an ongoing game
            elif live_data and game_active:
                sleep_duration = 1 # Quick monitoring cadence while inside the game
                
                # Fetch target player statistics
                your_data = None
                for player in live_data.get("allPlayers", []):
                    if player.get("riotId", "").lower() == self.riot_id.lower():
                        your_data = player
                        break

                if your_data:
                    scores = your_data.get("scores", {})
                    k, d, a = scores.get("kills", 0), scores.get("deaths", 0), scores.get("assists", 0)
                    
                    # CS Calculations
                    game_time_sec = int(live_data.get("gameData", {}).get("gameTime", 0))
                    game_mins = max(1, (game_time_sec + 30) // 60)
                    cs_per_min = (scores.get("creepScore", 0) + (game_mins // 2)) // game_mins
                    
                    self.send_data_to_overlay([d, cs_per_min])

                    current_kda = (k, d, a)
                    if current_kda != last_kda:
                        print(f"\r[LIVE STATS] KDA: {k}/{d}/{a} | CS/M: {cs_per_min}", end="", flush=True)
                        self.db.store_live_snapshot(game_id, self.puuid, k, d, a)
                        last_kda = current_kda

            # State Switch: Exiting a finished match
            elif not live_data and game_active:
                print("\n[WORKER] 🏁 Game concluded. Compiling statistics...")
                self.send_data_to_overlay("Game Ended!")
                game_active = False
                last_kda = None
                
                # Processing endgame entries
                time.sleep(5) # Brief buffer giving Riot's system server room to compile logs
                try:
                    m_ids = self.api.get_match_ids(self.puuid, count=1)
                    if m_ids:
                        self.process_finished_game(m_ids[0], rank_before)
                except Exception as e:
                    print(f"[ERROR] Failed post-game storage run: {e}")
                
                rank_before = None
                game_id = None
                sleep_duration = 10

            # Safe OS thread release mechanism
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