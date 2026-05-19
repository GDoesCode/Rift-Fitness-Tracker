import os
import requests
import time
import psycopg2 as psql
import threading
from datetime import datetime


API_KEY = os.environ.get("RIOT_API_KEY")
if not API_KEY:
    raise SystemExit("Set RIOT_API_KEY environment variable")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL environment variable")
else:
    print(DATABASE_URL)

HEADERS = {"X-Riot-Token": API_KEY}
PLATFORM_URL = "euw1.api.riotgames.com/"
REGION_URL = "europe.api.riotgames.com/"

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
            summoner_name TEXT NOT NULL,
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

def get_active_game(encrypted_summoner_id):
    #Fetch current active game for a summoner
    url = f"https://{PLATFORM_URL}lol/spectator/v5/active-games/by-summoner/{encrypted_summoner_id}"
    try:
        return safe_get(url, max_retries=1)
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise

def get_rank_by_summoner_id(encrypted_summoner_id):
    #Fetch summoner's current rank
    url = f"https://{PLATFORM_URL}lol/league/v4/entries/by-summoner/{encrypted_summoner_id}"
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

def calculate_punishments(connection, match_id, puuid, participant_data, match_duration, was_win, rank_before, rank_after):
    #Calculate and store punishments for a finished game
    deaths = participant_data.get("deaths", 0)
    minions = participant_data.get("totalMinionsKilled", 0)
    cs_per_min = minions / max(1, match_duration / 60)
    
    deaths_pushups = deaths
    cs_situps = 1 if cs_per_min < 10 else 0
    loss_planks = 1 if not was_win else 0
    demotion_runs = 0
    
    if rank_before and rank_after:
        rank_before_tier = f"{rank_before[0].get('tier', 'UNKNOWN')}{rank_before[0].get('rank', '')}"
        rank_after_tier = f"{rank_after[0].get('tier', 'UNKNOWN')}{rank_after[0].get('rank', '')}"
        if rank_before_tier != rank_after_tier:
            demotion_runs = 5
    
    total = deaths_pushups + cs_situps + loss_planks + demotion_runs
    
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO punishments(match_id, puuid, deaths_pushups, cs_situps, loss_planks, demotion_runs, total_punishment_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (match_id, puuid, deaths_pushups, cs_situps, loss_planks, demotion_runs, total))
        connection.commit()
    
    return {
        "deaths_pushups": deaths_pushups,
        "cs_situps": cs_situps,
        "loss_planks": loss_planks,
        "demotion_runs": demotion_runs,
        "total": total
    }

def track_live_game(puuid, encrypted_summoner_id, poll_interval=1):
    #Monitor active game and record K/D/A updates every poll_interval seconds
    connection = get_db_connection()
    init_db(connection)
    
    print(f"\n[LIVE] Checking for active game...")
    active_game = get_active_game(encrypted_summoner_id)
    
    if not active_game:
        print("[LIVE] No active game found")
        connection.close()
        return
    
    game_id = active_game.get("gameId")
    print(f"[LIVE] Game started! Tracking... (Game ID: {game_id})")
    
    rank_before = get_rank_by_summoner_id(encrypted_summoner_id)
    print(f"[LIVE] Pre-game rank: {rank_before}")
    
    try:
        while True:
            active_game = get_active_game(encrypted_summoner_id)
            
            if not active_game:
                print("[LIVE] Game ended!")
                break
            
            participants = active_game.get("participants", [])
            your_data = next((p for p in participants if p.get("summonerName") == active_game.get("summonerName")), None)
            
            if not your_data:
                print("[LIVE] Could not find your player data")
                time.sleep(poll_interval)
                continue
            
            kills = your_data.get("kills", 0)
            deaths = your_data.get("deaths", 0)
            assists = your_data.get("assists", 0)
            
            store_live_snapshot(connection, game_id, puuid, kills, deaths, assists)
            print(f"[LIVE] K/D/A: {kills}/{deaths}/{assists}")
            
            time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        print("\n[LIVE] Stopped by user")
    finally:
        connection.close()

def process_finished_game(connection, puuid, encrypted_summoner_id, match_id):
    #After game ends, store data in main tables and calculate punishments
    try:
        match = get_match_by_id(match_id)
        match_info = match["info"]
        rank_after = get_rank_by_summoner_id(encrypted_summoner_id)
        
        timestamp = match_info.get("gameStartTimestamp", 0)
        game_mode = match_info.get("gameMode", "Unknown")
        duration = match_info.get("gameDuration", 0)
        map_id = match_info.get("mapId", 0)
        queue_id = match_info.get("queueId", 0)
        
        store_match(connection, match_id, timestamp, game_mode, duration, map_id, queue_id)
        
        your_participant = None
        rank_before = get_rank_by_summoner_id(encrypted_summoner_id)
        
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
            minions = participant.get("totalminionsKilled", 0)
            
            store_participant(connection, mid, p_puuid, p_champ, k, d, a, kda, team, position, lane, gold, damage, minions)
            
            # Print tracked summoner info
            if p_puuid == puuid:
                print(f"Stored {mid}: {p_name} ({p_champ}) {k}/{d}/{a} -> KDA {kda:.2f}")

    connection.close()

if __name__ == "__main__":
    summoner_name = input("Input summoner name:\n")
    summoner_name = summoner_name.split("#")
    
    summoner_dto = safe_get(f"https://{REGION_URL}riot/account/v1/accounts/by-riot-id/{summoner_name[0]}/{summoner_name[1]}")
    puuid = summoner_dto["puuid"]
    
    summoner_id = get_summoner_by_puuid(puuid)
    encrypted_summoner_id = summoner_id.get("id")
    
    print(f"Summoner: {summoner_name[0]}#{summoner_name[1]}")
    print(f"PUUID: {puuid}")
    print(f"Encrypted ID: {encrypted_summoner_id}")
    
    mode = input("\nChoose mode:\n1. Track past 20 games\n2. Track live game\n3. Both (live in background)\n> ")
    
    if mode == "1":
        kda_to_database(puuid)
    elif mode == "2":
        track_live_game(puuid, encrypted_summoner_id, poll_interval=1)
    elif mode == "3":
        live_thread = threading.Thread(target=track_live_game, args=(puuid, encrypted_summoner_id, 1), daemon=True)
        live_thread.start()
        print("\n[INFO] Live game tracker started in background")
        kda_to_database(puuid)
    else:
        print("Invalid mode")