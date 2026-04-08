"""
test_ldap.py — Pytest tests for ldap_query.py
Dew CIS Solutions | Ref: 60/2026

Prerequisites:
  docker compose up -d   (wait 15 seconds before running)
  pip install -r requirements.txt

Run:
  pytest test_ldap.py -v
"""

import subprocess
import pytest


def run_query(group):
    """Run ldap_query.py for a given group name. Returns CompletedProcess."""
    return subprocess.run(
        ["python3", "ldap_query.py", group],
        capture_output=True, text=True
    )


def test_developers_group():
    """
    SCENARIO: Query the 'developers' group

    EXPECTED:
    - Exit code 0
    - Output contains 'Group: developers'
    - alice and bob are listed
    - Home directories are present
    """
    result = run_query("developers")

    assert result.returncode == 0, \
        f"Should exit 0 for valid group.\nSTDERR: {result.stderr}"
    assert "developers" in result.stdout
    assert "alice" in result.stdout
    assert "bob"   in result.stdout
    assert "/home/alice" in result.stdout
    assert "/home/bob"   in result.stdout


def test_ops_group():
    """
    SCENARIO: Query the 'ops' group

    EXPECTED:
    - carol and david are members
    """
    result = run_query("ops")

    assert result.returncode == 0
    assert "carol" in result.stdout
    assert "david" in result.stdout


def test_finance_group():
    """
    SCENARIO: Query the 'finance' group

    EXPECTED:
    - eve and frank are members
    """
    result = run_query("finance")

    assert result.returncode == 0
    assert "eve"   in result.stdout
    assert "frank" in result.stdout


def test_hr_group_single_member():
    """
    SCENARIO: Query 'hr' — a group with only one member (grace)

    EXPECTED:
    - Exit code 0
    - grace is listed
    - No crash when group has one member
    """
    result = run_query("hr")

    assert result.returncode == 0, \
        "Should handle single-member group without crashing"
    assert "grace" in result.stdout


def test_group_not_found():
    """
    SCENARIO: Query a group that does not exist in LDAP

    EXPECTED:
    - Exit code 1 (non-zero)
    - Error message contains the group name
    - No Python traceback
    """
    result = run_query("phantom")

    assert result.returncode != 0, \
        "Should exit non-zero when group is not found"
    assert "phantom" in result.stderr, \
        "Error message should mention the group name"
    assert "Traceback" not in result.stderr, \
        "Should not print a Python traceback"


def test_output_format():
    """
    SCENARIO: Output format matches the exact format required by the brief

    EXPECTED format:
        Group: developers (gidNumber: 2001)
        Members:
          alice | Alice Mwangi | /home/alice
          bob | Bob Otieno | /home/bob
    """
    result = run_query("developers")

    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")

    assert lines[0].startswith("Group: developers"), \
        "First line must start with 'Group: developers'"
    assert "gidNumber" in lines[0], \
        "First line must include gidNumber"
    assert lines[1].strip() == "Members:", \
        "Second line must be 'Members:'"

    member_lines = lines[2:]
    assert len(member_lines) >= 2, "Should have at least 2 member lines"

    for line in member_lines:
        parts = [p.strip() for p in line.split("|")]
        assert len(parts) == 3, \
            f"Each member line must have 3 parts separated by '|', got: '{line}'"