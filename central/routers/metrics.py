"""
Metrics API routes.

GET /api/servers                        → list of all configured servers + online status
GET /api/servers/{server_id}/live       → latest snapshot from Redis cache
GET /api/servers/{server_id}/history    → time-bucketed history from TimescaleDB
GET /api/servers/{server_id}/gpus       → GPU list from latest snapshot
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

import cache as c
import poller
from db import get_db, query_history, RANGE_CONFIG

log = logging.getLogger("srvwatch.api")
router = APIRouter(prefix="/api", tags=["metrics"])


def _find_server(server_id: str) -> dict:
    servers = poller.get_server_configs()
    for s in servers:
        if s["id"] == server_id:
            return s
    raise HTTPException(404, f"Server '{server_id}' not found in servers.yaml")


@router.get("/servers")
async def list_servers():
    """Return all configured servers with their current online status."""
    servers = poller.get_server_configs()
    result = []
    for s in servers:
        status = await c.get_server_status(s["id"])
        latest = await c.get_latest(s["id"])
        gpus   = latest.get("gpus", []) if latest else []
        result.append({
            **s,
            "online": status,
            "gpu_count": len(gpus),
            "gpu_vendors": list({g["vendor"] for g in gpus}),
        })
    return result


@router.get("/servers/{server_id}/live")
async def server_live(server_id: str):
    """
    Return the latest cached metrics for a server (updated every poll interval).
    This is the primary endpoint for the dashboard's live gauges.
    """
    _find_server(server_id)
    data = await c.get_latest(server_id)
    if data is None:
        raise HTTPException(503, f"No data yet for '{server_id}'. Polling in progress.")
    status = await c.get_server_status(server_id)
    return {**data, "online": status}


@router.get("/servers/{server_id}/history")
async def server_history(
    server_id: str,
    range: str = Query(default="1h", pattern="^(1h|3h|6h|24h|3d|7d)$"),
    gpu_index: int = Query(default=-1, ge=-1),
    db: AsyncSession = Depends(get_db),
):
    """
    Return time-bucketed history for a server.
    - range: 1h | 3h | 6h | 24h | 3d | 7d
    - gpu_index: -1 for system (CPU/MEM), 0..N for specific GPU
    """
    _find_server(server_id)
    rows = await query_history(db, server_id, range_key=range, gpu_index=gpu_index)
    return {
        "server_id": server_id,
        "range": range,
        "gpu_index": gpu_index,
        "points": len(rows),
        "data": rows,
    }


@router.get("/servers/{server_id}/gpus")
async def server_gpus(server_id: str):
    """Return the GPU list from the latest cached snapshot."""
    _find_server(server_id)
    data = await c.get_latest(server_id)
    if data is None:
        raise HTTPException(503, "No data yet for this server.")
    return {"server_id": server_id, "gpus": data.get("gpus", [])}
