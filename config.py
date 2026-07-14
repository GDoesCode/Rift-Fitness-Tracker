from enum import Enum

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