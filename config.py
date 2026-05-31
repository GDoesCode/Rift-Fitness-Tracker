import os
from enum import Enum, IntEnum

API_KEY = os.environ.get("RIOT_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not API_KEY:
    raise SystemExit("Set RIOT_API_KEY environment variable")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL environment variable")

PLATFORM_URL = "euw1.api.riotgames.com"
REGION_URL = "europe.api.riotgames.com"

# Fitness Multipliers
DEATHS_PUSHUPS_MULTIPLIER = 1
CS_SITUPS_MULTIPLIER = 1
LOSS_PLANKS_MULTIPLIER = 1
DEMOTION_RUNS_MULTIPLIER = 1

class Tier(IntEnum):
    IRON = 0
    BRONZE = 1
    SILVER = 2
    GOLD = 3
    PLATINUM = 4
    EMERALD = 5
    DIAMOND = 6
    MASTER = 7
    GRANDMASTER = 8
    CHALLENGER = 9

class Rank(float, Enum):
    IV = 0.1
    III = 0.2
    II = 0.3
    I = 0.4