#!/usr/bin/env bash
# SRVWatch — UFW firewall setup for the central server
# Run this on the machine that hosts the central server + dashboard.
#
# Usage: sudo bash ufw-setup.sh [agent-ip-1] [agent-ip-2] ...
# Example: sudo bash ufw-setup.sh 192.168.1.10 192.168.1.11 192.168.1.12
#
# What it does:
#   - Allows SSH (22) from anywhere
#   - Allows the dashboard (8000 or nginx 80) from anywhere on LAN
#   - Blocks direct access to TimescaleDB (5432) and Redis (6379) from outside
#   - Optionally adds rules to poll agent port 9100 from this machine

set -euo pipefail

DASHBOARD_PORT="${DASHBOARD_PORT:-80}"

echo "=== SRVWatch UFW setup ==="

# Ensure UFW is installed
if ! command -v ufw &>/dev/null; then
    apt-get install -y ufw
fi

# Allow SSH (prevent lockout)
ufw allow ssh

# Allow dashboard from LAN (adjust subnet as needed)
ufw allow "${DASHBOARD_PORT}/tcp" comment "SRVWatch dashboard"

# Block DB and cache from outside (they should only be accessed locally/via Docker)
ufw deny 5432/tcp comment "Block external PostgreSQL"
ufw deny 6379/tcp comment "Block external Redis"

# If running central FastAPI directly (not behind Nginx)
if [[ "${DASHBOARD_PORT}" != "8000" ]]; then
    ufw allow 8000/tcp comment "SRVWatch central API"
fi

# Enable UFW
ufw --force enable
ufw status verbose

echo ""
echo "=== Done ==="
echo "Reminder: on each AGENT machine, allow only this central server:"
echo "  sudo ufw allow from $(hostname -I | awk '{print $1}') to any port 9100"
