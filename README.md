# simple-server-monitor 🖥️

A self-hosted, multi-server metrics monitoring dashboard for Ubuntu machines.
Tracks CPU, memory, and GPU metrics (NVIDIA + AMD) with live gauges and historical charts.

```
[Ubuntu Server A] → agent (:9100) ─┐
[Ubuntu Server B] → agent (:9100) ─┤─▶ Central API (:8000) ─▶ TimescaleDB + Redis
[Ubuntu Server C] → agent (:9100) ─┘         ▲
                                         Frontend (browser)
```

## Features

- **Live metrics** — CPU %, memory, GPU vRAM & power, GPU temp & utilization
- **Historical charts** — 1h / 3h / 6h / 24h / 3d / 7d ranges via ApexCharts
- **Multi-server** — monitor unlimited machines from one dashboard
- **NVIDIA + AMD GPU** support (AMD via ROCm or sysfs fallback)
- **Zero-dependency frontend** — plain HTML/CSS/JS, no build step
- **One-command agent install** on any Ubuntu 20.04–24.04 machine

---

## Quick Start

### 1. Deploy agents on each Ubuntu server

```bash
SRVWATCH_SECRET=changeme SRVWATCH_LABEL="gpu-rig-01" \
  curl -fsSL https://raw.githubusercontent.com/YOUR_USER/srvwatch/main/agent/install.sh | sudo bash
```

### 2. Start the central server

```bash
cd central
cp .env.example .env      # edit with your DB/Redis credentials + server list
docker compose up -d
```

### 3. Open the dashboard

Visit `http://<central-server-ip>:8000` in your browser.

---

## Project Structure

```
srvwatch/
├── agent/               # Deploy on each monitored Ubuntu machine
│   ├── main.py          # FastAPI metrics endpoint
│   ├── install.sh       # One-line installer (systemd service)
│   ├── requirements.txt
│   └── srvwatch-agent.service
│
├── central/             # Central polling server + API + frontend host
│   ├── main.py          # FastAPI app entrypoint
│   ├── poller.py        # Background scheduler — polls all agents every 10s
│   ├── routers/
│   │   ├── metrics.py   # GET /api/servers, /api/servers/{id}/live, /api/servers/{id}/history
│   │   └── health.py    # GET /api/health
│   ├── db/
│   │   ├── database.py  # Async SQLAlchemy + TimescaleDB setup
│   │   ├── models.py    # ORM models
│   │   └── queries.py   # Time-series queries
│   ├── cache.py         # Redis latest-value cache
│   ├── servers.yaml     # ← Add your servers here
│   ├── requirements.txt
│   ├── .env.example
│   └── docker-compose.yml
│
├── frontend/            # Static dashboard (served by central FastAPI)
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js       # Bootstrap, routing, polling
│       ├── charts.js    # ApexCharts setup & update
│       └── api.js       # Central API client
│
└── deploy/
    ├── nginx.conf       # Reverse proxy config
    └── ufw-setup.sh     # Firewall helper
```

---

## Configuration

### Adding servers (`central/servers.yaml`)

```yaml
servers:
  - id: gpu-rig-01
    label: "GPU Rig #1"
    host: 192.168.1.10
    port: 9100
    secret: changeme     # must match SRVWATCH_SECRET on the agent

  - id: workstation-02
    label: "Workstation 2"
    host: 192.168.1.11
    port: 9100
    secret: changeme
```

### Environment (`central/.env`)

```env
DATABASE_URL=postgresql+asyncpg://srvwatch:srvwatch@localhost:5432/srvwatch
REDIS_URL=redis://localhost:6379/0
POLL_INTERVAL_SECONDS=10
DATA_RETENTION_DAYS=7
```

---

## Requirements

| Component | Requirement |
|---|---|
| Agent | Ubuntu 20.04+, Python 3.10+, open port 9100 |
| Central server | Python 3.11+, PostgreSQL 14+ with TimescaleDB, Redis 7+ |
| Frontend | Any modern browser |

---

## License

MIT
