#!/bin/bash
# setup.sh — Prepare the testenv container
# Dew CIS Solutions | Ref: 60/2026
set -e

echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y python3 python3-pip libpq-dev -qq

echo "==> Installing Python dependencies..."
pip3 install psycopg2-binary --break-system-packages -q

echo "==> Creating Linux groups..."
groupadd -f developers
groupadd -f ops

echo "==> Creating users and home directories..."
for user in alice bob; do
    if ! id "$user" &>/dev/null; then
        useradd -m -s /bin/bash -G developers "$user"
    fi
done

for user in carol david; do
    if ! id "$user" &>/dev/null; then
        useradd -m -s /bin/bash -G ops "$user"
    fi
done

echo "==> Creating test files..."
for user in alice bob; do
    home="/home/$user"
    mkdir -p "$home/documents" "$home/projects"
    for i in $(seq 1 4); do
        echo "file $i for $user" > "$home/documents/doc${i}.txt"
        echo "project $i for $user" > "$home/projects/proj${i}.py"
    done
    chown -R "$user:$user" "$home"
done

for user in carol david; do
    home="/home/$user"
    mkdir -p "$home/logs" "$home/configs"
    for i in $(seq 1 4); do
        echo "log $i for $user" > "$home/logs/log${i}.log"
        echo "config $i for $user" > "$home/configs/config${i}.yml"
    done
    chown -R "$user:$user" "$home"
done

echo "==> Setup complete. Container staying alive for exec..."
# Keep the container running so tests can exec into it
tail -f /dev/null