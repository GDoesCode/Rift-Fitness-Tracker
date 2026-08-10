import os
import sys
import time
import requests
import subprocess
import threading
from riot_api import RiotAPIClient
from tracker_worker import LiveTrackerWorker
from database import RiftFitnessTrackerDatabase
from config import load_user_data, save_riot_id

CURRENT_VERSION = get_app_version()
REPO_OWNER = "GDoesCode"
REPO_NAME = "Rift-Fitness-Tracker"
EXE_NAME = os.path.basename(sys.executable) if getattr(sys, 'frozen', False) else "myapp.exe"

def get_app_version() -> str:
    try:
        from rift_fitness_tracker._version import VERSION
        return VERSION
    except ImportError:
        pass

    try:
        tag = subprocess.check_output(["git", "describe", "--tags", "--always"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        return tag.lstrip("v")
    except Exception:
        return "0.0.0-dev"  # Default version if all else fails

def check_for_updates():
    # Only run auto-update logic when running as a compiled binary/exe
    if not getattr(sys, 'frozen', False):
        print("[Dev Mode] Skipping update check.")
        return

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        latest_version = data["tag_name"].lstrip("v")

        if latest_version > CURRENT_VERSION:
            print(f"\n[!] Update available: v{latest_version} (Current: v{CURRENT_VERSION})")
            choice = input("Would you like to update now? (y/n): ").strip().lower()
            if choice == 'y':
                apply_update(data)
    except Exception as e:
        print(f"[!] Update check failed: {e}")

def apply_update(release_data):
    # Search release assets for the .exe file
    exe_asset = None
    for asset in release_data.get("assets", []):
        if asset["name"].endswith(".exe"):
            exe_asset = asset
            break

    if not exe_asset:
        print("[!] No .exe asset found in the latest release.")
        return

    download_url = exe_asset["browser_download_url"]
    new_exe_path = "update_temp.exe"

    print(f"Downloading {exe_asset['name']}...")
    res = requests.get(download_url, stream=True)
    with open(new_exe_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=8192):
            f.write(chunk)

    print("Download complete. Applying update...")
    
    # Create a batch script to swap executables after this process exits
    batch_script = f"""@echo off
timeout /t 2 /nobreak > NUL
move /y "{new_exe_path}" "{EXE_NAME}"
start "" "{EXE_NAME}"
del "%~f0"
"""
    with open("updater.bat", "w") as f:
        f.write(batch_script)

    # Launch the updater script in the background and terminate current process
    subprocess.Popen(["cmd.exe", "/c", "updater.bat"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    sys.exit(0)

def authenticate_summoner(api_client):
    while True:
        user_data = load_user_data()
        name = user_data.get("gameName")
        tag = user_data.get("tagLine")
    
        if name:
            print(f"Welcome back, {name}!", flush=True)
            sys.stdout.flush()
            return user_data.get("puuid"), f"{name}#{tag}"
        else:
            riot_id = input("Input summoner name (Name#TAG):\n").strip()
        
            if "#" not in riot_id:
                print("[ERROR] Invalid Riot ID formatting. Remember the '#' symbol. Try again.\n")
                continue
                
            name_split = riot_id.split("#")
        
            # Ensure there is exactly one '#' separating a name and a tag
            if len(name_split) == 2 and name_split[0] and name_split[1]:
                try:
                    print("[SYSTEM] Reaching out to Riot servers for authentication...")
                    puuid = api_client.get_puuid(name_split[0], name_split[1])
                    print("[SYSTEM] Successfully authenticated.")
                    save_riot_id(puuid, api_client)
                except Exception as e:
                    print(f"[ERROR] An error occurred while fetching PUUID: {e}")
            else:
                print("[ERROR] Invalid format. Ensure you have text before and after the '#'. (e.g., HideOnBush#KR1)\n")


def run_background_tracking(worker, puuid):
    bg_thread = threading.Thread(target=worker.run_tracking_loop, daemon=True)
    bg_thread.start()
    worker.historical_sync(puuid)
    
    # Keep app alive while background worker is listening
    try:
        print("[SYSTEM] Background tracking active. Press Ctrl+C to return to the main menu.")
        while True: 
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down tracker service.")
        worker.stop_event.set()


def main():
    api_client = RiotAPIClient()
    db_api = RiftFitnessTrackerDatabase()

    try:
        authenticate_summoner(api_client)
        game_name, tag_line, puuid = load_user_data().values()
        worker = LiveTrackerWorker(puuid, game_name, tag_line, api_client, db_api)

        def track_historical():
            try:
                print("[SYSTEM] Running historical sync... (Ctrl+C to return to menu)")
                worker.historical_sync(puuid)
            except KeyboardInterrupt:
                print("\n[SYSTEM] Historical sync interrupted. Returning to menu...")

        def track_live():
            try:
                print("[SYSTEM] Starting live tracking... (Ctrl+C to return to menu)")
                worker.run_tracking_loop()
            except KeyboardInterrupt:
                print("\n[SYSTEM] Live tracking stopped. Returning to menu...")

        def track_both():
            try:
                print("[SYSTEM] Starting both... (Ctrl+C to return to menu)")
                run_background_tracking(worker, puuid)
            except KeyboardInterrupt:
                print("\n[SYSTEM] Background tracking stopped. Returning to menu...")

        def exit_application():
            print("\n[SYSTEM] Exiting application. Goodbye!")
            if hasattr(worker, 'stop_overlay_process'):
                worker.stop_overlay_process()
            exit()

        menu_options = {
            "1": track_historical,
            "2": track_live,
            "3": track_both,
            "4": exit_application
        }

        while True:
            print("\nChoose mode:\n" \
            "1. Track past 20 games\n" \
            "2. Track live game\n" \
            "3. Both (live in background)\n" \
            "4. Exit Application")
            mode = input("> ").strip()
            
            if mode in menu_options:
                menu_options[mode]()
            else:
                print("[ERROR] Invalid choice. Please enter 1, 2, 3, or 4.")

    except (KeyboardInterrupt, EOFError):
        # Catches a global Ctrl+C at the menu level
        print("\n\n[SYSTEM] Execution interrupted by user. Exiting gracefully... Goodbye!")
        if 'worker' in locals() and hasattr(worker, 'stop_overlay_process'):
            worker.stop_overlay_process()

if __name__ == '__main__':
    main()