#!/usr/bin/env bash
# setup.sh — Provision test users, groups, and home-directory files
# Runs inside the testenv container at startup (via docker-compose command).
# Safe to re-run: all operations are idempotent.
set -euo pipefail

echo "==> Installing Python + psycopg2 in testenv..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-psycopg2 > /dev/null

echo "==> Creating groups: developers, ops..."
groupadd --force developers
groupadd --force ops

# Helper: create user + home dir if not already present
create_user() {
    local username="$1"
    local group="$2"
    if ! id "$username" &>/dev/null; then
        # --gid sets the primary group; -G adds the user to the supplementary
        # group member list, which is what grp.getgrnam(group).gr_mem returns.
        useradd --create-home --no-log-init --gid "$group" -G "$group" "$username"
        echo "    Created user $username (group: $group)"
    else
        # User already exists — ensure they're in the supplementary group list
        usermod -aG "$group" "$username"
        echo "    User $username already exists — ensured membership in $group"
    fi
}

echo "==> Creating users..."
create_user alice   developers
create_user bob     developers
create_user carol   ops
create_user david   ops

seed_files() {
    local username="$1"
    local home_dir
    home_dir="$(getent passwd "$username" | cut -d: -f6)"

    local seeded=0
    for i in $(seq 1 8); do
        local fpath="${home_dir}/file${i}.txt"
        if [[ ! -f "$fpath" ]]; then
            echo "Sample content for $username — file $i" > "$fpath"
            chown "$username:" "$fpath"
            seeded=$((seeded + 1))
        fi
    done

    local subdir="${home_dir}/docs"
    mkdir -p "$subdir"
    chown "$username:" "$subdir"
    for i in 1 2; do
        local fpath="${subdir}/doc${i}.md"
        if [[ ! -f "$fpath" ]]; then
            echo "# Doc $i for $username" > "$fpath"
            chown "$username:" "$fpath"
            seeded=$((seeded + 1))
        fi
    done

    echo "    $username: seeded $seeded new file(s) in $home_dir"
}

echo "==> Seeding home-directory files..."
for user in alice bob carol david; do
    seed_files "$user"
done

echo "==> Setup complete."
echo "    Users : alice bob (developers)  |  carol david (ops)"
echo "    Files : 10 per user (8 in home, 2 in home/docs)"