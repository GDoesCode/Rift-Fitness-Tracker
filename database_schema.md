# Database Schema Documentation

## Overview
The database now uses a normalized relational structure with three main tables: `summoners`, `matches`, and `participants`.

## Tables

### summoners
Stores unique summoner identities. This is the source of truth for player information.

**Columns:**
- `puuid` (TEXT, PRIMARY KEY) - Universally unique identifier for a summoner
- `riot_id_game_name` (TEXT) - Summoner ID from Riot API
- `profile_icon_id` (INTEGER) - Profile icon identifier

**Example:**
```
puuid: "abc123def456"
summoner_name: "JustG#01G"
riot_id: "summoner_id_123"
profile_icon_id: 6394
```

### matches
Stores core match/game data. One row per match.

**Columns:**
- `match_id` (TEXT, PRIMARY KEY) - Unique match identifier (e.g., "EUW1_1234567890")
- `timestamp` (BIGINT) - Game start time (Unix timestamp in milliseconds)
- `game_mode` (TEXT) - Game mode (CLASSIC, ARAM, etc.)
- `game_duration` (INTEGER) - Game duration in seconds
- `map_id` (INTEGER) - Map identifier
- `queue_id` (INTEGER) - Queue type identifier

**Example:**
```
match_id: "EUW1_1234567890"
timestamp: 1705000000000
game_mode: "CLASSIC"
game_duration: 1847
map_id: 11
queue_id: 420
```

### participants
Stores individual player performance data. Each match has 10 participants (5v5).

**Columns:**
- `participant_id` (SERIAL, PRIMARY KEY) - Auto-incrementing unique ID
- `match_id` (TEXT, FOREIGN KEY) - Links to matches table
- `puuid` (TEXT, FOREIGN KEY) - Links to summoners table
- `champion` (TEXT) - Champion played (e.g., "Ahri")
- `kills` (INTEGER) - Number of kills
- `deaths` (INTEGER) - Number of deaths
- `assists` (INTEGER) - Number of assists
- `kda` (REAL) - Calculated K/D/A ratio
- `team` (TEXT) - Team color (BLUE or RED)
- `position` (TEXT) - Position played (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
- `lane` (TEXT) - Lane assignment (TOP, MID, BOT, NONE)
- `gold_earned` (INTEGER) - Total gold earned
- `total_damage_dealt` (INTEGER) - Total damage to champions

**Example:**
```
participant_id: 1
match_id: "EUW1_1234567890"
puuid: "abc123def456"
champion: "Ahri"
kills: 5
deaths: 2
assists: 12
kda: 8.5
team: "BLUE"
position: "MIDDLE"
lane: "MID"
gold_earned: 12500
total_damage_dealt: 18900
```

## Relationships

```
summoners (1) ─────────────── (N) participants ─────────────── (N) matches
                                                              (1)
```

- One summoner can have many participants (different matches)
- One match has many participants (up to 10 players)
- A participant is the join of a summoner + match + performance stats

## Query Examples

### Find a summoner's matches with KDA
```sql
SELECT m.match_id, m.timestamp, p.champion, p.kills, p.deaths, p.assists, p.kda
FROM participants p
JOIN matches m ON p.match_id = m.match_id
JOIN summoners s ON p.puuid = s.puuid
WHERE s.summoner_name = 'JustG#01G'
ORDER BY m.timestamp DESC;
```

### Find opponents in a specific match
```sql
SELECT p.champion, p.kills, p.deaths, p.assists, p.team
FROM participants p
WHERE p.match_id = 'EUW1_1234567890'
ORDER BY p.team;
```

### Find average KDA by champion
```sql
SELECT p.champion, AVG(p.kda) as avg_kda, COUNT(*) as games
FROM participants p
JOIN summoners s ON p.puuid = s.puuid
WHERE s.summoner_name = 'JustG#01G'
GROUP BY p.champion
ORDER BY avg_kda DESC;
```

### Find recent match performance
```sql
SELECT m.match_id, m.timestamp, p.champion, p.kills, p.deaths, p.assists, p.position
FROM participants p
JOIN matches m ON p.match_id = m.match_id
WHERE p.puuid = (SELECT puuid FROM summoners WHERE summoner_name = 'JustG#01G')
ORDER BY m.timestamp DESC
LIMIT 10;
```

## Benefits

1. **Data Integrity** - Foreign key constraints ensure referential consistency
2. **Elimination of Duplication** - Summoner data stored once, referenced everywhere
3. **Scalability** - Easy to add more participants or matches
4. **Query Flexibility** - Can analyze team comps, opponents, trends, etc.
5. **Performance** - Indexed primary keys for fast lookups
