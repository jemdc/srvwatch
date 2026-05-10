# SRVWatch Agent

Lightweight FastAPI metrics endpoint. Deploy on every Ubuntu machine you want to monitor.

## Quick Install

```bash
# Basic
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/srvwatch/main/agent/install.sh | sudo bash

# With options
SRVWATCH_SECRET=mysecret \
SRVWATCH_LABEL="gpu-rig-01" \
SRVWATCH_PORT=9100 \
  curl -fsSL https://raw.githubusercontent.com/YOUR_USER/srvwatch/main/agent/install.sh | sudo bash
```

## Environment Variables (`/etc/srvwatch-agent.env`)

| Variable | Default | Description |
|---|---|---|
| `SRVWATCH_SECRET` | *(empty)* | Shared secret. Set this and send `X-SRVWatch-Secret: <value>` header. |
| `SRVWATCH_LABEL` | hostname | Display name shown in dashboard |
| `SRVWATCH_PORT` | `9100` | Listen port |

## API

| Endpoint | Auth | Description |
|---|---|---|
| `GET /` | No | Service info |
| `GET /health` | No | Liveness probe |
| `GET /metrics` | If secret set | Full metrics snapshot |
| `GET /docs` | No | Swagger UI |

## AMD GPU Support

| Scenario | Method | Metrics |
|---|---|---|
| ROCm installed | `rocm-smi --json` | vRAM, power, temp, utilization |
| No ROCm, `amdgpu` driver loaded | sysfs `/sys/class/drm/` | vRAM, power (hwmon), temp, busy % |
| No AMD GPU | — | Silently skipped |

## Service Management

```bash
sudo systemctl status srvwatch-agent
sudo systemctl restart srvwatch-agent
sudo journalctl -u srvwatch-agent -f
```

## Update

```bash
sudo systemctl stop srvwatch-agent
sudo git -C /opt/srvwatch-agent pull
sudo /opt/srvwatch-agent/venv/bin/pip install -r /opt/srvwatch-agent/agent/requirements.txt
sudo systemctl start srvwatch-agent
```

## Uninstall

```bash
sudo systemctl disable --now srvwatch-agent
sudo rm /etc/systemd/system/srvwatch-agent.service /etc/srvwatch-agent.env
sudo rm -rf /opt/srvwatch-agent
sudo userdel srvwatch
sudo systemctl daemon-reload
```
