import requests

class RiftFitnessTrackerDatabase:
    def __init__(self, server_url="http://homeserver:8000"):
        self.server_url = server_url
        # Creating a Session handles connection pooling automatically
        self.session = requests.Session()

    def match_exists(self, match_id):
        res = self.session.get(f"{self.server_url}/matches/{match_id}/exists")
        return res.json().get("exists", False)
    
    def store_live_snapshot(self, match_id, puuid, kills, deaths, assists):
        payload = {
            "match_id": match_id,
            "puuid": puuid,
            "kills": kills,
            "deaths": deaths,
            "assists": assists
        }
        res = self.session.post(f"{self.server_url}/matches/live", json=payload)
        return res.json()

    def store_match(self, match_payload):
        res = self.session.post(f"{self.server_url}/matches", json=match_payload)
        return res.json()

    def store_participant(self, participant_payload):
        res = self.session.post(f"{self.server_url}/participants", json=participant_payload)
        return res.json()
    
    def upsert_summoner(self, summoner_payload):
        res = self.session.post(f"{self.server_url}/summoners", json=summoner_payload)
        return res.json()

    def store_punishment(self, match_id, puuid, pushups, situps, planks, runs):
        payload = {
            "match_id": match_id,
            "puuid": puuid,
            "deaths_pushups": pushups,
            "cs_situps": situps,
            "loss_planks": planks,
            "demotion_runs": runs
        }
        res = self.session.post(f"{self.server_url}/punishments", json=payload)
        return res.json()