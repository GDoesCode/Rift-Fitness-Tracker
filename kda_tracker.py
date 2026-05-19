import os
import requests
import time
import psycopg2 as psql


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
            riot_id TEXT,
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
            total_damage_dealt INTEGER
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

def store_participant(connection, match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold, damage):
    #Store individual participant data for a match
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO participants(match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold_earned, total_damage_dealt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold, damage))
        connection.commit()

def get_match_ids_by_puuid(puuid, count=20, start=0):
    url = f"https://{REGION_URL}lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"start": start, "count": count}
    return safe_get(url, params=params)

def get_match_by_id(match_id):
    url = f"https://{REGION_URL}lol/match/v5/matches/{match_id}"
    return safe_get(url)

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
            print(participant)
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
            
            store_participant(connection, mid, p_puuid, p_champ, k, d, a, kda, team, position, lane, gold, damage)
            
            # Print tracked summoner info
            if p_puuid == puuid:
                print(f"Stored {mid}: {p_name} ({p_champ}) {k}/{d}/{a} -> KDA {kda:.2f}")

    connection.close()

if __name__ == "__main__":
    summoner_name = input("Input summoner name:\n")
    summoner_name = summoner_name.split("#")
    #print(summoner_name)
    summoner_dto = safe_get(f"https://{REGION_URL}riot/account/v1/accounts/by-riot-id/{summoner_name[0]}/{summoner_name[1]}")
    puuid = summoner_dto["puuid"]
    #print(puuid)
    summoner_id = safe_get(f"https://{PLATFORM_URL}lol/summoner/v4/summoners/by-puuid/{puuid}")
    #print(summoner_id["profileIconId"])
    match_ids = safe_get(f"https://{REGION_URL}lol/match/v5/matches/by-puuid/{puuid}/ids", params={"startTime": 1778799600, "start": 0, "count": 20})
    #print(match_ids)
    kda_to_database(puuid)
