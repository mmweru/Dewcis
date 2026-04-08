# Planning Document — LDAP Query
## Ref: 60/2026

## What the script needs to do

Connect to an OpenLDAP server and, given a group name, list all members
with their uid, full name (cn), and home directory.

## Two-step lookup

The LDAP directory is structured with groups and users in separate
organisational units (OUs). A single search cannot return both group
membership and user details in one query. The lookup therefore has two steps:

Step 1 — Group search:
  Search base:   ou=groups,dc=dewcis,dc=com
  Filter:        (cn=<group_name>)
  Attributes:    cn, gidNumber, memberUid
  Purpose:       Get the list of member UIDs for this group.

Step 2 — User search (one per member):
  Search base:   ou=users,dc=dewcis,dc=com
  Filter:        (uid=<memberUid>)
  Attributes:    uid, cn, homeDirectory
  Purpose:       Get the full details for each member.

We do NOT fetch all groups and filter in Python — we use a proper LDAP
filter so the server does the filtering work. This is more efficient and
is what the brief explicitly requires.

## Connection details

  Host:      localhost
  Port:      3389
  Bind DN:   cn=admin,dc=dewcis,dc=com
  Password:  adminpass

## Robustness

Group not found:
  conn.entries will be empty after the group search.
  Print a clear error message to stderr and call sys.exit(1).
  Do not raise an exception or print a traceback.

LDAP server unavailable:
  Connection will raise LDAPException.
  Catch it, print error, exit with code 1.