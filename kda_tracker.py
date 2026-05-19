import os
import requests
import time
import psycopg2 as psql
import threading
import urllib3
from enum import Enum
from enum import IntEnum
from datetime import datetime

# Suppress SSL warnings for Live Client Data API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

#region Global Variables

API_KEY = os.environ.get("RIOT_API_KEY")
if not API_KEY:
    raise SystemExit("Set RIOT_API_KEY environment variable")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL environment variable")
 
HEADERS = {"X-Riot-Token": API_KEY}
PLATFORM_URL = "euw1.api.riotgames.com/"
REGION_URL = "europe.api.riotgames.com/"

class Tier(IntEnum):
    IRON = 0
    BRONZE = 1
    SILVER = 2
    GOLD = 3
    PLATINUM = 4
    EMERALD = 5
    DIAMOND = 6
    MASTER = 7
    GRANDMASTER = 8
    CHALLENGER = 9

class Rank(float, Enum):
    IV = 0.1
    III = 0.2
    II = 0.3
    I = 0.4

#endregion

# --- Helper: requests session with default headers ---
session = requests.Session()
session.headers.update({"X-Riot-Token": API_KEY, "Accept": "application/json"})

def safe_get(url, params=None, max_retries=5):
    attempt = 0
    while True:
        attempt += 1
        resp = session.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            # Rate limited: respect Retry-After if present
            retry_after = resp.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else 1 + attempt * 2
            print(f"429 received, sleeping {wait}s (attempt {attempt})")
            time.sleep(wait)
            if attempt >= max_retries:
                raise RuntimeError("Too many 429 responses")
            continue
        if 500 <= resp.status_code < 600 and attempt < max_retries:
            # server error: backoff and retry
            wait = 1 + attempt * 2
            print(f"Server error {resp.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        # other errors: raise with message
        raise RuntimeError(f"Request failed {resp.status_code}: {resp.text}")

def init_db(connection):
    with connection.cursor() as cur:
        # Summoners table: unique summoner identities
        cur.execute("""
        CREATE TABLE IF NOT EXISTS summoners(
            puuid TEXT PRIMARY KEY,
            riot_id_game_name TEXT,
            profile_icon_id INTEGER
        )""")
        
        # Matches table: core match data
        cur.execute("""
        CREATE TABLE IF NOT EXISTS matches(
            match_id TEXT PRIMARY KEY,
            timestamp BIGINT,
            game_mode TEXT,
            game_duration INTEGER,
            map_id INTEGER,
            queue_id INTEGER
        )""")
        
        # Participants table: all players in each match
        cur.execute("""
        CREATE TABLE IF NOT EXISTS participants(
            participant_id SERIAL PRIMARY KEY,
            match_id TEXT NOT NULL REFERENCES matches(match_id),
            puuid TEXT NOT NULL REFERENCES summoners(puuid),
            champion TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            kda REAL,
            team TEXT,
            position TEXT,
            lane TEXT,
            gold_earned INTEGER,
            total_damage_dealt INTEGER,
            minions_killed INTEGER
        )""")
        
        # Live games table: real-time K/D/A snapshots during active games
        cur.execute("""
        CREATE TABLE IF NOT EXISTS live_games(
            live_id SERIAL PRIMARY KEY,
            game_id TEXT,
            puuid TEXT NOT NULL REFERENCES summoners(puuid),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER
        )""")
        
        # Punishments table: post-game penalties
        cur.execute("""
        CREATE TABLE IF NOT EXISTS punishments(
            punishment_id SERIAL PRIMARY KEY,
            match_id TEXT NOT NULL REFERENCES matches(match_id),
            puuid TEXT NOT NULL REFERENCES summoners(puuid),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deaths_pushups INTEGER DEFAULT 0,
            cs_situps INTEGER DEFAULT 0,
            loss_planks INTEGER DEFAULT 0,
            demotion_runs INTEGER DEFAULT 0,
            total_punishment_count INTEGER DEFAULT 0
        )""")
        connection.commit()

def get_db_connection():
    return psql.connect(DATABASE_URL)

def match_exists(connection, match_id):
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM matches WHERE match_id = %s", (match_id,))
        return cur.fetchone() is not None


def upsert_summoner(connection, puuid, riot_id_game_name, profile_icon_id):
    #Insert or update summoner info
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO summoners(puuid, riot_id_game_name, profile_icon_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (puuid) DO UPDATE SET
                riot_id_game_name = EXCLUDED.riot_id_game_name,
                profile_icon_id = EXCLUDED.profile_icon_id
        """, (puuid, riot_id_game_name, profile_icon_id))
        connection.commit()

def store_match(connection, match_id, timestamp, game_mode, game_duration, map_id, queue_id):
    #Store match metadata
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO matches(match_id, timestamp, game_mode, game_duration, map_id, queue_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id) DO NOTHING
        """, (match_id, timestamp, game_mode, game_duration, map_id, queue_id))
        connection.commit()

def store_participant(connection, match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold, damage, minions):
    #Store individual participant data for a match
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO participants(match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold_earned, total_damage_dealt, minions_killed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold, damage, minions))
        connection.commit()

def get_match_ids_by_puuid(puuid, count=20, start=0):
    url = f"https://{REGION_URL}lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"start": start, "count": count}
    return safe_get(url, params=params)

def get_match_by_id(match_id):
    url = f"https://{REGION_URL}lol/match/v5/matches/{match_id}"
    return safe_get(url)

def get_summoner_by_puuid(puuid):
    url = f"https://{PLATFORM_URL}lol/summoner/v4/summoners/by-puuid/{puuid}"
    return safe_get(url)

def get_active_game(puuid):
    #Fetch current active game for a summoner
    url = f"https://{PLATFORM_URL}lol/spectator/v5/active-games/by-summoner/{puuid}"
    try:
        return safe_get(url, max_retries=1)
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise

def get_live_client_data():
    #Fetch live game data from League client running locally
    #Returns None if client is not running or no game is active
    url = "https://127.0.0.1:2999/liveclientdata/allgamedata"
    try:
        resp = requests.get(url, timeout=2, verify=False)
        if resp.status_code == 200:
            return resp.json()
        return None
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return None
    except Exception:
        return None

def get_live_player_data(player_name, live_data):
    #Extract your player data from live client data
    #player_name should be lowercase "gamename#tagline"
    if not live_data or "allPlayers" not in live_data:
        return None
    
    for player in live_data.get("allPlayers", []):
        riot_id = player.get("riotId", "")
        if riot_id.lower() == player_name.lower():
            return player
    return None

def get_rank_by_summoner_id(puuid):
    #Fetch summoner's current rank
    url = f"https://{PLATFORM_URL}lol/league/v4/entries/by-puuid/{puuid}"
    try:
        return safe_get(url, max_retries=1)
    except RuntimeError:
        return None

def store_live_snapshot(connection, game_id, puuid, kills, deaths, assists):
    #Store a live K/D/A snapshot during active game
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO live_games(game_id, puuid, kills, deaths, assists)
            VALUES (%s, %s, %s, %s, %s)
        """, (game_id, puuid, kills, deaths, assists))
        connection.commit()

def rank_down(rank_before, rank_after):
    val1 =  (Tier[rank_before["Tier"]].value + Rank[rank_before["Rank"]].value)
    val2 = (Tier[rank_after["Tier"]].value + Rank[rank_after["Rank"]].value)
    return val1 > val2

def calculate_punishments(connection, match_id, puuid, participant_data, match_duration, was_win, rank_before, rank_after):
    #Calculate and store punishments for a finished game
    deaths = participant_data.get("deaths", 0)
    minions = participant_data.get("totalMinionsKilled", 0)
    cs_per_min = minions / max(1, match_duration / 60)
    
    deaths_pushups = deaths * 5
    cs_situps = 10 - cs_per_min
    loss_planks = 1 if not was_win else 0
    demotion_runs = 0
    
    if rank_before and rank_after:
        rank_before = {"Tier": rank_before[0].get("tier", "UNKNOWN"), "Rank": rank_before[0].get("rank", "")}
        rank_after = {"Tier": rank_after[0].get("tier", "UNKNOWN"), "Rank": rank_after[0].get("rank", "")}
        if (rank_down(rank_before, rank_after)):
            demotion_runs = 1
    
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO punishments(match_id, puuid, deaths_pushups, cs_situps, loss_planks, demotion_runs, total_punishment_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (match_id, puuid, deaths_pushups, cs_situps, loss_planks, demotion_runs))
        connection.commit()
    
    return {
        "deaths_pushups": deaths_pushups,
        "cs_situps": cs_situps,
        "loss_planks": loss_planks,
        "demotion_runs": demotion_runs
    }

def track_live_game(puuid, riot_id, poll_interval=1, check_interval=30, stop_event=None):
    #Monitor active game using Live Client Data API for real-time K/D/A updates
    #Falls back to Spectator API for game detection if needed
    if stop_event is None:
        stop_event = threading.Event()
    
    connection = get_db_connection()
    init_db(connection)
    
    print(f"\n[LIVE] ✓ Thread started - waiting for active game (checking every {check_interval}s)")
    print("[LIVE] Using Live Client Data API for K/D/A updates")
    
    game_active = False
    last_check = 0
    rank_before = None
    game_id = None
    last_kda = None
    
    try:
        while not stop_event.is_set():
            current_time = time.time()
            
            # Check for active game periodically
            if current_time - last_check >= check_interval:
                try:
                    # Try Live Client API first
                    live_data = get_live_client_data()
                    
                    if not live_data:
                        # Fallback to Spectator API
                        spectator_data = get_active_game(puuid)
                        if not spectator_data:
                            if game_active:
                                print("[LIVE] ✓ Game ended! Fetching final stats from Match API...")
                                game_active = False
                                
                                # Get the most recent match ID for this summoner
                                try:
                                    match_ids = get_match_ids_by_puuid(puuid, count=1)
                                    if match_ids:
                                        latest_match_id = match_ids[0]
                                        process_finished_game(connection, puuid, latest_match_id)
                                        print("[LIVE] ✓ Final stats stored to database")
                                except Exception as e:
                                    print(f"[LIVE] Error fetching final match data: {e}")
                                
                                rank_before = None
                                game_id = None
                            else:
                                print(f"[LIVE] No game yet (checking every {check_interval}s)...")
                            
                            last_check = current_time
                            stop_event.wait(timeout=check_interval)
                            continue
                    
                    # Game found via Live Client API
                    if not game_active:
                        game_active = True
                        rank_before = get_rank_by_summoner_id(puuid)
                        game_info = live_data.get("gameData", {})
                        game_id = game_info.get("gameId")
                        print(f"[LIVE] ✓ Game found! (Game ID: {game_id})")
                        print(f"[LIVE] Pre-game rank: {rank_before}")
                    
                    last_check = current_time
                
                except Exception as e:
                    print(f"[LIVE] Error checking for game: {e}")
                    last_check = current_time
                    stop_event.wait(timeout=check_interval)
                    continue
            
            if not game_active:
                stop_event.wait(timeout=1)
                continue
            
            # Game is active - poll K/D/A via Live Client API
            try:
                live_data = get_live_client_data()
                
                if not live_data:
                    # Lost connection to client or game ended
                    print("\n[LIVE] ✓ Game ended or client disconnected!")
                    game_active = False
                    last_kda = None
                    
                    # Try to fetch final stats
                    try:
                        match_ids = get_match_ids_by_puuid(puuid, count=1)
                        if match_ids:
                            latest_match_id = match_ids[0]
                            process_finished_game(connection, puuid, latest_match_id)
                            print("[LIVE] ✓ Final stats stored to database")
                    except Exception as e:
                        print(f"[LIVE] Error fetching final match data: {e}")
                    
                    rank_before = None
                    game_id = None
                    stop_event.wait(timeout=1)
                    continue
                
                # Extract your player data
                your_data = get_live_player_data(riot_id, live_data)
                
                if not your_data:
                    stop_event.wait(timeout=poll_interval)
                    continue
                
                # Extract K/D/A from Live Client API
                kills = your_data.get("scores", {}).get("kills", 0)
                deaths = your_data.get("scores", {}).get("deaths", 0)
                assists = your_data.get("scores", {}).get("assists", 0)
                current_kda = (kills, deaths, assists)
                
                # Only update console and database if K/D/A changed
                if current_kda != last_kda:
                    print(f"\r[LIVE] K/D/A: {kills}/{deaths}/{assists}", end="", flush=True)
                    store_live_snapshot(connection, game_id, puuid, kills, deaths, assists)
                    last_kda = current_kda
                
                stop_event.wait(timeout=poll_interval)
            
            except Exception as e:
                print(f"[LIVE] Error during tracking: {e}")
                stop_event.wait(timeout=poll_interval)
    
    except KeyboardInterrupt:
        print("\n[LIVE] ✓ Stopped by user")
    finally:
        connection.close()
        print("[LIVE] Thread closed")

def process_finished_game(connection, puuid, match_id):
    #After game ends, store data in main tables and calculate punishments
    try:
        match = get_match_by_id(match_id)
        match_info = match["info"]
        rank_after = get_rank_by_summoner_id(puuid)
        
        timestamp = match_info.get("gameStartTimestamp", 0)
        game_mode = match_info.get("gameMode", "Unknown")
        duration = match_info.get("gameDuration", 0)
        map_id = match_info.get("mapId", 0)
        queue_id = match_info.get("queueId", 0)
        
        store_match(connection, match_id, timestamp, game_mode, duration, map_id, queue_id)
        
        your_participant = None
        rank_before = get_rank_by_summoner_id(puuid)
        
        for participant in match_info["participants"]:
            p_puuid = participant.get("puuid", "")
            p_name = participant.get("riotIdGameName", "")
            p_icon = participant.get("profileIcon", 0)
            p_champ = participant.get("championName", "Unknown")
            
            upsert_summoner(connection, p_puuid, p_name, p_icon)
            
            k = participant.get("kills", 0)
            d = participant.get("deaths", 0)
            a = participant.get("assists", 0)
            kda = (k + a) / max(1, d)
            team = "RED" if participant.get("teamId") == 200 else "BLUE"
            position = participant.get("individualPosition", "Unknown")
            lane = participant.get("lane", "Unknown")
            gold = participant.get("goldEarned", 0)
            damage = participant.get("totalDamageDealt", 0)
            minions = participant.get("totalMinionsKilled", 0)
            
            store_participant(connection, match_id, p_puuid, p_champ, k, d, a, kda, team, position, lane, gold, damage, minions)
            
            if p_puuid == puuid:
                your_participant = participant
                print(f"[GAME END] Stored {match_id}: {p_name} ({p_champ}) {k}/{d}/{a} -> KDA {kda:.2f}")
        
        if your_participant:
            was_win = your_participant.get("win", False)
            punishments = calculate_punishments(
                connection, match_id, puuid, your_participant, duration, was_win, rank_before, rank_after
            )
            print(f"[PUNISHMENTS] Press-ups: {punishments['deaths_pushups']}, Sit-ups: {punishments['cs_situps']}, Planks: {punishments['loss_planks']}min, Runs: {punishments['demotion_runs']}km")
            print(f"[PUNISHMENTS] Total: {punishments['total']} penalty points")
    
    except Exception as e:
        print(f"[ERROR] Failed to process finished game: {e}")

def kda_to_database(puuid):
    connection = get_db_connection()
    init_db(connection)

    match_ids = get_match_ids_by_puuid(puuid, count=20)
    
    for mid in match_ids:
        if match_exists(connection, mid):
            print(f"Skipping stored match {mid}")
            continue

        match = get_match_by_id(mid)
        match_info = match["info"]
        
        # Store match metadata
        timestamp = match_info.get("gameStartTimestamp", 0)
        game_mode = match_info.get("gameMode", "Unknown")
        duration = match_info.get("gameDuration", 0)
        map_id = match_info.get("mapId", 0)
        queue_id = match_info.get("queueId", 0)
        store_match(connection, mid, timestamp, game_mode, duration, map_id, queue_id)
        
        # Store all 10 participants
        for participant in match_info["participants"]:
            p_puuid = participant.get("puuid", "")
            p_name = participant.get("riotIdGameName", "")
            p_icon = participant.get("profileIcon", 0)
            p_champ = participant.get("championName", "Unknown")
            
            # Upsert summoner
            upsert_summoner(connection, p_puuid, p_name, p_icon)
            
            # Store participant stats
            k = participant.get("kills", 0)
            d = participant.get("deaths", 0)
            a = participant.get("assists", 0)
            kda = (k + a) / max(1, d)
            team = "RED" if participant.get("teamId") == 200 else "BLUE"
            position = participant.get("individualPosition", "Unknown")
            lane = participant.get("lane", "Unknown")
            gold = participant.get("goldEarned", 0)
            damage = participant.get("totalDamageDealt", 0)
            minions = participant.get("totalMinionsKilled", 0)
            
            store_participant(connection, mid, p_puuid, p_champ, k, d, a, kda, team, position, lane, gold, damage, minions)
            
            # Print tracked summoner info
            if p_puuid == puuid:
                print(f"Stored {mid}: {p_name} ({p_champ}) {k}/{d}/{a} -> KDA {kda:.2f}")

    connection.close()

if __name__ == "__main__":
    riot_id = input("Input summoner name:\n").lower()
    summoner_name = riot_id.split("#")
    
    summoner_dto = safe_get(f"https://{REGION_URL}riot/account/v1/accounts/by-riot-id/{summoner_name[0]}/{summoner_name[1]}")
    puuid = summoner_dto["puuid"]
    
    summoner_id = get_summoner_by_puuid(puuid)
    
    print(f"Summoner: {summoner_name[0]}#{summoner_name[1]}")
    print(f"PUUID: {puuid}")

    mode = input("\nChoose mode:\n1. Track past 20 games\n2. Track live game\n3. Both (live in background)\n> ")
    
    if mode == "1":
        kda_to_database(puuid)
    elif mode == "2":
        track_live_game(puuid, riot_id)
    elif mode == "3":
        live_thread = threading.Thread(target=track_live_game, args=(puuid, riot_id, 2))
        live_thread.start()
        print("\n[INFO] Live game tracker started in background")
        kda_to_database(puuid)
    else:
        print("Invalid mode")