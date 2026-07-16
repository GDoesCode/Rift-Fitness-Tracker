import os
import json
from enum import Enum

CONFIG_FILE = "user_config.json"

PLATFORM_URL = "euw1.api.riotgames.com"
REGION_URL = "europe.api.riotgames.com"
PROXY_BASE_URL = "https://anyway-rejoicing-collar.ngrok-free.dev"

# Fitness Multipliers
DEATH_PUNISHMENT_MULTIPLIER = 1
CS_PUNISHMENT_MULTIPLIER = 1
LOSS_PUNISHMENT_MULTIPLIER = 1
DEMOTION_PUNISHMENT_MULTIPLIER = 1

DEATH_PUNISHMENT_NAME = ""
CS_PUNISHMENT_NAME = ""
LOSS_PUNISHMENT_NAME = ""
DEMOTION_PUNISHMENT_NAME = ""

class Tier(float, Enum):
    IRON = 0.0
    BRONZE = 1.0
    SILVER = 2.0
    GOLD = 3.0
    PLATINUM = 4.0
    EMERALD = 5.0
    DIAMOND = 6.0
    MASTER = 7.0
    GRANDMASTER = 8.0
    CHALLENGER = 9.0

class Rank(float, Enum):
    IV = 0.1
    III = 0.2
    II = 0.3
    I = 0.4

def load_user_data():
    """Checks if the file exists and loads the user data."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                # In case the file gets corrupted or is empty
                return {}
    return {}

def update_user_data(data):
    """Loads existing data, merges the new updates, and saves it all."""
    # 1. Load the current data from the file
    current_data = load_user_data()
    
    # 2. Merge the new updates into the current data
    current_data.update(data)
    
    # 3. Save the merged dictionary back to the file
    with open(CONFIG_FILE, "w") as file:
        json.dump(current_data, file, indent=4)

def save_riot_id(puuid, api_client):
    """Saves the users riot id locally"""
    resp = api_client.get_riot_id(puuid)
    user_data = {k: resp.get(k) for k in ["gameName", "tagLine", "puuid"]}
    update_user_data(user_data)
    print("[SYSTEM] Successfully save user data.")

