import psycopg2 as psql
from config import DATABASE_URL, DEATHS_PUSHUPS_MULTIPLIER, CS_SITUPS_MULTIPLIER, LOSS_PLANKS_MULTIPLIER, DEMOTION_RUNS_MULTIPLIER, Tier, Rank

class DatabaseManager:
    def __init__(self):
        self.url = DATABASE_URL

    def get_connection(self):
        return psql.connect(self.url)

    def init_db(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS summoners(
                    puuid TEXT PRIMARY KEY,
                    riot_id_game_name TEXT,
                    profile_icon_id INTEGER
                )""")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS matches(
                    match_id TEXT PRIMARY KEY,
                    timestamp BIGINT,
                    game_mode TEXT,
                    game_duration INTEGER,
                    map_id INTEGER,
                    queue_id INTEGER
                )""")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS participants(
                    participant_id SERIAL PRIMARY KEY,
                    match_id TEXT NOT NULL REFERENCES matches(match_id),
                    puuid TEXT NOT NULL REFERENCES summoners(puuid),
                    champion TEXT,
                    kills INTEGER,
                    deaths INTEGER,
                    assists INTEGER,
                    kda REAL,
                    team TEXT,
                    position TEXT,
                    lane TEXT,
                    gold_earned INTEGER,
                    total_damage_dealt INTEGER,
                    minions_killed INTEGER
                )""")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS live_games(
                    live_id SERIAL PRIMARY KEY,
                    game_id TEXT,
                    puuid TEXT NOT NULL REFERENCES summoners(puuid),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    kills INTEGER,
                    deaths INTEGER,
                    assists INTEGER
                )""")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS punishments(
                    punishment_id SERIAL PRIMARY KEY,
                    match_id TEXT NOT NULL REFERENCES matches(match_id),
                    puuid TEXT NOT NULL REFERENCES summoners(puuid),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deaths_pushups INTEGER DEFAULT 0,
                    cs_situps INTEGER DEFAULT 0,
                    loss_planks INTEGER DEFAULT 0,
                    demotion_runs INTEGER DEFAULT 0
                )""")
                conn.commit()

    def match_exists(self, match_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM matches WHERE match_id = %s", (match_id,))
                return cur.fetchone() is not None

    def upsert_summoner(self, conn, puuid, game_name, icon_id):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO summoners(puuid, riot_id_game_name, profile_icon_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (puuid) DO UPDATE SET
                    riot_id_game_name = EXCLUDED.riot_id_game_name,
                    profile_icon_id = EXCLUDED.profile_icon_id
            """, (puuid, game_name, icon_id))

    def store_match(self, conn, m_id, ts, mode, duration, map_id, q_id):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO matches(match_id, timestamp, game_mode, game_duration, map_id, queue_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (match_id) DO NOTHING
            """, (m_id, ts, mode, duration, map_id, q_id))

    def store_participant(self, conn, m_id, puuid, champ, k, d, a, kda, team, pos, lane, gold, dmg, minions):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO participants(match_id, puuid, champion, kills, deaths, assists, kda, team, position, lane, gold_earned, total_damage_dealt, minions_killed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (m_id, puuid, champ, k, d, a, kda, team, pos, lane, gold, dmg, minions))

    def store_live_snapshot(self, game_id, puuid, k, d, a):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO live_games(game_id, puuid, kills, deaths, assists)
                    VALUES (%s, %s, %s, %s, %s)
                """, (game_id, puuid, k, d, a))
                conn.commit()

    def _rank_down(self, rank_before, rank_after):
        val1 = Tier[rank_before["Tier"]].value + Rank[rank_before["Rank"]].value
        val2 = Tier[rank_after["Tier"]].value + Rank[rank_after["Rank"]].value
        return val1 > val2

    def calculate_and_store_punishments(self, conn, match_id, puuid, participant_data, match_duration, was_win, rank_before, rank_after):
        deaths = participant_data.get("deaths", 0)
        minions = participant_data.get("totalMinionsKilled", 0)
        cs_per_min = int(minions // max(1, match_duration / 60))
        
        deaths_pushups = deaths * DEATHS_PUSHUPS_MULTIPLIER
        cs_situps = max(0, (10 - cs_per_min)) * CS_SITUPS_MULTIPLIER
        loss_planks = LOSS_PLANKS_MULTIPLIER if not was_win else 0
        demotion_runs = 0
        
        if rank_before and rank_after:
            rb_entry = rank_before[1] if isinstance(rank_before, list) and len(rank_before) > 1 else None
            ra_entry = rank_after[1] if isinstance(rank_after, list) and len(rank_after) > 1 else None
            
            if rb_entry and ra_entry:
                rb_dict = {"Tier": rb_entry.get("tier", "UNKNOWN"), "Rank": rb_entry.get("rank", "")}
                ra_dict = {"Tier": ra_entry.get("tier", "UNKNOWN"), "Rank": ra_entry.get("rank", "")}
                if self._rank_down(rb_dict, ra_dict):
                    demotion_runs = 1 * DEMOTION_RUNS_MULTIPLIER

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO punishments(match_id, puuid, deaths_pushups, cs_situps, loss_planks, demotion_runs)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (match_id, puuid, deaths_pushups, cs_situps, loss_planks, demotion_runs))
        
        return {
            "deaths_pushups": deaths_pushups,
            "cs_situps": cs_situps,
            "loss_planks": loss_planks,
            "demotion_runs": demotion_runs
        }