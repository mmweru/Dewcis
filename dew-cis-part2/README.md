# Part 2 — LDAP Query
## Dew CIS Solutions | Ref: 60/2026 | Author: Maryann Mweru

---

## What This Is

A Python script that connects to an OpenLDAP server, looks up a group by name, and prints every member's uid, full name, and home directory. It handles missing groups cleanly with a clear error message and a non-zero exit code — no Python traceback.

```
python3 ldap_query.py developers
  │
  ├── Step 1: Search ou=groups for cn=developers  →  get memberUid list
  └── Step 2: Search ou=users for each uid        →  print uid | cn | homeDirectory
```

---

## Project Structure

```
dew-cis-part2/
├── docker-compose.yml      # Starts OpenLDAP server + phpLDAPadmin browser UI
├── ldap-seed.ldif          # Pre-populates LDAP with users and groups
├── ldap_query.py           # The LDAP query script
├── test_ldap.py            # 6 pytest tests
├── requirements.txt        # Python dependencies (ldap3, pytest)
├── PLANNING.md             # Design decisions and lookup logic
└── README.md               # This file
```

---

## LDAP Directory Structure

The `ldap-seed.ldif` file seeds the following structure into OpenLDAP on startup:

```
dc=dewcis,dc=com
├── ou=groups
│   ├── cn=developers   (members: alice, bob)       gidNumber: 2001
│   ├── cn=ops          (members: carol, david)      gidNumber: 2002
│   ├── cn=finance      (members: eve, frank)        gidNumber: 2003
│   └── cn=hr           (members: grace)             gidNumber: 2004
└── ou=users
    ├── uid=alice   cn=Alice Mwangi    homeDirectory=/home/alice
    ├── uid=bob     cn=Bob Otieno      homeDirectory=/home/bob
    ├── uid=carol   cn=Carol Kamau     homeDirectory=/home/carol
    ├── uid=david   cn=David Njoroge   homeDirectory=/home/david
    ├── uid=eve     cn=Eve Wanjiku     homeDirectory=/home/eve
    ├── uid=frank   cn=Frank Odhiambo  homeDirectory=/home/frank
    └── uid=grace   cn=Grace Achieng   homeDirectory=/home/grace
```

---

## Prerequisites

| Tool | Minimum version | Check |
|------|----------------|-------|
| Docker Desktop | 24+ | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |
| Python | 3.10+ | `python3 --version` |

---

## Setup

```bash
# 1. Start the LDAP server
docker compose up -d

# 2. Wait 15 seconds for OpenLDAP to finish seeding data
sleep 15

# 3. Install Python dependencies
pip3 install -r requirements.txt
```

> The 15-second wait is important. OpenLDAP processes the `ldap-seed.ldif` file asynchronously on first start. Running the script before seeding completes will return empty results.

---

## Running the Script

### All four groups

```bash
python3 ldap_query.py developers
python3 ldap_query.py ops
python3 ldap_query.py finance
python3 ldap_query.py hr
```

### Edge case — group not found

```bash
python3 ldap_query.py phantom
```

---

## Expected Output

### `python3 ldap_query.py developers`

```
Group: developers (gidNumber: 2001)
Members:
  alice | Alice Mwangi | /home/alice
  bob | Bob Otieno | /home/bob
```

### `python3 ldap_query.py ops`

```
Group: ops (gidNumber: 2002)
Members:
  carol | Carol Kamau | /home/carol
  david | David Njoroge | /home/david
```

### `python3 ldap_query.py finance`

```
Group: finance (gidNumber: 2003)
Members:
  eve | Eve Wanjiku | /home/eve
  frank | Frank Odhiambo | /home/frank
```

### `python3 ldap_query.py hr`

```
Group: hr (gidNumber: 2004)
Members:
  grace | Grace Achieng | /home/grace
```

### `python3 ldap_query.py phantom`

```
Error: group 'phantom' not found in directory.
```

Exit code: `1` (non-zero — signals failure to the caller without a traceback)

Verify the exit code:
```bash
python3 ldap_query.py phantom
echo $?    # prints: 1
```

---

## Running the Tests

```bash
pytest test_ldap.py -v
```

Expected output:

```
test_ldap.py::test_developers_group          PASSED
test_ldap.py::test_ops_group                 PASSED
test_ldap.py::test_finance_group             PASSED
test_ldap.py::test_hr_group_single_member    PASSED
test_ldap.py::test_group_not_found           PASSED
test_ldap.py::test_output_format             PASSED

============ 6 passed in X.XXs ============
```

---

## Test Coverage

| Test | Scenario | What is verified |
|------|----------|-----------------|
| `test_developers_group` | Query `developers` | Exit 0, alice and bob listed, home directories present |
| `test_ops_group` | Query `ops` | Exit 0, carol and david listed |
| `test_finance_group` | Query `finance` | Exit 0, eve and frank listed |
| `test_hr_group_single_member` | Query `hr` (one member) | Exit 0, grace listed, no crash on single-member group |
| `test_group_not_found` | Query `phantom` | Exit code ≠ 0, error contains group name, no Python traceback |
| `test_output_format` | Query `developers` | First line `Group: developers (gidNumber: ...)`, second line `Members:`, each member line has exactly 3 pipe-separated fields |

---

## Connection Details

| Field | Value |
|-------|-------|
| Host | localhost |
| Port | 3389 |
| Bind DN | cn=admin,dc=dewcis,dc=com |
| Password | adminpass |
| Groups search base | ou=groups,dc=dewcis,dc=com |
| Users search base | ou=users,dc=dewcis,dc=com |

---

## phpLDAPadmin (Browser UI)

A browser-based LDAP explorer is available at **http://localhost:8090**

| Field | Value |
|-------|-------|
| Login DN | cn=admin,dc=dewcis,dc=com |
| Password | adminpass |

Use this to browse the full directory tree and verify the seeded data visually.

---

## How the Lookup Works

The script performs two separate LDAP searches — it cannot retrieve group membership and user details in a single query because groups and users live in different organisational units.

**Search 1 — Find the group** (server-side filter, not Python-side)

```
Search base:  ou=groups,dc=dewcis,dc=com
Filter:       (cn=developers)
Attributes:   cn, gidNumber, memberUid
```

This returns the group entry, which includes a `memberUid` list: `['alice', 'bob']`.

**Search 2 — Look up each member individually**

```
Search base:  ou=users,dc=dewcis,dc=com
Filter:       (uid=alice)
Attributes:   uid, cn, homeDirectory
```

Repeated once per `memberUid`. The results are printed in the required format.

The filter `(cn=developers)` is evaluated on the LDAP server — not all groups are fetched and filtered in Python. This is the correct and efficient approach.

---

## Robustness Handling

| Scenario | What happens |
|----------|-------------|
| Group not found | Prints `Error: group '<name>' not found in directory.` to stderr, exits with code 1, no traceback |
| LDAP server unavailable | Catches `LDAPException`, prints connection error, exits with code 1 |
| Group member has no user record | Prints `(user record not found)` for that member, continues |

---

## Troubleshooting

**Script returns no members or empty output immediately after `docker compose up`**
OpenLDAP needs up to 15 seconds to process the seed file. Wait and try again.

**`ldap3.core.exceptions.LDAPSocketOpenError`**
The LDAP container is not running. Run `docker compose ps` and check the `openldap` service status. If it shows as stopped, run `docker compose up -d`.

**`Error: group 'developers' not found` even though the container is up**
The seed data has not finished loading. Run `docker compose logs openldap` — you should see lines confirming the LDIF was processed. Wait a few more seconds and retry.

**`ModuleNotFoundError: No module named 'ldap3'`**
Run `pip3 install -r requirements.txt` first.

**phpLDAPadmin shows a blank page or connection error**
The `ldap-admin` container may still be starting. Wait 30 seconds and refresh. It depends on the `openldap` service being fully up.
