#!/bin/sh
# ============================================================
# deploy/server_setup.sh — prepare a fresh Ubuntu 24.04 server for TriageIQ. Safe to re-run (each step
# checks first). Run ON THE SERVER from the triageiq folder; deploy/push.sh does that for you.
#   1. swap      : 2 GB of disk used as emergency memory — the server has 2 GB RAM; this stops the
#                  out-of-memory killer during image builds or a traffic spike
#   2. Docker    : Docker Engine + the Compose plugin, from Docker's official install script
#   3. deploy/.env : a random database password created HERE, on the server — it never leaves it
# ============================================================
set -e

if ! sudo swapon --show | grep -q /swapfile; then
    echo "== adding a 2 GB swap file"
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "== installing Docker"
    curl -fsSL https://get.docker.com | sudo sh >/dev/null
    sudo systemctl enable --now docker
fi

if [ ! -f deploy/.env ]; then
    echo "== creating deploy/.env (random password, not printed)"
    PW=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
    printf 'POSTGRES_USER=triageiq\nPOSTGRES_DB=triageiq\nPOSTGRES_PASSWORD=%s\n' "$PW" > deploy/.env
    chmod 600 deploy/.env
    unset PW
fi

if ! grep -q '^ORIGIN_SECRET=' deploy/.env; then
    echo "== adding ORIGIN_SECRET to deploy/.env (shared with Vercel; not printed)"
    printf 'ORIGIN_SECRET=%s\n' "$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)" >> deploy/.env
fi

echo "== server ready: $(docker --version | cut -d, -f1) · $(sudo docker compose version --short 2>/dev/null) · swap $(free -h | awk '/Swap/{print $2}')"
