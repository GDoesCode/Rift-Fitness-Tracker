import time
import socket
import json
import threading
from config import DEATH_PUSHUPS_MULTIPLIER, CS_SITUPS_MULTIPLIER, LOSS_PLANKS_MULTIPLIER, DEMOTION_RUNS_MULTIPLIER, Tier, Rank
from riot_api import RiotAPIClient
from database import RiftFitnessTrackerDatabase

class LiveTrackerWorker:
    def __init__(self, puuid, riot_id, api_client: RiotAPIClient, db: RiftFitnessTrackerDatabase):
        self.puuid = puuid
        self.riot_id = riot_id
        self.rank_before = None
        self.api = api_client
        self.db = db
        self.stop_event = threading.Event()

    def send_data_to_overlay(self, data):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(('127.0.0.1', 5555))
                s.sendall(json.dumps(data).encode('utf-8'))
        except Exception:
            pass # Overlay window overlay.py isn't actively running

    def historical_sync(self, puuid):
        print("\n[HISTORICAL] Synced requested. Pulling down past 20 games...")
        match_ids = self.api.get_match_ids(puuid, count=20)

        for m_id in match_ids:
            if self.db.match_exists(m_id):
                print(f"Skipping match {m_id} (Already recorded)")
                continue
                
            print(f"Processing old match record: {m_id}")
            match_info = self.api.get_match(m_id).get("info")
            timestamp = (match_info.get("gameStartTimestamp") // 1000) + match_info.get("gameDuration") + 120 # additional 2 mins for loading time
            rank_after = self.db.get_rank_at_time(puuid, timestamp)
            self.process_finished_game(m_id, rank_after)
        print("[HISTORICAL] Sync Complete.")

    def run_tracking_loop(self):
        print(f"\n[WORKER] 🚀 Adaptive background tracker active for {self.riot_id}.")
        
        game_active = None
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
                    self.rank_before = self.api.get_rank(self.puuid)
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
                        self.db.store_live_snapshot(self.db.create_live_snapshot(self.puuid, scores))
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
                            self.process_finished_game(m_ids[0])
                    except Exception as e:
                        print(f"[ERROR] Post-game routine failure: {e}")
                    
                    self.rank_before = None
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

    def process_finished_game(self, match_id, rank_after=None):
        match = self.api.get_match(match_id)
        info = match["info"]
        if rank_after is None or rank_after.get("error") == "sql: no rows in result set":
            rank_after = self.api.get_rank(self.puuid)
        your_part = None

        self.db.store_match(self.db.create_match_payload(match_id, info))

        your_part = self.process_participants(info)
        if your_part:
            punishments = self.calculate_punishments(match_id, self.puuid, your_part, info.get("gameDuration"), your_part.get("win"), self.rank_before, rank_after)
            print(f"\n[WORKOUT WORKBOOK REQUIRED]:\n -> 🏃 Push-ups: {punishments['death_pushups']}\n -> 🏋️ Sit-ups: {punishments['cs_situps']}\n -> 🪵 Planks: {punishments['loss_planks']} min\n -> 👟 Penalty Runs: {punishments['demotion_runs']} km")

    def calculate_punishments(self, match_id, puuid, participant_data, match_duration, was_win, rank_before, rank_after):
        deaths = participant_data.get("deaths", 0)
        minions = participant_data.get("totalMinionsKilled", 0) + participant_data.get("neutralMinionsKilled", 0)
        cs_per_min = int(minions // max(1, match_duration / 60))
        
        death_pushups = deaths * DEATH_PUSHUPS_MULTIPLIER
        cs_situps = max(0, (10 - cs_per_min)) * CS_SITUPS_MULTIPLIER
        loss_planks = LOSS_PLANKS_MULTIPLIER if not was_win else 0
        demotion_runs = 0
        
        if rank_before and rank_after:
            rb_entry = rank_before[1] if isinstance(rank_before, list) and len(rank_before) > 1 else None
            ra_entry = rank_after[1] if isinstance(rank_after, list) and len(rank_after) > 1 else None
            
            if rb_entry and ra_entry:
                rb_dict = {"Tier": rb_entry.get("tier", "UNKNOWN"), "Rank": rb_entry.get("rank", "")}
                ra_dict = {"Tier": ra_entry.get("tier", "UNKNOWN"), "Rank": ra_entry.get("rank", "")}
                result = (Rank[rb_dict["Rank"]].value + Tier[rb_dict["Tier"]].value) < (Rank[ra_dict["Rank"]].value + Tier[ra_dict["Tier"]].value)
                if result:
                    demotion_runs = 1 * DEMOTION_RUNS_MULTIPLIER
        punishments = self.db.create_punishment_payload(match_id, puuid, death_pushups, cs_situps, loss_planks, demotion_runs)
        self.db.store_punishment(punishments)

        return punishments
    
    def process_participants(self, info):
        for p in info["participants"]:
            self.db.upsert_summoner(self.db.create_summoner_payload(p))
            match_id = info.get("platformId") + "_" + str(info.get("gameId"))
            self.db.store_participant(self.db.create_participant_payload(match_id, p))
        
            rank_before = self.db.get_rank_at_time(p.get("puuid"), info.get("gameStartTimestamp"))
            if rank_before.get("error") == "sql: no rows in result set":
                for rank_after in self.api.get_rank(p.get("puuid")):
                    self.db.store_rank(self.db.create_rank_payload(match_id, rank_after))
            if p.get("puuid") == self.puuid:
                self.rank_before = rank_before
                return p