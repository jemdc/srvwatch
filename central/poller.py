"""
Background poller — uses APScheduler to poll every agent on a fixed interval.
On each tick: fetch /metrics from the agent, write to DB, update Redis cache.
"""

import asyncio
import logging
import os
import time
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
MAX_RETRY_ATTEMPTS = 3    # max retries per server before marking offline
RETRY_BACKOFF_BASE = 2    # exponential backoff base (seconds)

# Loaded once at startup from servers.yaml
_servers: list[dict] = []
_scheduler: AsyncIOScheduler | None = None

# Retry state per server (tracks consecutive failures)
_server_failures: dict[str, int] = {}  # {server_id: failure_count}


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

    # Initialize retry state
    retry_count = _server_failures.get(sid, 0)

    for attempt in range(MAX_RETRY_ATTEMPTS - retry_count):
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

            log.debug("Polled %s OK (cpu=%.1f%%), attempt=%d/%d", sid, payload["cpu"]["utilization_pct"], attempt + 1, MAX_RETRY_ATTEMPTS - retry_count)
            # Reset failure counter on success
            _server_failures[sid] = 0
            break

        except Exception as exc:
            log.warning("Poll %s failed (attempt %d/%d): %s", sid, attempt + 1, MAX_RETRY_ATTEMPTS - retry_count, exc)
            # Apply exponential backoff before retry
            if attempt < MAX_RETRY_ATTEMPTS - retry_count - 1:
                wait_sec = RETRY_BACKOFF_BASE ** (attempt + 1)
                log.info(f"Retrying {sid} in {wait_sec}s...")
                await asyncio.sleep(wait_sec)
    else:
        # All retries exhausted
        await set_server_status(sid, False)
        _server_failures[sid] = MAX_RETRY_ATTEMPTS
        log.error(f"Server {sid} marked offline after {MAX_RETRY_ATTEMPTS} consecutive failures")

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
