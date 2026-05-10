"""
SQLAlchemy ORM model for the metrics time-series table.
One row per poll per GPU slot (GPU index -1 = system-level row).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Metric(Base):
    __tablename__ = "metrics"

    # TimescaleDB requires time as the first dimension
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    server_id: Mapped[str]  = mapped_column(String(64), primary_key=True)

    # GPU index: -1 = system row (cpu/mem only), 0..N = per-GPU row
    gpu_index: Mapped[int]  = mapped_column(Integer, primary_key=True, default=-1)

    # CPU & memory (only set when gpu_index == -1)
    cpu_pct:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpu_freq_mhz:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpu_temp_c:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mem_used_mb:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mem_total_mb:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mem_pct:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    swap_used_mb:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # GPU fields (only set when gpu_index >= 0)
    gpu_vendor:    Mapped[Optional[str]]   = mapped_column(String(16), nullable=True)
    gpu_name:      Mapped[Optional[str]]   = mapped_column(String(128), nullable=True)
    vram_used_mb:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vram_total_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vram_pct:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_power_w:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_power_limit_w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_temp_c:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gpu_util_pct:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
