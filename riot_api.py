import requests
import time
import urllib3
from config import API_KEY, REGION_URL, PLATFORM_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RiotAPIClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"X-Riot-Token": API_KEY, "Accept": "application/json"})

    def _safe_get(self, url, params=None, max_retries=5):
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.get(url, params=params, timeout=5)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else 1 + attempt * 2
                    print(f"⚠️ [429] Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    if attempt >= max_retries:
                        raise RuntimeError("Max retries exceeded on 429.")
                    continue
                if 500 <= resp.status_code < 600 and attempt < max_retries:
                    time.sleep(1 + attempt * 2)
                    continue
                raise RuntimeError(f"API Error {resp.status_code}: {resp.text}")
            except requests.exceptions.RequestException as e:
                if attempt >= max_retries:
                    raise e
                time.sleep(1 + attempt * 2)

    def get_puuid(self, game_name, tag_line):
        url = f"https://{REGION_URL}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        return self._safe_get(url)["puuid"]

    def get_summoner_id_data(self, puuid):
        url = f"https://{PLATFORM_URL}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return self._safe_get(url)

    def get_match_ids(self, puuid, count=20):
        url = f"https://{REGION_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return self._safe_get(url, params={"start": 0, "count": count})

    def get_match(self, match_id):
        url = f"https://{REGION_URL}/lol/match/v5/matches/{match_id}"
        return self._safe_get(url)

    def get_rank(self, puuid):
        url = f"https://{PLATFORM_URL}/lol/league/v4/entries/by-puuid/{puuid}"
        try:
            return self._safe_get(url, max_retries=1)
        except Exception:
            return None

    def get_live_client_data(self):
        """Pings local live game host endpoint."""
        try:
            resp = requests.get("https://127.0.0.1:2999/liveclientdata/allgamedata", timeout=0.8, verify=False)
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None