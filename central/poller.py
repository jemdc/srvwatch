"""
Background poller — uses APScheduler to poll every agent on a fixed interval.
On each tick: fetch /metrics from the agent, write to DB, update Redis cache.
"""

import logging
import os
from typing import Any

import httpx
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from cache import set_latest, set_server_status
from db import AsyncSessionLocal, insert_metrics

log = logging.getLogger("srvwatch.poller")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
AGENT_TIMEOUT = 8   # seconds per request

# Loaded once at startup from servers.yaml
_servers: list[dict] = []
_scheduler: AsyncIOScheduler | None = None


def load_servers(path: str = "servers.yaml") -> list[dict]:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get("servers", [])


async def _poll_server(server: dict) -> None:
    sid    = server["id"]
    host   = server["host"]
    port   = server.get("port", 9100)
    secret = server.get("secret", "")
    url    = f"http://{host}:{port}/metrics"
    headers = {}
    if secret:
        headers["X-SRVWatch-Secret"] = secret

    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()

        # Cache latest for live endpoint
        await set_latest(sid, payload)
        await set_server_status(sid, True)

        # Persist to TimescaleDB
        async with AsyncSessionLocal() as session:
            await insert_metrics(session, sid, payload)

        log.debug("Polled %s OK (cpu=%.1f%%)", sid, payload["cpu"]["utilization_pct"])

    except Exception as exc:
        await set_server_status(sid, False)
        log.warning("Failed to poll %s: %s", sid, exc)


async def poll_all() -> None:
    for server in _servers:
        await _poll_server(server)


def start_poller(servers_yaml: str = "servers.yaml") -> None:
    global _servers, _scheduler
    _servers = load_servers(servers_yaml)
    log.info("Poller loaded %d server(s). Interval: %ds", len(_servers), POLL_INTERVAL)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        poll_all,
        trigger=IntervalTrigger(seconds=POLL_INTERVAL),
        id="poll_all",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    log.info("Poller scheduler started.")


def stop_poller() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


def get_server_configs() -> list[dict]:
    """Return server list (without secrets) for the API."""
    return [
        {"id": s["id"], "label": s.get("label", s["id"]), "host": s["host"], "port": s.get("port", 9100)}
        for s in _servers
    ]
