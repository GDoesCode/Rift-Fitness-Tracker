import threading
from config import API_KEY
from riot_api import RiotAPIClient
from database import DatabaseManager
from tracker_worker import LiveTrackerWorker

def historical_sync(puuid, api: RiotAPIClient, db: DatabaseManager):
    print("\n[HISTORICAL] Synced requested. Pulling down past 20 games...")
    match_ids = api.get_match_ids(puuid, count=20)
    
    for m_id in match_ids:
        if db.match_exists(m_id):
            print(f"Skipping match {m_id} (Already recorded)")
            continue
            
        print(f"Processing old match record: {m_id}")
        match = api.get_match(m_id)
        info = match["info"]
        
        with db.get_connection() as conn:
            db.store_match(conn, m_id, info.get("gameStartTimestamp"), info.get("gameMode"), info.get("gameDuration"), info.get("mapId"), info.get("queueId"))
            for p in info["participants"]:
                p_puuid = p.get("puuid")
                db.upsert_summoner(conn, p_puuid, p.get("riotIdGameName"), p.get("profileIcon"))
                k, d, a = p.get("kills", 0), p.get("deaths", 0), p.get("assists", 0)
                db.store_participant(
                    conn, m_id, p_puuid, p.get("championName"), k, d, a, (k+a)/max(1,d),
                    "RED" if p.get("teamId") == 200 else "BLUE", p.get("individualPosition"), p.get("lane"),
                    p.get("goldEarned"), p.get("totalDamageDealt"), p.get("totalMinionsKilled")
                )
            conn.commit()
    print("[HISTORICAL] Sync Complete.")

def main():
    riot_id = input("Input summoner name (Name#TAG):\n").strip()
    if "#" not in riot_id:
        print("Invalid Riot ID formatting. Remember the '#' symbol.")
        return
        
    name_split = riot_id.split("#")
    
    api_client = RiotAPIClient()
    db_manager = DatabaseManager()
    db_manager.init_db()

    print("[SYSTEM] Reaching out to Riot servers for authentication...")
    puuid = api_client.get_puuid(name_split[0], name_split[1])

    mode = input("\nChoose mode:\n1. Track past 20 games\n2. Track live game\n3. Both (live in background)\n> ")
    
    worker = LiveTrackerWorker(puuid, riot_id, api_client, db_manager)

    if mode == "1":
        historical_sync(puuid, api_client, db_manager)
    elif mode == "2":
        worker.run_tracking_loop()
    elif mode == "3":
        bg_thread = threading.Thread(target=worker.run_tracking_loop, daemon=True)
        bg_thread.start()
        historical_sync(puuid, api_client, db_manager)
        # Keep app alive while background worker is listening
        try:
            while True: 
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SYSTEM] Shutting down tracker service.")
            worker.stop_event.set()

if __name__ == "__main__":
    main()