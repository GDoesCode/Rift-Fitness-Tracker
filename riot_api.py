import os
import time
import base64
import urllib3
import requests
from config import REGION_URL, PLATFORM_URL 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY_BASE_URL = "https://anyway-rejoicing-collar.ngrok-free.dev/api/riot"

class RiotAPIClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _safe_get(self, riot_url, params=None, max_retries=5):
        attempt = 0
        while True:
            attempt += 1
            try:
                proxy_params = {"url": riot_url}
                if params:
                    encoded_params = requests.models.PreparedRequest()
                    encoded_params.prepare_url(riot_url, params)
                    proxy_params["url"] = encoded_params.url

                resp = self.session.get(PROXY_BASE_URL, params=proxy_params, timeout=7)
                
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
                raise RuntimeError(f"Proxy/API Error {resp.status_code}: {resp.text}")
            except requests.exceptions.RequestException as e:
                if attempt >= max_retries:
                    raise e
                time.sleep(1 + attempt * 2)

    def get_lcu_gameflow_phase(self):
        lockfile_path = r"C:\\Riot Games\\League of Legends\\lockfile"
        if not os.path.exists(lockfile_path):
            return "CLOSED"
        try:
            with open(lockfile_path, "r") as f:
                lockfile_content = f.read()
            parts = lockfile_content.split(":")
            port = parts[2]
            password = parts[3]
            auth_token = base64.b64encode(f"riot:{password}".encode('utf-8')).decode('utf-8')
            headers = {
                "Authorization": f"Basic {auth_token}",
                "Accept": "application/json"
            }
            url = f"https://127.0.0.1:{port}/lol-gameflow/v1/gameflow-phase"
            resp = requests.get(url, headers=headers, timeout=0.5, verify=False)
            if resp.status_code == 200:
                return resp.json()
            return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

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
        try:
            resp = requests.get("https://127.0.0.1:2999/liveclientdata/allgamedata", timeout=0.8, verify=False)
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None