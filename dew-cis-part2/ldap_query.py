#!/usr/bin/env python3
"""
ldap_query.py — LDAP Group Member Lookup
Dew CIS Solutions | Ref: 60/2026

Connects to OpenLDAP, looks up a group, and prints each member's
uid, full name, and home directory.

Usage:
    python3 ldap_query.py developers
    python3 ldap_query.py phantom    # exits cleanly with error
"""

import sys
import argparse
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException

LDAP_HOST = "localhost"
LDAP_PORT = 3389
BIND_DN   = "cn=admin,dc=dewcis,dc=com"
BIND_PASS = "adminpass"
GROUPS_OU = "ou=groups,dc=dewcis,dc=com"
USERS_OU  = "ou=users,dc=dewcis,dc=com"


def lookup_group(group_name):
    # Connect and bind
    try:
        server = Server(LDAP_HOST, port=LDAP_PORT, get_info=ALL)
        conn   = Connection(server, user=BIND_DN, password=BIND_PASS, auto_bind=True)
    except LDAPException as e:
        print(f"Error: Cannot connect to LDAP server: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 1: Search for the group by name (server-side filter)
    conn.search(
        search_base=GROUPS_OU,
        search_filter=f"(cn={group_name})",
        search_scope=SUBTREE,
        attributes=["cn", "gidNumber", "memberUid"]
    )

    if not conn.entries:
        print(f"Error: group '{group_name}' not found in directory.", file=sys.stderr)
        sys.exit(1)

    group      = conn.entries[0]
    gid_number = group.gidNumber.value
    members    = group.memberUid.values if group.memberUid else []

    print(f"Group: {group_name} (gidNumber: {gid_number})")
    print("Members:")

    # Step 2: Look up each member individually
    for uid in members:
        conn.search(
            search_base=USERS_OU,
            search_filter=f"(uid={uid})",
            search_scope=SUBTREE,
            attributes=["uid", "cn", "homeDirectory"]
        )
        if conn.entries:
            u = conn.entries[0]
            print(f"  {u.uid.value} | {u.cn.value} | {u.homeDirectory.value}")
        else:
            print(f"  {uid} | (user record not found)")

    conn.unbind()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Look up LDAP group members.")
    parser.add_argument("group", help="Group name to query")
    args = parser.parse_args()
    lookup_group(args.group)