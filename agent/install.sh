#!/usr/bin/env bash
# =============================================================================
# SRVWatch Agent — One-line installer for Ubuntu 20.04 / 22.04 / 24.04
#
# Basic usage (run as root or with sudo):
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/srvwatch/main/agent/install.sh | sudo bash
#
# With options:
#   SRVWATCH_SECRET=mysecret \
#   SRVWATCH_LABEL="gpu-rig-01" \
#   SRVWATCH_PORT=9100 \
#     curl -fsSL ... | sudo bash
# =============================================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/YOUR_USER/srvwatch}"
INSTALL_DIR="${INSTALL_DIR:-/opt/srvwatch-agent}"
SERVICE_USER="${SERVICE_USER:-srvwatch}"
SRVWATCH_PORT="${SRVWATCH_PORT:-9100}"
SRVWATCH_SECRET="${SRVWATCH_SECRET:-}"
SRVWATCH_LABEL="${SRVWATCH_LABEL:-$(hostname)}"
VENV_DIR="${INSTALL_DIR}/venv"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[srvwatch]${NC} $*"; }
warn()  { echo -e "${YELLOW}[srvwatch]${NC} $*"; }
error() { echo -e "${RED}[srvwatch]${NC} $*" >&2; exit 1; }
head()  { echo -e "\n${CYAN}══════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}══════════════════════════════════════${NC}"; }

[[ $EUID -ne 0 ]] && error "Run this script as root or with sudo."

head "SRVWatch Agent Installer"
info "Install dir : $INSTALL_DIR"
info "Port        : $SRVWATCH_PORT"
info "Label       : $SRVWATCH_LABEL"
[[ -n "$SRVWATCH_SECRET" ]] && info "Secret      : (set)" || warn "Secret      : NOT SET — open to all LAN traffic"

head "System packages"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl > /dev/null
info "Done."

head "Repository"
AGENT_SRC="${INSTALL_DIR}/agent"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Updating existing clone..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    info "Cloning srvwatch repo..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

head "Python environment"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "${AGENT_SRC}/requirements.txt"
info "Virtual environment ready."

head "Service user"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    info "Created user: $SERVICE_USER"
else
    info "User $SERVICE_USER already exists."
fi
# GPU group access (both AMD and NVIDIA may need these)
usermod -aG render "$SERVICE_USER" 2>/dev/null || true
usermod -aG video  "$SERVICE_USER" 2>/dev/null || true
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

head "GPU detection"
if command -v nvidia-smi &>/dev/null; then
    info "✓ nvidia-smi found — NVIDIA GPU metrics enabled"
else
    warn "  nvidia-smi not found — NVIDIA metrics will be skipped"
    warn "  Install NVIDIA drivers to enable: https://ubuntu.com/server/docs/nvidia-drivers-installation"
fi

if command -v rocm-smi &>/dev/null; then
    info "✓ rocm-smi found — AMD GPU metrics via ROCm enabled"
else
    warn "  rocm-smi not found — AMD GPU will use sysfs fallback (basic metrics)"
    warn "  For full AMD metrics, install ROCm: https://rocm.docs.amd.com/en/latest/deploy/linux/"
fi

head "Environment config"
cat > /etc/srvwatch-agent.env <<EOF
SRVWATCH_SECRET=${SRVWATCH_SECRET}
SRVWATCH_LABEL=${SRVWATCH_LABEL}
SRVWATCH_PORT=${SRVWATCH_PORT}
EOF
chmod 600 /etc/srvwatch-agent.env
info "Written to /etc/srvwatch-agent.env"

head "systemd service"
cat > /etc/systemd/system/srvwatch-agent.service <<EOF
[Unit]
Description=SRVWatch Metrics Agent
After=network.target
Wants=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
EnvironmentFile=/etc/srvwatch-agent.env
WorkingDirectory=${AGENT_SRC}
ExecStart=${VENV_DIR}/bin/uvicorn main:app --host 0.0.0.0 --port \${SRVWATCH_PORT} --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=srvwatch-agent
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable srvwatch-agent
systemctl restart srvwatch-agent
sleep 2

head "Status"
if systemctl is-active --quiet srvwatch-agent; then
    info "✓ srvwatch-agent is running on port ${SRVWATCH_PORT}"
    info ""
    info "  Health check : curl http://localhost:${SRVWATCH_PORT}/health"
    info "  Full metrics : curl http://localhost:${SRVWATCH_PORT}/metrics"
    info "  Swagger UI   : http://$(hostname -I | awk '{print $1}'):${SRVWATCH_PORT}/docs"
    info ""
    if command -v ufw &>/dev/null; then
        warn "Firewall tip: only allow your central server to reach this port:"
        warn "  ufw allow from <central-server-ip> to any port ${SRVWATCH_PORT}"
    fi
else
    error "Service failed to start. Check: journalctl -u srvwatch-agent -n 50"
fi
