#!/usr/bin/env python3
"""
archive_files.py — File Archiving System
Dew CIS Solutions | Ref: 60/2026

Archives all files from home directories of a Linux group's members
to a configurable archive folder. Writes every event to PostgreSQL
as it happens, so partial runs are always visible.

Usage:
    python3 archive_files.py --group developers
    python3 archive_files.py --group ops --archive-dir /mnt/archive
"""

import argparse
import grp
import os
import psycopg2
import pwd
import shutil
import sys

# ── DB config from environment (set in docker-compose.yml or shell) ───────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "archivedb"),
    "user":     os.environ.get("DB_USER", "archiveuser"),
    "password": os.environ.get("DB_PASS", "archivepass"),
}
DEFAULT_ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", "/tmp/archive")


# ── Database helpers ───────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def create_schema(conn):
    """Create archive_runs and archive_events tables if they do not exist."""
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


def start_run(conn, group_name):
    """Insert a run record and return its id. Status starts as 'running'."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO archive_runs (group_name) VALUES (%s) RETURNING id",
            (group_name,)
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id, moved, skipped, errors, status="completed"):
    """Update totals and mark the run finished."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE archive_runs
               SET finished_at = NOW(), status = %s,
                   total_moved = %s, total_skipped = %s, total_errors = %s
               WHERE id = %s""",
            (status, moved, skipped, errors, run_id)
        )
    conn.commit()


def log_event(conn, run_id, source, destination, status, reason=None):
    """Write one file event to the DB immediately (not batched)."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO archive_events
               (run_id, source, destination, status, reason)
               VALUES (%s, %s, %s, %s, %s)""",
            (run_id, source, destination, status, reason)
        )
    conn.commit()


# ── Archiving logic ────────────────────────────────────────────────────────────

def archive_group(group_name, archive_dir):
    """
    Main function. Resolves group members, archives their files,
    and records every event in PostgreSQL.
    """

    # 1. Connect to DB — fail fast if unavailable
    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}", file=sys.stderr)
        sys.exit(1)

    create_schema(conn)

    # 2. Resolve group — exit cleanly if not found
    try:
        group_info = grp.getgrnam(group_name)
    except KeyError:
        print(f"ERROR: Group '{group_name}' does not exist on this system.", file=sys.stderr)
        sys.exit(1)

    members = group_info.gr_mem
    if not members:
        print(f"WARNING: Group '{group_name}' has no members. Nothing to archive.")
        sys.exit(0)

    # 3. Open a run record before touching any files
    run_id = start_run(conn, group_name)
    print(f"Run #{run_id} started — group '{group_name}', {len(members)} member(s).")

    moved = skipped = errors = 0

    for username in members:

        # Resolve home directory
        try:
            home_dir = pwd.getpwnam(username).pw_dir
        except KeyError:
            print(f"  WARNING: No passwd entry for '{username}', skipping.")
            continue

        if not os.path.isdir(home_dir):
            print(f"  WARNING: Home dir '{home_dir}' missing for '{username}', skipping.")
            continue

        # Walk all files recursively
        for dirpath, _, filenames in os.walk(home_dir):
            for filename in filenames:
                src = os.path.join(dirpath, filename)

                # Preserve directory structure under archive_dir
                rel = os.path.relpath(src, "/")
                dst = os.path.join(archive_dir, rel)

                if os.path.exists(dst):
                    log_event(conn, run_id, src, dst, "skipped", "already at destination")
                    print(f"  SKIP  {src}")
                    skipped += 1
                    continue

                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                    log_event(conn, run_id, src, dst, "moved")
                    print(f"  MOVE  {src}")
                    moved += 1
                except PermissionError as e:
                    log_event(conn, run_id, src, None, "error", f"permission denied: {e}")
                    print(f"  ERR   {src} — permission denied")
                    errors += 1
                except Exception as e:
                    log_event(conn, run_id, src, None, "error", str(e))
                    print(f"  ERR   {src} — {e}")
                    errors += 1

    finish_run(conn, run_id, moved, skipped, errors)
    conn.close()
    print(f"\nRun #{run_id} done: {moved} moved, {skipped} skipped, {errors} errors.")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Archive files for all members of a Linux group."
    )
    parser.add_argument("--group",       required=True,             help="Linux group name")
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR, help="Destination directory")
    args = parser.parse_args()

    archive_group(args.group, args.archive_dir)