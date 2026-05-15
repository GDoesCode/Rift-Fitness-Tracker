# kda_tracker.py
import os
import time
import requests
import sqlite3
from urllib.parse import quote_plus

# --- Configuration ---
API_KEY = os.environ.get("RIOT_API_KEY")
if not API_KEY:
    raise SystemExit("Set RIOT_API_KEY environment variable")

# Platform routing value for summoner endpoints (e.g., "na1", "euw1", "kr")
PLATFORM = "euw1"
# Continent routing for match-v5 (AMERICAS, EUROPE, ASIA)
CONTINENT = "EUROPE"
SUMMONER_NAME = "JustG#01G"  # change this

# SQLite DB file
DB_FILE = "kda.db"

# --- Helper: requests session with default headers ---
session = requests.Session()
session.headers.update({"X-Riot-Token": API_KEY, "Accept": "application/json"})

# --- Simple rate-limit/backoff helper ---
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

# --- Riot endpoints (no wrapper) ---
def get_summoner_by_name(platform, summoner_name):
    name_enc = quote_plus(summoner_name)
    url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{name_enc}"
    return safe_get(url)

def get_match_ids_by_puuid(continent, puuid, count=20, start=0):
    url = f"https://{continent}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    params = {"start": start, "count": count}
    return safe_get(url, params=params)

def get_match_by_id(continent, match_id):
    url = f"https://{continent}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    return safe_get(url)

# --- DB helpers ---
def init_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS matches(
        match_id TEXT PRIMARY KEY,
        timestamp INTEGER,
        champion TEXT,
        kills INTEGER,
        deaths INTEGER,
        assists INTEGER,
        kda REAL
    )""")
    conn.commit()

def store_match(conn, match_id, timestamp, champ, k, d, a, kda):
    conn.execute(
        "INSERT OR IGNORE INTO matches(match_id, timestamp, champion, kills, deaths, assists, kda) VALUES (?,?,?,?,?,?,?)",
        (match_id, timestamp, champ, k, d, a, kda)
    )
    conn.commit()

# --- Processing ---
def process_recent_matches(summoner_name, platform, continent, count=20):
    # 1) get puuid
    summ = get_summoner_by_name(platform, summoner_name)
    puuid = summ["puuid"]
    print(f"PUUID for {summoner_name}: {puuid}")

    # 2) get match ids
    match_ids = get_match_ids_by_puuid(continent, puuid, count=count)
    print(f"Found {len(match_ids)} match ids (requested {count})")

    # 3) open DB
    conn = sqlite3.connect(DB_FILE)
    init_db(conn)

    # 4) fetch each match and store KDA for this puuid
    for mid in match_ids:
        # skip if already stored
        cur = conn.execute("SELECT 1 FROM matches WHERE match_id=?", (mid,)).fetchone()
        if cur:
            print(f"Skipping stored match {mid}")
            continue

        match = get_match_by_id(continent, mid)
        # find participant by puuid
        participant = None
        for p in match["info"]["participants"]:
            if p["puuid"] == puuid:
                participant = p
                break
        if not participant:
            print(f"PUUID not found in match {mid}, skipping")
            continue

        k = participant.get("kills", 0)
        d = participant.get("deaths", 0)
        a = participant.get("assists", 0)
        champ = participant.get("championName", "Unknown")
        timestamp = match["info"].get("gameStartTimestamp", 0)
        kda = (k + a) / max(1, d)
        store_match(conn, mid, timestamp, champ, k, d, a, kda)
        print(f"Stored {mid}: {champ} {k}/{d}/{a} -> KDA {kda:.2f}")

    conn.close()

# --- Example usage ---
if __name__ == "__main__":
    process_recent_matches(SUMMONER_NAME, PLATFORM, CONTINENT, count=50)
