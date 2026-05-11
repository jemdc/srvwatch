"""
Time-series queries against the TimescaleDB metrics table.

Fix: asyncpg requires a Python timedelta for time_bucket's interval argument,
not a string like '30 seconds'. We now pass the timedelta directly and use
a separate bucket_seconds param for the GROUP BY to_char() call.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Map range key → (lookback timedelta, bucket timedelta)
RANGE_CONFIG: dict[str, tuple[timedelta, timedelta]] = {
    "1h":  (timedelta(hours=1),  timedelta(seconds=30)),
    "3h":  (timedelta(hours=3),  timedelta(minutes=1)),
    "6h":  (timedelta(hours=6),  timedelta(minutes=2)),
    "24h": (timedelta(hours=24), timedelta(minutes=5)),
    "3d":  (timedelta(days=3),   timedelta(minutes=15)),
    "7d":  (timedelta(days=7),   timedelta(minutes=30)),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def insert_metrics(session: AsyncSession, server_id: str, payload: dict) -> None:
    """
    Write one poll snapshot — one system row (gpu_index=-1) + one row per GPU.
    Plain INSERT, no ON CONFLICT: TimescaleDB hypertables require a special
    unique index for upserts; plain insert is correct at a 10-second poll interval.
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
    """), {
        "time":         ts,
        "server_id":    server_id,
        "cpu_pct":      cpu["utilization_pct"],
        "cpu_freq_mhz": cpu.get("frequency_mhz"),
        "cpu_temp_c":   cpu.get("temperature_c"),
        "mem_used_mb":  mem["used_mb"],
        "mem_total_mb": mem["total_mb"],
        "mem_pct":      mem["used_pct"],
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
        """), {
            "time":              ts,
            "server_id":         server_id,
            "gpu_index":         int(gpu["index"]),
            "gpu_vendor":        gpu["vendor"],
            "gpu_name":          gpu["name"],
            "vram_used_mb":      gpu["vram_used_mb"],
            "vram_total_mb":     gpu["vram_total_mb"],
            "vram_pct":          gpu["vram_pct"],
            "gpu_power_w":       gpu.get("power_draw_w"),
            "gpu_power_limit_w": gpu.get("power_limit_w"),
            "gpu_temp_c":        gpu.get("temperature_c"),
            "gpu_util_pct":      gpu.get("gpu_utilization_pct"),
        })

    await session.commit()


async def query_history(
    session: AsyncSession,
    server_id: str,
    range_key: str = "1h",
    gpu_index: int = -1,
) -> list[dict[str, Any]]:
    """
    Return time-bucketed history rows for one server.

    asyncpg requires a Python timedelta (not a string) for time_bucket's
    interval argument — it maps to PostgreSQL's INTERVAL type directly.

    The bucket column is returned as an ISO-8601 TEXT string so JavaScript's
    new Date() always parses it correctly.
    """
    lookback, bucket_td = RANGE_CONFIG.get(range_key, RANGE_CONFIG["1h"])
    since = _now() - lookback

    if int(gpu_index) == -1:
        sql = text("""
            SELECT
                to_char(
                    time_bucket(:bucket, time),
                    'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                )                AS bucket,
                AVG(cpu_pct)     AS cpu_pct,
                AVG(mem_pct)     AS mem_pct,
                AVG(cpu_temp_c)  AS cpu_temp_c
            FROM   metrics
            WHERE  server_id = :server_id
              AND  gpu_index  = -1
              AND  time       >= :since
            GROUP  BY time_bucket(:bucket, time)
            ORDER  BY 1 ASC
        """)
    else:
        sql = text("""
            SELECT
                to_char(
                    time_bucket(:bucket, time),
                    'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                )                  AS bucket,
                AVG(vram_pct)      AS vram_pct,
                AVG(gpu_power_w)   AS gpu_power_w,
                AVG(gpu_util_pct)  AS gpu_util_pct,
                AVG(gpu_temp_c)    AS gpu_temp_c
            FROM   metrics
            WHERE  server_id = :server_id
              AND  gpu_index  = :gpu_index
              AND  time       >= :since
            GROUP  BY time_bucket(:bucket, time)
            ORDER  BY 1 ASC
        """)

    result = await session.execute(sql, {
        "bucket":     bucket_td,       # timedelta — asyncpg maps to INTERVAL
        "server_id":  server_id,
        "since":      since,
        "gpu_index":  int(gpu_index),
    })

    return [dict(r) for r in result.mappings().all()]
