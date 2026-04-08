"""
conftest.py — Shared pytest configuration and fixtures.
Reads DB and API connection details from environment variables so
this file works identically locally and inside Docker.
"""

import os
import pytest
import psycopg2
import psycopg2.extras

# ── Read from environment (set in docker-compose.yml) ─────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "archivedb"),
    "user":     os.environ.get("DB_USER", "archiveuser"),
    "password": os.environ.get("DB_PASS", "archivepass"),
}
API_URL = os.environ.get("API_URL", "http://localhost:8000")


def get_db_conn():
    """Return a psycopg2 connection with RealDictCursor."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)


@pytest.fixture(scope="session")
def db():
    """Session-scoped DB connection. Shared across all tests in the session."""
    conn = get_db_conn()
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def api_url():
    """Session-scoped API base URL."""
    return API_URL