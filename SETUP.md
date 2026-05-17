# PostgreSQL Setup Checklist

## 1. Install PostgreSQL Server
- [/] Download from https://www.postgresql.org/download/windows/
- [/] Install with port 5432 and set postgres password
- [/] Add PostgreSQL to PATH (checked during install)

## 2. Create Database & User
Open Command Prompt and run:
```
psql -U postgres
```

Then in psql, run:
```sql
CREATE DATABASE riot_tracker;
CREATE USER riot_user WITH PASSWORD 'your_password_here';
GRANT ALL PRIVILEGES ON DATABASE riot_tracker TO riot_user;
\q
```

Replace `your_password_here` with a real password!

## 3. Install Python Dependencies
```bash
pip install psycopg2-binary python-dotenv requests
```

## 4. Create .env File
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Then edit `.env` and fill in:
- `DATABASE_URL`: your PostgreSQL connection string
- `RIOT_API_KEY`: your Riot API key

Example `.env`:
```
DATABASE_URL=postgresql://riot_user:your_password_here@localhost:5432/riot_tracker
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## 5. Migrate Existing Data (if you have kda.db)
```bash
python migrate_to_postgres.py
```

This will copy all data from SQLite to PostgreSQL.

## 6. Test the New Setup
```bash
python kda_tracker.py
```

If it works, you can delete `kda.db` (keep a backup just in case).

## Troubleshooting

**Error: "psycopg2: connection refused"**
- PostgreSQL server not running
- Windows: Use Services or pgAdmin to start PostgreSQL

**Error: "password authentication failed"**
- Wrong username/password in .env
- Verify with: `psql -U riot_user -h localhost -d riot_tracker`

**Error: "database riot_tracker does not exist"**
- Database creation failed
- Run the SQL commands again in psql

**Error: "RIOT_API_KEY not set"**
- Make sure .env file is created and filled in
- Try: `echo %RIOT_API_KEY%` in Command Prompt to verify
