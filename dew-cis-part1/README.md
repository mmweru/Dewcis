# File Archiving System — Dew CIS Solutions
## Ref: 60/2026

A complete file archiving system: CLI archiver → PostgreSQL → FastAPI → Dashboard.

---

## Prerequisites

- Docker Desktop installed and running
- `docker compose version` must show v2+

---

## Step 1 — Start all services

```bash
docker compose up -d
docker compose ps
```

All three services (postgres, pgadmin, testenv) must show as healthy/running before continuing.

---

## Step 2 — Run the archiver (first time)

```bash
docker compose exec testenv python3 archive_files.py --group developers
```

Expected output:

Run #1 started — group 'developers', 2 member(s).
MOVE  /home/alice/docs/report.pdf
MOVE  /home/alice/projects/web/index.html
...
Run #1 done: 16 moved, 0 skipped, 0 errors.

---

## Step 3 — Verify the database

Open pgAdmin at http://localhost:5050
Login: admin@dewcis.com / adminpass

Connect to server: host=postgres, port=5432, db=archivedb, user=archiveuser, pass=archivepass

Run this SQL query:
```sql
SELECT id, group_name, started_at, total_moved, total_skipped, status
FROM archive_runs
ORDER BY id;

SELECT run_id, source, destination, status
FROM archive_events
WHERE run_id = 1
LIMIT 10;
```

---

## Step 4 — Start the FastAPI service

The API container starts automatically with `docker compose up -d`.
It is available at http://localhost:8000

Test with curl:
```bash
curl http://localhost:8000/runs
curl http://localhost:8000/stats
curl http://localhost:8000/runs/1
curl "http://localhost:8000/runs/1/files?status=moved"
```

API documentation (auto-generated): http://localhost:8000/docs

---

## Step 5 — Open the dashboard

Navigate to: http://localhost:8000/

You will see the summary bar (total runs, files archived, skipped, errors) and a table
of all runs. Click any row to expand file events for that run.

---

## Step 6 — Run the archiver a second time

```bash
docker compose exec testenv python3 archive_files.py --group developers
```

Within 10 seconds, the dashboard auto-refreshes and shows a new row. The second run
shows 0 moved and 16 skipped (files already at destination).

Run a different group:
```bash
docker compose exec testenv python3 archive_files.py --group ops
```

---

## Step 7 — Build and install the Debian package

```bash
# Build the .deb package inside the testenv container
docker compose exec testenv dpkg-deb --build /workspace/debian-pkg /workspace/archive-files.deb

# Install it
docker compose exec testenv dpkg -i /workspace/archive-files.deb

# Verify it runs from PATH
docker compose exec testenv archive-files --group finance
```

---

## Running the full test suite (self-contained)

No local Python needed. Docker runs everything:

```bash
docker compose run test-runner
```

All 13 tests run automatically. Expected output:

test_archive.py::test_group_not_found              PASSED
test_archive.py::test_developers_happy_path        PASSED
test_archive.py::test_second_invocation_same_group PASSED
test_archive.py::test_ops_group_separate_run       PASSED
test_archive.py::test_progressive_db_writes        PASSED
test_archive.py::test_api_get_runs_returns_array   PASSED
test_archive.py::test_api_get_single_run_with_files PASSED
test_archive.py::test_api_run_not_found_returns_404 PASSED
test_archive.py::test_api_run_files_filter_by_status PASSED
test_archive.py::test_api_run_files_filter_404     PASSED
test_archive.py::test_api_stats_aggregates         PASSED
test_archive.py::test_api_docs_accessible          PASSED
test_archive.py::test_dashboard_accessible         PASSED
13 passed in X.XXs

To run locally (requires Python + packages installed):
```bash
pip install -r requirements.txt
pytest test_archive.py -v
```