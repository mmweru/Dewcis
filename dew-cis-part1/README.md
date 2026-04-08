# Part 1 — File Archiving System
## Dew CIS Solutions | Ref: 60/2026 | Author: Maryann Mweru

---

## What This Is

A complete file archiving system built in Python. It moves files from the home directories of Linux group members to a configurable archive folder, records every event to a PostgreSQL database as it happens, exposes that data through a FastAPI REST API, and displays it on a live browser dashboard.

```
archive_files.py  →  PostgreSQL  →  FastAPI (main.py)  →  dashboard.html
     (CLI)            (archivedb)       :8000               :8000/
```

---

## Project Structure

```
dew-cis-part1/
├── docker-compose.yml      # All services: postgres, pgadmin, testenv, api, test-runner
├── setup.sh                # Bootstraps testenv: creates users, groups, and test files
├── archive_files.py        # The archiver CLI script
├── main.py                 # FastAPI REST API + dashboard server
├── dashboard.html          # Browser dashboard (served by FastAPI at /)
├── test_archive.py         # 13 pytest tests (archiver + API)
├── conftest.py             # Shared pytest fixtures and DB config
├── pytest.ini              # Pytest settings and marker definitions
├── requirements.txt        # Python dependencies
├── PLANNING.md             # Schema design, API mapping, robustness cases, test plan
├── README.md               # This file
└── debian-pkg/
    ├── DEBIAN/
    │   └── control         # Package metadata
    └── usr/local/bin/
        └── archive-files   # Executable wrapper installed to PATH
```

---

## Prerequisites

| Tool | Minimum version | Check |
|------|----------------|-------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |
| Python | 3.10+ | `python3 --version` (only needed to run tests locally) |

Docker must be **running** before any command below will work.

---

## Quick Start — Run the Whole System

```bash
# 1. Start all services (database, API, test environment)
docker compose up -d

# 2. Wait for everything to be healthy (about 30 seconds)
docker compose ps

# 3. Run the archiver for the first time
docker compose exec testenv python3 archive_files.py --group developers

# 4. Open the dashboard
#    http://localhost:8000/
```

That is the complete system running. Steps below go deeper.

---

## Step-by-Step Verification Guide

### Step 1 — Start Docker services

```bash
docker compose up -d
```

Wait until all services report the expected state:

```bash
docker compose ps
```

Expected output:

```
NAME                    STATUS
dew-cis-part1-postgres  Up (healthy)
dew-cis-part1-pgadmin   Up
dew-cis-part1-testenv   Up
dew-cis-part1-api       Up (healthy)
```

> If `api` takes longer than 60 seconds to become healthy, run `docker compose logs api` to check for errors.

---

### Step 2 — Run the archiver (first time)

```bash
docker compose exec testenv python3 archive_files.py --group developers
```

Expected output:

```
Run #1 started — group 'developers', 2 member(s).
  MOVE  /home/alice/documents/doc1.txt
  MOVE  /home/alice/documents/doc2.txt
  MOVE  /home/alice/documents/doc3.txt
  MOVE  /home/alice/documents/doc4.txt
  MOVE  /home/alice/projects/proj1.py
  MOVE  /home/alice/projects/proj2.py
  MOVE  /home/alice/projects/proj3.py
  MOVE  /home/alice/projects/proj4.py
  MOVE  /home/bob/documents/doc1.txt
  ...
Run #1 done: 16 moved, 0 skipped, 0 errors.
```

---

### Step 3 — Verify the database

Open pgAdmin at **http://localhost:5050**

| Field | Value |
|-------|-------|
| Email | admin@dewcis.com |
| Password | adminpass |

To connect to the database server in pgAdmin, right-click **Servers → Register → Server**:

| Field | Value |
|-------|-------|
| Host | postgres |
| Port | 5432 |
| Database | archivedb |
| Username | archiveuser |
| Password | archivepass |

Run these SQL queries in the Query Tool to confirm data was written:

```sql
-- See all runs
SELECT id, group_name, started_at, total_moved, total_skipped, status
FROM archive_runs
ORDER BY id;

-- See the file events for run #1
SELECT source, destination, status
FROM archive_events
WHERE run_id = 1
ORDER BY timestamp;

-- Count events by status
SELECT status, COUNT(*) AS total
FROM archive_events
GROUP BY status;
```

---

### Step 4 — Use the FastAPI service

The API starts automatically with `docker compose up -d` and is available at **http://localhost:8000**.

Test each endpoint with curl:

```bash
# List all runs
curl http://localhost:8000/runs

# Get a single run with its file events
curl http://localhost:8000/runs/1

# Get only the moved files from run #1
curl "http://localhost:8000/runs/1/files?status=moved"

# Get aggregate statistics
curl http://localhost:8000/stats

# Test 404 handling
curl http://localhost:8000/runs/99999
```

Auto-generated API documentation (Swagger UI): **http://localhost:8000/docs**

---

### Step 5 — Open the dashboard

Navigate to **http://localhost:8000/** in your browser.

You will see:
- A **summary bar** at the top: total runs, files archived, skipped, errors
- A **runs table** with one row per archiving run
- Clicking any row **expands file events** for that run (source, destination, status, reason, time)
- The dashboard **auto-refreshes every 10 seconds** without a full page reload

---

### Step 6 — Run the archiver a second time (same group)

```bash
docker compose exec testenv python3 archive_files.py --group developers
```

Expected output:

```
Run #2 started — group 'developers', 2 member(s).
  SKIP  /home/alice/documents/doc1.txt
  SKIP  /home/alice/documents/doc2.txt
  ...
Run #2 done: 0 moved, 16 skipped, 0 errors.
```

Within 10 seconds, the dashboard shows a new row — **Run #2** — with 0 moved and 16 skipped. The two runs are completely separate records in the database.

Run a different group to see independent run records:

```bash
docker compose exec testenv python3 archive_files.py --group ops
```

Check `GET /stats` again — `total_runs` is now 3, `busiest_group` will be `developers`.

---

### Step 7 — Build and install the Debian package

```bash
# Build the .deb inside the testenv container
docker compose exec testenv dpkg-deb --build /workspace/debian-pkg /workspace/archive-files.deb

# Install it
docker compose exec testenv dpkg -i /workspace/archive-files.deb

# Verify it is on PATH and runs correctly
docker compose exec testenv archive-files --group finance
```

The `archive-files` command is now available system-wide inside the container, exactly as it would be on a production Debian server.

---

## Running the Tests

### Option A — Self-contained via Docker (recommended)

No local Python installation required. Docker handles everything.

```bash
docker compose run test-runner
```

The `test-runner` service:
1. Installs all Python dependencies from `requirements.txt`
2. Waits for `postgres` to be healthy and `api` to be healthy
3. Runs all 13 tests in order
4. Prints a full result report

Expected output:

```
test_archive.py::test_group_not_found               PASSED
test_archive.py::test_developers_happy_path         PASSED
test_archive.py::test_second_invocation_same_group  PASSED
test_archive.py::test_ops_group_separate_run        PASSED
test_archive.py::test_progressive_db_writes         PASSED
test_archive.py::test_api_get_runs_returns_array    PASSED
test_archive.py::test_api_get_single_run_with_files PASSED
test_archive.py::test_api_run_not_found_returns_404 PASSED
test_archive.py::test_api_run_files_filter_by_status PASSED
test_archive.py::test_api_run_files_filter_404      PASSED
test_archive.py::test_api_stats_aggregates          PASSED
test_archive.py::test_api_docs_accessible           PASSED
test_archive.py::test_dashboard_accessible          PASSED

============ 13 passed in X.XXs ============
```

### Option B — Run locally (requires Python)

```bash
pip install -r requirements.txt
pytest test_archive.py -v
```

> When running locally, `docker compose up -d` must still be running so tests can reach the database and API.

---

## Test Coverage

Tests are split into two sections and run in a fixed order using `pytest-order`. Archiver tests run first because they populate the database that API tests then read from.

**Section A — Archiver tests (orders 1–5)**

| Test | Scenario | What is verified |
|------|----------|-----------------|
| `test_group_not_found` | `--group phantom` | Exit code ≠ 0, error mentions group name, no traceback, no DB record created |
| `test_developers_happy_path` | First run — developers | Exit 0, `total_moved > 0`, `status = completed`, event count matches `total_moved` |
| `test_second_invocation_same_group` | Second run — developers | Exit 0, 2 separate run records exist, latest has `total_skipped > 0`, `total_moved = 0` |
| `test_ops_group_separate_run` | First run — ops | Separate run record, `total_moved > 0`, independent of developers |
| `test_progressive_db_writes` | DB write timing | `started_at` ≤ first event `timestamp` — proves run opened before files processed |

**Section B — API tests (orders 6–13)**

| Test | Endpoint | What is verified |
|------|----------|-----------------|
| `test_api_get_runs_returns_array` | `GET /runs` | HTTP 200, JSON array, required fields present |
| `test_api_get_single_run_with_files` | `GET /runs/{id}` | HTTP 200, `files` array included, event fields present |
| `test_api_run_not_found_returns_404` | `GET /runs/99999` | HTTP 404, `detail` field in response |
| `test_api_run_files_filter_by_status` | `GET /runs/{id}/files?status=moved` | HTTP 200, all returned events have `status = moved` |
| `test_api_run_files_filter_404` | `GET /runs/99999/files` | HTTP 404 |
| `test_api_stats_aggregates` | `GET /stats` | HTTP 200, all aggregate fields present, `total_runs ≥ 3` |
| `test_api_docs_accessible` | `GET /docs` | HTTP 200, content-type is HTML |
| `test_dashboard_accessible` | `GET /` | HTTP 200, HTML response contains "Dashboard" |

---

## API Reference

All endpoints are also documented interactively at **http://localhost:8000/docs**.

### `GET /runs`
Returns all archiving runs, most recent first.

```json
[
  {
    "id": 1,
    "group_name": "developers",
    "started_at": "2026-04-08T10:00:00",
    "finished_at": "2026-04-08T10:00:03",
    "duration": 3,
    "total_moved": 16,
    "total_skipped": 0,
    "total_errors": 0,
    "status": "completed"
  }
]
```

### `GET /runs/{run_id}`
Returns a single run and all its file events. Returns `404` if the run does not exist.

```json
{
  "id": 1,
  "group_name": "developers",
  "status": "completed",
  "total_moved": 16,
  "files": [
    {
      "source": "/home/alice/documents/doc1.txt",
      "destination": "/tmp/archive/home/alice/documents/doc1.txt",
      "status": "moved",
      "reason": null,
      "timestamp": "2026-04-08T10:00:01"
    }
  ]
}
```

### `GET /runs/{run_id}/files`
Returns file events for a run. Accepts optional query parameter `?status=moved|skipped|error`. Returns `404` if the run does not exist.

### `GET /stats`
Returns aggregates across all runs.

```json
{
  "total_runs": 3,
  "total_files_archived": 24,
  "total_skipped": 16,
  "total_errors": 0,
  "most_recent_group": "ops",
  "busiest_group": "developers"
}
```

---

## Environment Variables

All services read their configuration from environment variables set in `docker-compose.yml`. You can override any of these in your shell before running Docker commands.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST` | `postgres` (Docker) / `localhost` (local) | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `archivedb` | Database name |
| `DB_USER` | `archiveuser` | Database user |
| `DB_PASS` | `archivepass` | Database password |
| `ARCHIVE_DIR` | `/tmp/archive` | Destination folder for archived files |
| `API_URL` | `http://api:8000` (Docker) / `http://localhost:8000` (local) | API base URL used by tests |

---

## Robustness Handling

The archiver handles all edge cases without crashing. Every scenario below exits cleanly or continues gracefully.

| Scenario | What happens |
|----------|-------------|
| `--group phantom` (group not found) | Prints `ERROR: Group 'phantom' does not exist`, exits with code 1, no traceback |
| Group has no members | Prints warning, exits with code 0 |
| Member has no passwd entry | Logs warning, skips that user, continues |
| Member's home directory missing | Logs warning, skips that user, continues |
| File permission denied | Logs `error` event in DB with reason, continues to next file |
| File already at destination | Logs `skipped` event, continues |
| Database connection fails | Prints error, exits with code 1 before touching any files |
| Run interrupted mid-way | Partial events already in DB row-by-row; run record stays `status = running` |

---

## Database Schema

Two tables. Schema is created automatically on first run — no manual setup in pgAdmin needed.

**`archive_runs`** — one row per invocation

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | Auto-incrementing |
| group_name | TEXT NOT NULL | Linux group archived |
| started_at | TIMESTAMP NOT NULL | Set at INSERT |
| finished_at | TIMESTAMP | NULL while running |
| status | TEXT | `running` → `completed` or `failed` |
| total_moved | INTEGER DEFAULT 0 | Updated on finish |
| total_skipped | INTEGER DEFAULT 0 | Updated on finish |
| total_errors | INTEGER DEFAULT 0 | Updated on finish |

**`archive_events`** — one row per file encountered

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | Auto-incrementing |
| run_id | INTEGER FK | References `archive_runs.id` |
| source | TEXT NOT NULL | Original file path |
| destination | TEXT | NULL if file errored |
| status | TEXT NOT NULL | `moved`, `skipped`, or `error` |
| reason | TEXT | NULL if moved; explains skip/error |
| timestamp | TIMESTAMP | Written immediately per file |

---

## Troubleshooting

**`docker compose up -d` fails with "port already in use"**
Another process is using port 5432, 5050, or 8000. Either stop that process or change the host port in `docker-compose.yml`.

**`api` service stays unhealthy**
Run `docker compose logs api` to see the error. The most common cause is a missing package in `requirements.txt` or a syntax error in `main.py`.

**Tests fail with "connection refused"**
Ensure `docker compose up -d` is running before executing tests. The API must be healthy (`docker compose ps`) before `test-runner` can reach it.

**`testenv` container keeps restarting**
Run `docker compose logs testenv`. A failure in `setup.sh` will cause this. Check that `setup.sh` is in the same folder as `docker-compose.yml`.

**pgAdmin shows "could not connect to server"**
Use `postgres` (not `localhost`) as the host when connecting from inside pgAdmin — pgAdmin runs in Docker and reaches the database via the internal Docker network name.
