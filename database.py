import requests

class RiftFitnessTrackerDatabase:
    def __init__(self):
        self.server_url = "http://5.tcp.eu.ngrok.io:21104"
        # Creating a Session handles connection pooling automatically
        self.session = requests.Session()

#region Database interaction methods

    def match_exists(self, match_id):
        res = self.session.get(f"{self.server_url}/matches/{match_id}/exists")
        return res.json().get("exists", False)
    
    def get_rank_at_time(self, puuid, timestamp):
        res = self.session.get(f"{self.server_url}/rank/{puuid}/{timestamp}")
        return res.json()
    
    def store_live_snapshot(self, live_snapshot_payload):
        res = self.session.post(f"{self.server_url}/matches/live", json=live_snapshot_payload)
        return res.json()
    
    def upsert_summoner(self, summoner_payload):
        res = self.session.post(f"{self.server_url}/summoners", json=summoner_payload)
        return res.json()

    def store_match(self, match_payload):
        res = self.session.post(f"{self.server_url}/matches", json=match_payload)
        return res.json()

    def store_participant(self, participant_payload):
        res = self.session.post(f"{self.server_url}/participants", json=participant_payload)
        return res.json()

    def store_punishment(self, punishment_payload):
        res = self.session.post(f"{self.server_url}/punishments", json=punishment_payload)
        return res.json()
    
    def store_rank(self, rank_payload):
        res = self.session.post(f"{self.server_url}/rank", json=rank_payload)
        return res.json()
    
#endregion
    
#region Payload creation methods

    def create_match_payload(self, match_id, info=None):
        # Fallback to an empty dict if info is None to prevent .get() from crashing
        info = info or {} 
        
        return {
            "match_id": match_id,
            "game_start_timestamp": info.get("gameStartTimestamp"),
            "game_mode": info.get("gameMode"),
            "game_duration": info.get("gameDuration"),
            "map_id": info.get("mapId"),
            "queue_id": info.get("queueId")
        }
    
    def create_live_snapshot(self, puuid, scores):
        return {
            "puuid": puuid,
            "kills": scores.get("kills", 0),
            "deaths": scores.get("deaths", 0),
            "assists": scores.get("assists", 0)
        }
    
    def create_punishment_payload(self, match_id, puuid, pushups, situps, planks, runs):
        return {
            "match_id": match_id,
            "puuid": puuid,
            "death_pushups": pushups,
            "cs_situps": situps,
            "loss_planks": planks,
            "demotion_runs": runs
        }
    
    def create_participant_payload(self, match_id, p=None):
        # Fallback to an empty dict if p is None to prevent .get() from crashing
        p = p or {}
        
        return {
            "match_id": match_id,
            "puuid": p.get("puuid"),
            "champion_name": p.get("championName"),
            "kills": p.get("kills", 0),
            "deaths": p.get("deaths", 0),
            "assists": p.get("assists", 0),
            "kda": (p.get("kills", 0) + p.get("assists", 0)) / max(1, p.get("deaths", 0)),
            "team": "RED" if p.get("teamId") == 200 else "BLUE",
            "individual_position": "SUPPORT" if p.get("individualPosition") == "UTILITY" else p.get("individualPosition"),
            "gold_earned": p.get("goldEarned"),
            "total_minions_killed": p.get("totalMinionsKilled") + p.get("neutralMinionsKilled")
        }
    
    def create_summoner_payload(self, p):
        return {
            "puuid": p.get("puuid"),
            "riot_id_game_name": p.get("riotIdGameName"),
            "profile_icon": p.get("profileIcon")
        }
    
    def create_rank_payload(self, match_id, rank):
        return {
            "match_id": match_id,
            "puuid": rank.get("puuid"),
            "queue_type": rank.get("queueType"),
            "tier": rank.get("tier"),
            "rank": rank.get("rank"),
            "league_points": rank.get("leaguePoints")
        }
    
#endregion