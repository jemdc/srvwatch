"""
Time-series queries against the TimescaleDB metrics table.
Uses time_bucket() for efficient downsampling over longer ranges.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Map range string → (lookback timedelta, bucket width string)
RANGE_CONFIG: dict[str, tuple[timedelta, str]] = {
    "1h":  (timedelta(hours=1),   "30 seconds"),
    "3h":  (timedelta(hours=3),   "1 minute"),
    "6h":  (timedelta(hours=6),   "2 minutes"),
    "24h": (timedelta(hours=24),  "5 minutes"),
    "3d":  (timedelta(days=3),    "15 minutes"),
    "7d":  (timedelta(days=7),    "30 minutes"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def insert_metrics(session: AsyncSession, server_id: str, payload: dict) -> None:
    """
    Write one poll snapshot into the metrics table.
    Creates one system row + one row per GPU.
    """
    ts  = datetime.fromtimestamp(payload["timestamp"], tz=timezone.utc)
    cpu = payload["cpu"]
    mem = payload["memory"]

    # System row
    await session.execute(text("""
        INSERT INTO metrics (
            time, server_id, gpu_index,
            cpu_pct, cpu_freq_mhz, cpu_temp_c,
            mem_used_mb, mem_total_mb, mem_pct, swap_used_mb
        ) VALUES (
            :time, :server_id, -1,
            :cpu_pct, :cpu_freq_mhz, :cpu_temp_c,
            :mem_used_mb, :mem_total_mb, :mem_pct, :swap_used_mb
        )
        ON CONFLICT (time, server_id, gpu_index) DO UPDATE SET
            cpu_pct       = EXCLUDED.cpu_pct,
            cpu_freq_mhz  = EXCLUDED.cpu_freq_mhz,
            cpu_temp_c    = EXCLUDED.cpu_temp_c,
            mem_used_mb   = EXCLUDED.mem_used_mb,
            mem_total_mb  = EXCLUDED.mem_total_mb,
            mem_pct       = EXCLUDED.mem_pct,
            swap_used_mb  = EXCLUDED.swap_used_mb
    """), {
        "time": ts, "server_id": server_id,
        "cpu_pct": cpu["utilization_pct"],
        "cpu_freq_mhz": cpu.get("frequency_mhz"),
        "cpu_temp_c": cpu.get("temperature_c"),
        "mem_used_mb": mem["used_mb"],
        "mem_total_mb": mem["total_mb"],
        "mem_pct": mem["used_pct"],
        "swap_used_mb": mem["swap_used_mb"],
    })

    # GPU rows
    for gpu in payload.get("gpus", []):
        await session.execute(text("""
            INSERT INTO metrics (
                time, server_id, gpu_index,
                gpu_vendor, gpu_name,
                vram_used_mb, vram_total_mb, vram_pct,
                gpu_power_w, gpu_power_limit_w, gpu_temp_c, gpu_util_pct
            ) VALUES (
                :time, :server_id, :gpu_index,
                :gpu_vendor, :gpu_name,
                :vram_used_mb, :vram_total_mb, :vram_pct,
                :gpu_power_w, :gpu_power_limit_w, :gpu_temp_c, :gpu_util_pct
            )
            ON CONFLICT (time, server_id, gpu_index) DO UPDATE SET
                vram_used_mb     = EXCLUDED.vram_used_mb,
                vram_pct         = EXCLUDED.vram_pct,
                gpu_power_w      = EXCLUDED.gpu_power_w,
                gpu_temp_c       = EXCLUDED.gpu_temp_c,
                gpu_util_pct     = EXCLUDED.gpu_util_pct
        """), {
            "time": ts, "server_id": server_id,
            "gpu_index": gpu["index"],
            "gpu_vendor": gpu["vendor"],
            "gpu_name": gpu["name"],
            "vram_used_mb": gpu["vram_used_mb"],
            "vram_total_mb": gpu["vram_total_mb"],
            "vram_pct": gpu["vram_pct"],
            "gpu_power_w": gpu.get("power_draw_w"),
            "gpu_power_limit_w": gpu.get("power_limit_w"),
            "gpu_temp_c": gpu.get("temperature_c"),
            "gpu_util_pct": gpu.get("gpu_utilization_pct"),
        })

    await session.commit()


async def query_history(
    session: AsyncSession,
    server_id: str,
    range_key: str = "1h",
    gpu_index: int = -1,
) -> list[dict[str, Any]]:
    """
    Return time-bucketed history for a server.
    gpu_index == -1 → system (cpu/mem) row
    gpu_index >= 0  → specific GPU row
    """
    lookback, bucket = RANGE_CONFIG.get(range_key, RANGE_CONFIG["1h"])
    since = _now() - lookback

    if gpu_index == -1:
        sql = text("""
            SELECT
                time_bucket(:bucket, time) AS bucket,
                AVG(cpu_pct)      AS cpu_pct,
                AVG(mem_pct)      AS mem_pct,
                AVG(cpu_temp_c)   AS cpu_temp_c
            FROM metrics
            WHERE server_id = :server_id
              AND gpu_index = -1
              AND time >= :since
            GROUP BY bucket
            ORDER BY bucket ASC
        """)
    else:
        sql = text("""
            SELECT
                time_bucket(:bucket, time) AS bucket,
                AVG(vram_pct)     AS vram_pct,
                AVG(gpu_power_w)  AS gpu_power_w,
                AVG(gpu_util_pct) AS gpu_util_pct,
                AVG(gpu_temp_c)   AS gpu_temp_c
            FROM metrics
            WHERE server_id  = :server_id
              AND gpu_index  = :gpu_index
              AND time >= :since
            GROUP BY bucket
            ORDER BY bucket ASC
        """)

    result = await session.execute(sql, {
        "bucket":     bucket,
        "server_id":  server_id,
        "since":      since,
        "gpu_index":  gpu_index,
    })

    rows = result.mappings().all()
    return [dict(r) for r in rows]
