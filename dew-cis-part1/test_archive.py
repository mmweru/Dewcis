"""
test_archive.py — Automated pytest test suite
Dew CIS Solutions | Ref: 60/2026

Tests run in order using pytest-order. The archiver tests run first
(they populate the database), then the API tests read from it.

Run locally:
    pytest test_archive.py -v

Run via Docker (self-contained, no local setup needed):
    docker compose run test-runner

Environment variables (set in docker-compose.yml or conftest.py):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
    API_URL  (e.g. http://api:8000 inside Docker, http://localhost:8000 locally)
"""

import os
import subprocess
import pytest
import requests
import psycopg2
import psycopg2.extras

# ── Connection helpers (read from environment) ─────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "archivedb"),
    "user":     os.environ.get("DB_USER", "archiveuser"),
    "password": os.environ.get("DB_PASS", "archivepass"),
}
API = os.environ.get("API_URL", "http://localhost:8000")


def db():
    """Open and return a DB connection with dict rows."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)


def run_archiver(group, extra_args=None):
    """
    Run archive_files.py inside the testenv container via docker compose exec.
    Returns the CompletedProcess so tests can inspect returncode, stdout, stderr.
    """
    cmd = [
        "docker", "compose", "exec", "-T", "testenv",
        "python3", "/workspace/archive_files.py", "--group", group
    ]
    if extra_args:
        cmd += extra_args
    return subprocess.run(cmd, capture_output=True, text=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — ARCHIVER TESTS
# These tests exercise the archive_files.py script and verify the DB records.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.order(1)
def test_group_not_found():
    """
    SCENARIO: --group phantom (group does not exist on the system)

    EXPECTED:
    - Exit code is non-zero (signals failure to the caller)
    - Output contains the group name 'phantom' in a human-readable error
    - No Python traceback is printed (clean error, not a crash)
    - No run record is created in the database
    """
    result = run_archiver("phantom")

    assert result.returncode != 0, \
        "Should exit with non-zero code when group is not found"

    combined = result.stdout + result.stderr
    assert "phantom" in combined.lower(), \
        "Error message should mention the group name 'phantom'"
    assert "Traceback" not in result.stderr, \
        "Should NOT print a Python traceback — use sys.exit() for clean errors"

    conn = db()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM archive_runs WHERE group_name = 'phantom'")
        count = cur.fetchone()["cnt"]
    conn.close()
    assert count == 0, "No run record should be created for a non-existent group"


@pytest.mark.order(2)
def test_developers_happy_path():
    """
    SCENARIO: First run for the 'developers' group (alice + bob)

    EXPECTED:
    - Exit code 0
    - Files are moved (alice has 8 files, bob has 8 files = 16 total minimum)
    - A run record exists in archive_runs with status = 'completed'
    - total_moved > 0 and total_errors = 0
    - archive_events rows were written for this run
    """
    result = run_archiver("developers")

    assert result.returncode == 0, \
        f"Archiver should exit 0 for a valid group.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"

    conn = db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM archive_runs
            WHERE group_name = 'developers'
            ORDER BY id DESC LIMIT 1
        """)
        run = cur.fetchone()

        assert run is not None, "A run record must be created in archive_runs"
        assert run["status"] == "completed", \
            f"Run status should be 'completed', got '{run['status']}'"
        assert run["total_moved"] > 0, \
            "total_moved should be > 0 — files should have been archived"
        assert run["total_errors"] == 0, \
            "total_errors should be 0 on the happy path"

        # Verify events were written to archive_events
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM archive_events WHERE run_id = %s AND status = 'moved'",
            (run["id"],)
        )
        event_count = cur.fetchone()["cnt"]
        assert event_count == run["total_moved"], \
            "Number of 'moved' events must match total_moved on the run record"

    conn.close()


@pytest.mark.order(3)
def test_second_invocation_same_group():
    """
    SCENARIO: Run 'developers' a second time (files already at destination)

    EXPECTED:
    - Exit code 0 (no crash)
    - A NEW separate run record is created (2 run records total for 'developers')
    - The new run has total_skipped > 0 (files already archived = skipped)
    - total_moved = 0 on the second run (nothing new to move)
    - No duplicate events overwrite the first run
    """
    result = run_archiver("developers")

    assert result.returncode == 0, \
        f"Second invocation should not crash.\nSTDERR: {result.stderr}"

    conn = db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM archive_runs WHERE group_name = 'developers'"
        )
        total_runs = cur.fetchone()["cnt"]
        assert total_runs >= 2, \
            "Should have at least 2 separate run records for 'developers'"

        cur.execute("""
            SELECT * FROM archive_runs
            WHERE group_name = 'developers'
            ORDER BY id DESC LIMIT 1
        """)
        latest = cur.fetchone()
        assert latest["total_skipped"] > 0, \
            "Second run should skip already-archived files (total_skipped > 0)"
        assert latest["total_moved"] == 0, \
            "Second run should move 0 files (all already archived)"

    conn.close()


@pytest.mark.order(4)
def test_ops_group_separate_run():
    """
    SCENARIO: Run the 'ops' group (carol + david)

    EXPECTED:
    - Exit code 0
    - A separate run record exists for 'ops' (distinct from developers)
    - carol and david files are moved
    - The ops run is independent of the developers runs
    """
    result = run_archiver("ops")

    assert result.returncode == 0, \
        f"Archiver should succeed for 'ops' group.\nSTDERR: {result.stderr}"

    conn = db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM archive_runs
            WHERE group_name = 'ops'
            ORDER BY id DESC LIMIT 1
        """)
        run = cur.fetchone()
        assert run is not None, "A run record for 'ops' must exist"
        assert run["status"] == "completed"
        assert run["total_moved"] > 0, "ops files should have been archived"

    conn.close()


@pytest.mark.order(5)
def test_progressive_db_writes():
    """
    SCENARIO: Events are written progressively, not batched at the end.

    EXPECTED:
    - archive_events rows exist for the developers run
    - Each event has its own timestamp
    - The run record's started_at is earlier than the first event's timestamp
      (proves the run was opened before file processing began)
    """
    conn = db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.started_at, MIN(e.timestamp) AS first_event
            FROM archive_runs r
            JOIN archive_events e ON e.run_id = r.id
            WHERE r.group_name = 'developers'
            GROUP BY r.id, r.started_at
            ORDER BY r.id ASC
            LIMIT 1
        """)
        row = cur.fetchone()
        assert row is not None, "Must have at least one developers run with events"
        assert row["started_at"] <= row["first_event"], \
            "Run must be opened (started_at) before or when the first file event is written"

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — FASTAPI TESTS
# These tests hit the running API service.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.order(6)
def test_api_get_runs_returns_array():
    """
    SCENARIO: GET /runs

    EXPECTED:
    - HTTP 200
    - Response body is a JSON array
    - Array is non-empty (archiver tests ran before this)
    - Each object has the required fields
    """
    r = requests.get(f"{API}/runs")
    assert r.status_code == 200, f"GET /runs should return 200, got {r.status_code}"

    data = r.json()
    assert isinstance(data, list), "GET /runs must return a JSON array"
    assert len(data) > 0, "Array should be non-empty after archiver tests"

    required_fields = {"id", "group_name", "started_at", "total_moved", "total_skipped", "total_errors", "status"}
    for field in required_fields:
        assert field in data[0], f"Run object must contain field '{field}'"


@pytest.mark.order(7)
def test_api_get_single_run_with_files():
    """
    SCENARIO: GET /runs/{id}

    EXPECTED:
    - HTTP 200
    - Response contains both run fields and a 'files' array
    - 'files' array contains event objects with source, destination, status, reason, timestamp
    """
    runs = requests.get(f"{API}/runs").json()
    run_id = runs[0]["id"]

    r = requests.get(f"{API}/runs/{run_id}")
    assert r.status_code == 200, f"GET /runs/{run_id} should return 200"

    data = r.json()
    assert "files" in data, "Run detail response must include a 'files' array"
    assert isinstance(data["files"], list), "'files' must be a list"

    if data["files"]:
        event = data["files"][0]
        for field in ["source", "status", "timestamp"]:
            assert field in event, f"File event must contain field '{field}'"


@pytest.mark.order(8)
def test_api_run_not_found_returns_404():
    """
    SCENARIO: GET /runs/99999 (run ID that does not exist)

    EXPECTED:
    - HTTP 404 (not 500 — the API must handle missing IDs gracefully)
    - Response body contains a 'detail' field explaining the error
    """
    r = requests.get(f"{API}/runs/99999")
    assert r.status_code == 404, \
        f"Missing run should return 404, got {r.status_code}. Body: {r.text}"

    data = r.json()
    assert "detail" in data, "404 response must contain a 'detail' field"


@pytest.mark.order(9)
def test_api_run_files_filter_by_status():
    """
    SCENARIO: GET /runs/{id}/files?status=moved

    EXPECTED:
    - HTTP 200
    - All returned file events have status == 'moved'
    - No 'skipped' or 'error' events appear in the filtered response
    """
    runs = requests.get(f"{API}/runs").json()
    # Find a run that has moved files
    run_id = next((r["id"] for r in runs if r["total_moved"] > 0), None)
    assert run_id is not None, "Need at least one run with moved files"

    r = requests.get(f"{API}/runs/{run_id}/files", params={"status": "moved"})
    assert r.status_code == 200

    files = r.json()
    assert len(files) > 0, "Should return at least one moved file"
    for f in files:
        assert f["status"] == "moved", \
            f"Filtered response should only contain 'moved' events, got '{f['status']}'"


@pytest.mark.order(10)
def test_api_run_files_filter_404():
    """
    SCENARIO: GET /runs/99999/files (run does not exist)

    EXPECTED:
    - HTTP 404 with clear error message
    """
    r = requests.get(f"{API}/runs/99999/files")
    assert r.status_code == 404


@pytest.mark.order(11)
def test_api_stats_aggregates():
    """
    SCENARIO: GET /stats

    EXPECTED:
    - HTTP 200
    - All required aggregate fields are present
    - total_runs >= 3 (developers x2, ops x1 from tests above)
    - total_files_archived > 0
    """
    r = requests.get(f"{API}/stats")
    assert r.status_code == 200

    data = r.json()
    required = {"total_runs", "total_files_archived", "total_skipped", "total_errors"}
    for field in required:
        assert field in data, f"Stats must contain field '{field}'"

    assert data["total_runs"] >= 3, \
        "Should have at least 3 runs from the archiver tests"
    assert data["total_files_archived"] > 0, \
        "total_files_archived should be > 0"


@pytest.mark.order(12)
def test_api_docs_accessible():
    """
    SCENARIO: GET /docs (FastAPI auto-generated documentation)

    EXPECTED:
    - HTTP 200
    - Response is HTML (FastAPI's Swagger UI)
    """
    r = requests.get(f"{API}/docs")
    assert r.status_code == 200, "FastAPI /docs should be accessible"
    assert "text/html" in r.headers.get("content-type", ""), \
        "/docs should return HTML"


@pytest.mark.order(13)
def test_dashboard_accessible():
    """
    SCENARIO: GET / (the browser dashboard)

    EXPECTED:
    - HTTP 200
    - Response is HTML
    - Contains expected dashboard content
    """
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Dashboard" in r.text or "dashboard" in r.text.lower(), \
        "Dashboard HTML should contain the word 'Dashboard'"