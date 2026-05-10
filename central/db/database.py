"""
Async SQLAlchemy engine + session factory.
Connects to PostgreSQL with TimescaleDB extension.
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://srvwatch:srvwatch@localhost:5432/srvwatch")

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Create tables and TimescaleDB hypertable on startup."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)

        # Enable TimescaleDB (safe to run multiple times)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))

        # Convert metrics table to hypertable (idempotent)
        await conn.execute(text("""
            SELECT create_hypertable(
                'metrics', 'time',
                if_not_exists => TRUE,
                migrate_data  => TRUE
            );
        """))

        # Auto-drop chunks older than retention window
        retention_days = int(os.getenv("DATA_RETENTION_DAYS", "7"))
        await conn.execute(text(f"""
            SELECT add_retention_policy(
                'metrics',
                INTERVAL '{retention_days} days',
                if_not_exists => TRUE
            );
        """))
