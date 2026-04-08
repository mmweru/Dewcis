# Planning Document — File Archiving System
## Ref: 60/2026 | Author: [Maryann Mweru]

---

## Section 1A — Database Schema Design

### Why two tables?

The system needs to track two separate things:
- The overall archiving run (which group, when, how many files total)
- Each individual file event within that run (where it came from, where it went, what happened)

Separating these into two tables means: a run record exists the moment archiving starts (before any files are processed), and each file event is written immediately as it happens — so a crash midway leaves partial records visible, not silence.

---

### Table 1: archive_runs

Stores one row per invocation of the archiver.

| Column        | Type             | Constraints         | Purpose                                      |
|---------------|------------------|---------------------|----------------------------------------------|
| id            | SERIAL           | PRIMARY KEY         | Unique run identifier                        |
| group_name    | TEXT             | NOT NULL            | Linux group that was archived                |
| started_at    | TIMESTAMP        | NOT NULL, DEFAULT NOW() | When this run began                      |
| finished_at   | TIMESTAMP        | NULL allowed        | When this run ended (NULL = still running)   |
| status        | TEXT             | NOT NULL DEFAULT 'running' | 'running', 'completed', or 'failed'  |
| total_moved   | INTEGER          | NOT NULL DEFAULT 0  | Count of files successfully moved            |
| total_skipped | INTEGER          | NOT NULL DEFAULT 0  | Count of files skipped (already archived)    |
| total_errors  | INTEGER          | NOT NULL DEFAULT 0  | Count of files that failed                   |

Design decisions:
- `finished_at` is nullable so the row exists before archiving completes
- `status = 'running'` is set on INSERT and updated to 'completed' or 'failed' on exit
- Running the same group twice creates two rows — each run is fully independent and distinguishable by `id` and `started_at`

---

### Table 2: archive_events

Stores one row per file encountered during a run.

| Column      | Type      | Constraints                   | Purpose                                       |
|-------------|-----------|-------------------------------|-----------------------------------------------|
| id          | SERIAL    | PRIMARY KEY                   | Unique event identifier                       |
| run_id      | INTEGER   | NOT NULL, FOREIGN KEY → runs  | Links this event to its parent run            |
| source      | TEXT      | NOT NULL                      | Original file path                            |
| destination | TEXT      | NULL allowed                  | Where the file was moved to (NULL if error)   |
| status      | TEXT      | NOT NULL                      | 'moved', 'skipped', or 'error'                |
| reason      | TEXT      | NULL allowed                  | Explanation for skipped/error (NULL if moved) |
| timestamp   | TIMESTAMP | NOT NULL, DEFAULT NOW()       | Exact moment this event was recorded          |

Design decisions:
- `destination` is nullable because if a file errors, there is no destination
- `reason` explains why: "already at destination", "permission denied: [details]"
- Each event is committed immediately (not batched) — so partial runs are always visible in the database
- The FOREIGN KEY on `run_id` ensures no orphan events can exist without a parent run

---

### Entity Relationship

archive_runs          archive_events
────────────          ──────────────
id  ──────────────── run_id  (many events per run)
group_name            source
started_at            destination
finished_at           status
status                reason
total_moved           timestamp
total_skipped
total_errors

---

## Section 1B — API Endpoint Design

Before building the API, each endpoint is mapped to its SQL logic.

### GET /runs
Returns all archiving runs, most recent first.

```sql
SELECT
    id, group_name, started_at, finished_at,
    EXTRACT(EPOCH FROM (finished_at - started_at))::int AS duration,
    total_moved, total_skipped, total_errors, status
FROM archive_runs
ORDER BY started_at DESC;
```

Returns: Array of run objects. Duration is in seconds. NULL if run is still in progress.

---

### GET /runs/{run_id}
Returns a single run plus every file event for that run.

```sql
-- Step 1: Get the run
SELECT id, group_name, started_at, finished_at, ... FROM archive_runs WHERE id = $1;

-- Step 2: Get all file events for that run
SELECT source, destination, status, reason, timestamp
FROM archive_events
WHERE run_id = $1
ORDER BY timestamp;
```

Returns: Run object with an embedded `files` array.
Returns HTTP 404 if run_id does not exist — not a 500 error.

---

### GET /runs/{run_id}/files
Returns file events for a run, optionally filtered by status.

```sql
-- Without filter:
SELECT source, destination, status, reason, timestamp
FROM archive_events WHERE run_id = $1 ORDER BY timestamp;

-- With ?status=moved (or skipped, or error):
SELECT source, destination, status, reason, timestamp
FROM archive_events WHERE run_id = $1 AND status = $2 ORDER BY timestamp;
```

Returns HTTP 404 if run_id does not exist.

---

### GET /stats
Returns aggregate statistics across all runs.

```sql
SELECT
    COUNT(*)                             AS total_runs,
    COALESCE(SUM(total_moved),   0)      AS total_files_archived,
    COALESCE(SUM(total_skipped), 0)      AS total_skipped,
    COALESCE(SUM(total_errors),  0)      AS total_errors,
    (SELECT group_name FROM archive_runs ORDER BY started_at DESC LIMIT 1)
                                         AS most_recent_group,
    (SELECT group_name FROM archive_runs
     GROUP BY group_name ORDER BY SUM(total_moved) DESC LIMIT 1)
                                         AS busiest_group
FROM archive_runs;
```

Uses COALESCE to return 0 instead of NULL when no runs exist yet.

---

## Section 1C — Robustness Cases

Each edge case is handled explicitly before any file processing begins.

| Scenario                        | Detection method                         | Handling                                                        |
|---------------------------------|------------------------------------------|-----------------------------------------------------------------|
| Group does not exist            | `grp.getgrnam()` raises `KeyError`       | Print clear error to stderr, exit with code 1, no traceback     |
| Group exists but has no members | `group.gr_mem` is empty list             | Print warning, exit cleanly with code 0                         |
| User has no passwd entry        | `pwd.getpwnam()` raises `KeyError`       | Log warning to stdout, skip that user, continue                 |
| Home directory does not exist   | `os.path.isdir(home_dir)` returns False  | Log warning, skip that user, continue                           |
| File permission denied          | `shutil.move()` raises `PermissionError` | Log as 'error' event in DB with reason, continue to next file   |
| File already at destination     | `os.path.exists(dst_path)` is True       | Log as 'skipped' event with reason "already at destination"     |
| Database connection fails       | `psycopg2.connect()` raises exception    | Print error to stderr, exit with code 1 before any file work    |
| Run interrupted mid-way         | (partial execution)                      | Partial events already committed row-by-row; run stays 'running'|

---

## Section 1D — Test Plan

Tests are written in pytest. Each scenario maps directly to a requirement in the brief.

| Test name                        | What it checks                                                         | Pass condition                                           |
|----------------------------------|------------------------------------------------------------------------|----------------------------------------------------------|
| test_group_not_found             | `--group phantom` exits non-zero, prints error, no traceback           | returncode != 0, "phantom" in output, no "Traceback"     |
| test_developers_happy_path       | developers group moves alice+bob files, creates DB run record          | returncode 0, total_moved > 0, status = 'completed'      |
| test_second_invocation_skips     | running developers again skips all files, creates separate run record  | 2+ run records, latest has total_skipped > 0             |
| test_ops_group                   | ops group creates its own separate run record                          | run record with group_name = 'ops' exists                |
| test_api_get_runs                | GET /runs returns array                                                | status 200, response is list                             |
| test_api_get_run_detail          | GET /runs/{id} includes files array                                    | status 200, "files" key present                          |
| test_api_run_not_found           | GET /runs/99999 returns 404                                            | status 404                                               |
| test_api_stats                   | GET /stats returns aggregate fields                                    | status 200, total_runs > 0                               |
| test_api_filter_by_status        | GET /runs/{id}/files?status=moved returns only moved files             | all returned files have status == 'moved'                |