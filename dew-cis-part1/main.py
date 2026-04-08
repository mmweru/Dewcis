"""
main.py — FastAPI REST API
Dew CIS Solutions | Ref: 60/2026

Reads from PostgreSQL and serves:
  GET /          → dashboard HTML
  GET /runs      → all archive runs
  GET /runs/{id} → single run + file events
  GET /runs/{id}/files → file events (filterable)
  GET /stats     → aggregate statistics
  GET /docs      → FastAPI auto-generated docs (built in)
"""

import os
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="File Archive API",
    description="Dew CIS Solutions — Ref 60/2026",
    version="1.0.0",
)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "archivedb"),
    "user":     os.environ.get("DB_USER", "archiveuser"),
    "password": os.environ.get("DB_PASS", "archivepass"),
}


def get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)


def ensure_schema():
    """Create archive_runs and archive_events tables if they do not exist."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS archive_runs (
                id            SERIAL      PRIMARY KEY,
                group_name    TEXT        NOT NULL,
                started_at    TIMESTAMP   NOT NULL DEFAULT NOW(),
                finished_at   TIMESTAMP,
                status        TEXT        NOT NULL DEFAULT 'running',
                total_moved   INTEGER     NOT NULL DEFAULT 0,
                total_skipped INTEGER     NOT NULL DEFAULT 0,
                total_errors  INTEGER     NOT NULL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS archive_events (
                id          SERIAL      PRIMARY KEY,
                run_id      INTEGER     NOT NULL REFERENCES archive_runs(id),
                source      TEXT        NOT NULL,
                destination TEXT,
                status      TEXT        NOT NULL,
                reason      TEXT,
                timestamp   TIMESTAMP   NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup():
    """Ensure DB schema exists before the first request is served."""
    ensure_schema()


@app.get("/runs", summary="List all archive runs")
def list_runs():
    """Return all runs, most recent first."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, group_name, started_at, finished_at,
                   EXTRACT(EPOCH FROM (finished_at - started_at))::int AS duration,
                   total_moved, total_skipped, total_errors, status
            FROM archive_runs ORDER BY started_at DESC
        """)
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/runs/{run_id}", summary="Get a single run with all file events")
def get_run(run_id: int):
    """Return one run and every file event for it. 404 if not found."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, group_name, started_at, finished_at,
                   EXTRACT(EPOCH FROM (finished_at - started_at))::int AS duration,
                   total_moved, total_skipped, total_errors, status
            FROM archive_runs WHERE id = %s
        """, (run_id,))
        run = cur.fetchone()

        if not run:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        cur.execute("""
            SELECT source, destination, status, reason, timestamp
            FROM archive_events WHERE run_id = %s ORDER BY timestamp
        """, (run_id,))
        events = cur.fetchall()

    conn.close()
    result = dict(run)
    result["files"] = [dict(e) for e in events]
    return result


@app.get("/runs/{run_id}/files", summary="Get file events for a run (filterable)")
def get_run_files(run_id: int, status: str = Query(None, description="moved | skipped | error")):
    """Return file events. Filter by ?status=moved, ?status=skipped, or ?status=error."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM archive_runs WHERE id = %s", (run_id,))
        if not cur.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        if status:
            cur.execute("""
                SELECT source, destination, status, reason, timestamp
                FROM archive_events WHERE run_id = %s AND status = %s ORDER BY timestamp
            """, (run_id, status))
        else:
            cur.execute("""
                SELECT source, destination, status, reason, timestamp
                FROM archive_events WHERE run_id = %s ORDER BY timestamp
            """, (run_id,))
        events = cur.fetchall()

    conn.close()
    return [dict(e) for e in events]


@app.get("/stats", summary="Aggregate statistics across all runs")
def get_stats():
    """Return totals and group highlights across all runs."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*)                             AS total_runs,
                COALESCE(SUM(total_moved),   0)      AS total_files_archived,
                COALESCE(SUM(total_skipped), 0)      AS total_skipped,
                COALESCE(SUM(total_errors),  0)      AS total_errors,
                (SELECT group_name FROM archive_runs
                 ORDER BY started_at DESC LIMIT 1)   AS most_recent_group,
                (SELECT group_name FROM archive_runs
                 GROUP BY group_name
                 ORDER BY SUM(total_moved) DESC LIMIT 1) AS busiest_group
            FROM archive_runs
        """)
        stats = cur.fetchone()
    conn.close()
    return dict(stats)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    """Serve the browser dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path) as f:
        return HTMLResponse(content=f.read())