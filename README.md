# Rift-Fitness-Tracker
Track KDA for punishment system

- Database PostgreSQL
-  Riot Developer Portal API

# Join Discord: https://discord.gg/YH7PfEc5Ku

## Overview
Enhanced KDA tracker with live game monitoring and punishment system.

## Tables

### `live_games`
Stores real-time K/D/A snapshots during active games (1 second polling).
- `live_id` - Auto-incrementing ID
- `game_id` - Active game ID
- `puuid` - Your summoner PUUID
- `timestamp` - When snapshot was taken (includes date)
- `kills`, `deaths`, `assists` - Your current stats

### `punishments`
Records post-game penalties based on performance.
- `punishment_id` - Auto-incrementing ID
- `match_id` - Link to finished match
- `puuid` - Your summoner PUUID
- `timestamp` - When game ended (includes date)
- `deaths_pushups` - Number of deaths (1 per death)
- `cs_situps` - 1 if CS < 10/min, else 0
- `loss_planks` - 1 minute plank if loss, else 0
- `demotion_runs` - 5km run if rank dropped, else 0
- `total_punishment_count` - Sum of all penalties

## Features

### 1. Live Game Tracking
**Mode: Option 2 or 3**

Polls the Spectator API every 1 second to capture your live K/D/A during games.
- Automatically detects when you're in an active game
- Records pre-game rank for comparison
- Stores all snapshots in `live_games` table
- Press Ctrl+C to stop (will keep running until game ends otherwise)

### 2. Punishment System
**Automatic after game finishes**

After every ranked game, calculates penalties:
- **Deaths → Press-ups**: 1 push-up per death
- **Low CS → Sit-ups**: 1 sit-up if CS < 10/min
- **Loss → Plank**: 1 minute plank if you lost the game
- **Demotion → Runs**: 5km run if you got demoted

All stored in `punishments` table with timestamp (includes date).

### 3. Three Operating Modes

1. **Track Past 20 Games** (Option 1)
   - Fetches last 20 games from Riot API
   - Stores in matches/participants/summoners tables
   - Can calculate punishments for those games

2. **Track Live Game Only** (Option 2)
   - Monitors active game in real-time
   - Polls every 1 second
   - Stores K/D/A snapshots
   - Stops when game ends

3. **Both Simultaneously** (Option 3)
   - Uses threading (same application)
   - Live tracker runs in background thread
   - Main thread fetches past 20 games
   - Both complete independently

### Timestamp Format
All new tables use PostgreSQL `TIMESTAMP` type, displaying dates like:
`2026-05-19 14:30:45` (instead of epoch milliseconds)

## Usage

```bash
python kda_tracker.py
```

Enter summoner name (e.g., `summonername#taghere`), then choose mode:

```
Choose mode:
1. Track past 20 games
2. Track live game
3. Both (live in background)
```

### Example Output

**Live Game:**
```
[LIVE] Checking for active game...
[LIVE] Game started! Tracking... (Game ID: NA1_12345678901)
[LIVE] Pre-game rank: [{'tier': 'DIAMOND', 'rank': 'I', 'summonerName': 'JustG', ...}]
[LIVE] K/D/A: 3/1/5
[LIVE] K/D/A: 4/1/7
[LIVE] K/D/A: 5/2/9
[LIVE] Game ended!
```

**Punishments:**
```
[PUNISHMENTS] Press-ups: 2, Sit-ups: 0, Planks: 0min, Runs: 0km
```

Rift Fitness Tracker isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
