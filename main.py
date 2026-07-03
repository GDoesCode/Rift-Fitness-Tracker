import time
import threading
from database import RiftFitnessTrackerDatabase
from riot_api import RiotAPIClient
from tracker_worker import LiveTrackerWorker

def main():
    riot_id = input("Input summoner name (Name#TAG):\n").strip()
    if "#" not in riot_id:
        print("Invalid Riot ID formatting. Remember the '#' symbol.")
        return
        
    name_split = riot_id.split("#")
    
    api_client = RiotAPIClient()
    db_api = RiftFitnessTrackerDatabase()

    print("[SYSTEM] Reaching out to Riot servers for authentication...")
    puuid = api_client.get_puuid(name_split[0], name_split[1])

    mode = input("\nChoose mode:\n1. Track past 20 games\n2. Track live game\n3. Both (live in background)\n> ")
    
    worker = LiveTrackerWorker(puuid, riot_id, api_client, db_api)

    if mode == "1":
        worker.historical_sync(puuid)
    elif mode == "2":
        worker.run_tracking_loop()
    elif mode == "3":
        bg_thread = threading.Thread(target=worker.run_tracking_loop, daemon=True)
        bg_thread.start()
        worker.historical_sync(puuid)
        # Keep app alive while background worker is listening
        try:
            while True: 
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SYSTEM] Shutting down tracker service.")
            worker.stop_event.set()

if __name__ == "__main__":
    main()