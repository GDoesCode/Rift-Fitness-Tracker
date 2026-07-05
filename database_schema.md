## Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    SUMMONERS ||--o{ MATCH_PARTICIPANTS : participates_as
    SUMMONERS ||--o{ LIVE_GAMES : is_playing
    SUMMONERS ||--o{ PUNISHMENTS : receives
    SUMMONERS ||--o{ RANK_HISTORY : match_to_summoner_id
    MATCHES ||--o{ MATCH_PARTICIPANTS : contains
    MATCHES ||--o{ PUNISHMENTS : results_in
    MATCHES ||--o{ RANK_HISTORY : match_to_match_id

    SUMMONERS {
        bigint id PK
        text puuid UK
        text riot_id_game_name
        integer profile_icon_id
    }

    MATCHES {
        bigint id PK
        text riot_match_id UK
        bigint game_start_timestamp
        text game_mode
        integer game_duration
        integer map_id
        integer queue_id
    }

    MATCH_PARTICIPANTS {
        bigint id PK
        bigint match_id FK
        bigint summoner_id FK
        text champion
        integer kills
        integer deaths
        integer assists
        real kda
        text team
        text position
        text lane
        integer gold_earned
        integer total_damage_dealt
        integer minions_killed
    }

    LIVE_GAMES {
        bigint id PK
        bigint summoner_id FK
        timestamp timestamp
        integer kills
        integer deaths
        integer assists
    }

    PUNISHMENTS {
        bigint id PK
        bigint match_id FK
        bigint summoner_id FK
        timestamp timestamp
        integer deaths_pushups
        integer cs_situps
        integer loss_planks
        integer demotion_runs
    }

    RANK_HISTORY {
        bigint id PK
        bigint match_id FK
        bigint summoner_id FK
        text queue_type
        text tier
        text rank
        integer lp
        timestamp updated_at
    }