import os
import requests
import time
import sqlite3
from urllib.parse import quote_plus

API_KEY = os.environ.get("RIOT_API_KEY")
if not API_KEY:
    raise SystemExit("Set RIOT_API_KEY environment variable")
HEADERS = {"X-Riot-Token": API_KEY}
PLATFORM_URL = "euw1.api.riotgames.com"
REGION_URL = "europe.api.riotgames.com"
DATABASE_FILE = "kda.db"

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
    connection.execute("""
    CREATE TABLE IF NOT EXISTS matches(
        match_id TEXT PRIMARY KEY,
        timestamp INTEGER,
        champion TEXT,
        kills INTEGER,
        deaths INTEGER,
        assists INTEGER,
        kda REAL
    )""")
    connection.commit()

def kda_to_database():
    connection = sqlite3.connect(DATABASE_FILE)
    init_db(connection)

    params = {"start": start, "count": count}
    return safe_get(url, params=params)

    # 4) fetch each match and store KDA for this puuid
    for mid in match_ids:
        # skip if already stored
        cur = connection.execute("SELECT 1 FROM matches WHERE match_id=?", (mid,)).fetchone()
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
        store_match(connection, mid, timestamp, champ, k, d, a, kda)
        print(f"Stored {mid}: {champ} {k}/{d}/{a} -> KDA {kda:.2f}")

    connection.close()

if __name__ == "__main__":
    summoner_name = input("Input summoner name:\n")
    summoner_name = summoner_name.split("#")
    print(summoner_name)
    summoner_dto = safe_get(f"https://{REGION_URL}/riot/account/v1/accounts/by-riot-id/{summoner_name[0]}/{summoner_name[1]}")
    puuid = summoner_dto["puuid"]
    print(puuid)
    summoner_id = safe_get(f"https://{PLATFORM_URL}/lol/summoner/v4/summoners/by-puuid/{puuid}")
    print(summoner_id["profileIconId"])
    current_match = safe_get(f"https://{PLATFORM_URL}/lol/spectator/v5/active-games/by-summoner/{puuid}")
    print(current_match) # get match details
