from enum import Enum

PLATFORM_URL = "euw1.api.riotgames.com"
REGION_URL = "europe.api.riotgames.com"

# Fitness Multipliers
DEATH_PUSHUPS_MULTIPLIER = 1
CS_SITUPS_MULTIPLIER = 1
LOSS_PLANKS_MULTIPLIER = 1
DEMOTION_RUNS_MULTIPLIER = 1

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