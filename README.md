# Dew CIS Solutions — Python Developer Technical Assignment
## Ref: 60/2026 | Author: Maryann Mweru | April 2026

---

## Overview

This repository contains the complete solution for the Dew CIS Solutions Python Developer technical assignment. The assignment is divided into two independent parts, each in its own folder with its own Docker environment.

| Part | Folder | What it builds | Time |
|------|--------|---------------|------|
| 1 | `dew-cis-part1/` | File Archiving System — CLI + PostgreSQL + FastAPI + Dashboard | 2½ hours |
| 2 | `dew-cis-part2/` | LDAP Query Script | ½ hour |

---

## Repository Structure

```
dew-cis-solutions/
│
├── dew-cis-part1/                  ← Part 1: File Archiving System
│   ├── docker-compose.yml          # postgres, pgadmin, testenv, api, test-runner
│   ├── setup.sh                    # Bootstraps testenv with users, groups, and files
│   ├── archive_files.py            # The archiver CLI (--group <name>)
│   ├── main.py                     # FastAPI service (GET /runs, /stats, /docs, /)
│   ├── dashboard.html              # Live browser dashboard served at /
│   ├── test_archive.py             # 13 pytest tests (archiver + API, ordered)
│   ├── conftest.py                 # Shared fixtures; reads config from env vars
│   ├── pytest.ini                  # Pytest settings and marker definitions
│   ├── requirements.txt            # Python dependencies
│   ├── PLANNING.md                 # Schema design, API mapping, robustness, test plan
│   ├── README.md                   # Full Part 1 documentation
│   └── debian-pkg/
│       ├── DEBIAN/control          # .deb package metadata
│       └── usr/local/bin/
│           └── archive-files       # Installed executable
│
└── dew-cis-part2/                  ← Part 2: LDAP Query
    ├── docker-compose.yml          # openldap + phpLDAPadmin
    ├── ldap-seed.ldif              # Seeds users and groups into OpenLDAP
    ├── ldap_query.py               # The LDAP query script (positional group arg)
    ├── test_ldap.py                # 6 pytest tests
    ├── requirements.txt            # Python dependencies (ldap3, pytest)
    ├── PLANNING.md                 # Lookup design and robustness decisions
    └── README.md                   # Full Part 2 documentation
```

---

## Prerequisites

Both parts require Docker. Nothing else needs to be installed on your machine to run the systems — Docker handles all dependencies internally.

```bash
# Verify Docker is installed and running
docker --version
docker compose version

# Verify Python (only needed to run tests locally, outside Docker)
python3 --version    # 3.10 or higher
```

If `docker compose version` fails, install Docker Desktop from https://docker.com and restart your terminal.

---

## Part 1 — File Archiving System

### What it does

Moves files from home directories of Linux group members to a configurable archive folder. Records every file event to PostgreSQL as it happens. Exposes the data through a FastAPI REST API. Displays it on a live auto-refreshing browser dashboard.

```
archive_files.py  →  PostgreSQL  →  FastAPI (main.py)  →  dashboard.html
  (CLI script)       (archivedb)       :8000                  :8000/
```

### Start everything

```bash
cd dew-cis-part1
docker compose up -d
docker compose ps    # wait until postgres and api show (healthy)
```

### Run the archiver

```bash
# First run — moves 16 files (alice: 8, bob: 8)
docker compose exec testenv python3 archive_files.py --group developers

# Second run — all files already archived, shows 16 skipped
docker compose exec testenv python3 archive_files.py --group developers

# Different group
docker compose exec testenv python3 archive_files.py --group ops

# Edge case — group not found (exits non-zero, no traceback)
docker compose exec testenv python3 archive_files.py --group phantom
```

### Services and URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Dashboard | http://localhost:8000/ | — |
| API | http://localhost:8000/runs | — |
| API docs (Swagger) | http://localhost:8000/docs | — |
| pgAdmin | http://localhost:5050 | admin@dewcis.com / adminpass |

### API endpoints

| Method + Path | What it returns |
|---------------|----------------|
| `GET /runs` | All archive runs, most recent first |
| `GET /runs/{id}` | Single run + all file events. `404` if not found |
| `GET /runs/{id}/files` | File events, filterable with `?status=moved\|skipped\|error`. `404` if not found |
| `GET /stats` | Aggregates: total runs, files archived, skipped, errors, busiest group |
| `GET /` | Browser dashboard (HTML) |
| `GET /docs` | FastAPI Swagger UI |

### Run the tests

```bash
# Self-contained — no local Python needed
docker compose run test-runner

# Or locally (requires pip install -r requirements.txt first)
pytest test_archive.py -v
```

13 tests cover the archiver, database writes, all API endpoints, 404 handling, and the dashboard.

### Build the Debian package

```bash
docker compose exec testenv dpkg-deb --build /workspace/debian-pkg /workspace/archive-files.deb
docker compose exec testenv dpkg -i /workspace/archive-files.deb
docker compose exec testenv archive-files --group finance
```

---

## Part 2 — LDAP Query

### What it does

Connects to an OpenLDAP server, looks up a group by name using a proper server-side LDAP filter, and prints each member's uid, full name, and home directory. Handles missing groups with a clean error message and non-zero exit code.

### Start the LDAP environment

```bash
cd dew-cis-part2
docker compose up -d
sleep 15    # wait for OpenLDAP to finish seeding data
pip3 install -r requirements.txt
```

### Run the script

```bash
python3 ldap_query.py developers
python3 ldap_query.py ops
python3 ldap_query.py finance
python3 ldap_query.py hr
python3 ldap_query.py phantom    # error case
```

### Expected output — developers

```
Group: developers (gidNumber: 2001)
Members:
  alice | Alice Mwangi | /home/alice
  bob | Bob Otieno | /home/bob
```

### Expected output — phantom (not found)

```
Error: group 'phantom' not found in directory.
```
Exit code: `1`

### Run the tests

```bash
pytest test_ldap.py -v
```

6 tests cover all four groups, the single-member group, the not-found error case, and the exact output format.

### Services and URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| phpLDAPadmin | http://localhost:8090 | cn=admin,dc=dewcis,dc=com / adminpass |

---

## Design Decisions

### Part 1 — Why two database tables?

The system tracks two conceptually different things: a run (which group, when, summary totals) and individual file events (which file, what happened, why). Keeping them separate means a run record is created the moment the archiver starts — before any files are touched — and each file event is committed to the database immediately as it happens. If the script is killed halfway through, partial results are already visible in the database with `status = running` on the run record. A single table would require batching everything and writing only at the end, which loses all observability during a run.

### Part 1 — Why read DB config from environment variables?

Hard-coding `localhost` and credentials into the script would break as soon as the script runs inside Docker (where the DB host is `postgres`, not `localhost`). Reading from environment variables means the exact same code works in both places — Docker sets `DB_HOST=postgres`, a local developer's shell uses the default `localhost`.

### Part 1 — Why is test order important?

Archiver tests (orders 1–5) create the database records that API tests (orders 6–13) then read. If the API tests ran first, `GET /runs` would return an empty array and every assertion would fail. `pytest-order` guarantees the sequence is always correct.

### Part 2 — Why two LDAP searches instead of one?

Groups and users live in separate organisational units (`ou=groups` and `ou=users`). A single LDAP search cannot span both OUs and join the results — that is not how LDAP works. The correct pattern is: search the groups OU for the group entry to get the `memberUid` list, then search the users OU once per member to get their full attributes.

### Part 2 — Why use a server-side filter?

The LDAP search uses `search_filter="(cn=developers)"`, which tells the LDAP server to return only the matching entry. The alternative — fetching all groups and filtering in Python — sends unnecessary data over the network and is explicitly flagged as incorrect in the assignment brief.

---

## Test Summary

### Part 1 — 13 tests

| # | Test | Category |
|---|------|----------|
| 1 | `test_group_not_found` | Archiver robustness |
| 2 | `test_developers_happy_path` | Archiver + DB |
| 3 | `test_second_invocation_same_group` | Archiver idempotency |
| 4 | `test_ops_group_separate_run` | Archiver isolation |
| 5 | `test_progressive_db_writes` | DB write timing |
| 6 | `test_api_get_runs_returns_array` | API |
| 7 | `test_api_get_single_run_with_files` | API |
| 8 | `test_api_run_not_found_returns_404` | API error handling |
| 9 | `test_api_run_files_filter_by_status` | API filtering |
| 10 | `test_api_run_files_filter_404` | API error handling |
| 11 | `test_api_stats_aggregates` | API aggregates |
| 12 | `test_api_docs_accessible` | API docs |
| 13 | `test_dashboard_accessible` | Dashboard |

### Part 2 — 6 tests

| # | Test | Scenario |
|---|------|----------|
| 1 | `test_developers_group` | Happy path, 2 members |
| 2 | `test_ops_group` | Happy path, 2 members |
| 3 | `test_finance_group` | Happy path, 2 members |
| 4 | `test_hr_group_single_member` | Single-member group |
| 5 | `test_group_not_found` | Missing group — clean error |
| 6 | `test_output_format` | Exact format validation |

---

## Submission Checklist

### Part 1

- [x] `docker-compose.yml` — includes postgres, pgadmin, testenv, api, and test-runner
- [x] `setup.sh` — creates Linux users, groups, and test files in testenv
- [x] `requirements.txt` — all Python dependencies pinned
- [x] `archive_files.py` — CLI archiver reading from env vars
- [x] `main.py` — FastAPI service with all 4 required endpoints + startup schema creation
- [x] `dashboard.html` — auto-refreshes every 10 seconds
- [x] `test_archive.py` — 13 ordered pytest tests with docstrings
- [x] `conftest.py` — shared session-scoped fixtures
- [x] `pytest.ini` — test paths, markers, and default options
- [x] `PLANNING.md` — schema tables, ER diagram, SQL per endpoint, robustness table, test plan
- [x] `README.md` — 7-step verification guide, API reference, test table, troubleshooting
- [x] `debian-pkg/DEBIAN/control` — package metadata
- [x] `debian-pkg/usr/local/bin/archive-files` — executable wrapper

### Part 2

- [x] `docker-compose.yml` — openldap + phpLDAPadmin
- [x] `ldap-seed.ldif` — seeds all users and groups
- [x] `ldap_query.py` — two-step LDAP lookup with clean error handling
- [x] `test_ldap.py` — 6 pytest tests covering all groups and edge cases
- [x] `requirements.txt` — ldap3 and pytest
- [x] `PLANNING.md` — two-step lookup design, search bases, robustness decisions
- [x] `README.md` — setup, expected output for all groups, test table, troubleshooting

---

## Quick Reference — All Commands

```bash
# ── PART 1 ──────────────────────────────────────────────────────────────────

cd dew-cis-part1

# Start
docker compose up -d
docker compose ps

# Run archiver
docker compose exec testenv python3 archive_files.py --group developers
docker compose exec testenv python3 archive_files.py --group ops
docker compose exec testenv python3 archive_files.py --group phantom   # error case

# Test (self-contained)
docker compose run test-runner

# Test (locally)
pip install -r requirements.txt && pytest test_archive.py -v

# Build .deb
docker compose exec testenv dpkg-deb --build /workspace/debian-pkg /workspace/archive-files.deb
docker compose exec testenv dpkg -i /workspace/archive-files.deb
docker compose exec testenv archive-files --group finance

# Stop
docker compose down

# ── PART 2 ──────────────────────────────────────────────────────────────────

cd ../dew-cis-part2

# Start
docker compose up -d && sleep 15
pip3 install -r requirements.txt

# Run script
python3 ldap_query.py developers
python3 ldap_query.py ops
python3 ldap_query.py finance
python3 ldap_query.py hr
python3 ldap_query.py phantom    # error case

# Test
pytest test_ldap.py -v

# Stop
docker compose down
```
