import requests

SERVER_URL = "http://homeserver:8000"

def check_if_match_logged(match_id):
    res = requests.get(f"{SERVER_URL}/matches/{match_id}/exists")
    return res.json().get("exists", False)

def upload_match_and_participants(match_data_payload):
    # Sends match properties and participant list as a single JSON object
    res = requests.post(f"{SERVER_URL}/matches", json=match_data_payload)
    return res.json()

def save_workout(match_id, puuid, pushups, situps, planks, runs):
    payload = {
        "match_id": match_id,
        "puuid": puuid,
        "deaths_pushups": pushups,
        "cs_situps": situps,
        "loss_planks": planks,
        "demotion_runs": runs
    }
    res = requests.post(f"{SERVER_URL}/punishments", json=payload)
    return res.json()