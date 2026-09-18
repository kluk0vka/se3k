from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.dsn, pool_size=10, max_overflow=10, pool_pre_ping=True)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS btree_gist",
    """
    CREATE TABLE IF NOT EXISTS holds (
        id uuid PRIMARY KEY,
        booking_id uuid NOT NULL UNIQUE,
        room_id bigint NOT NULL,
        stay daterange NOT NULL,
        status text NOT NULL CHECK (status IN ('HELD', 'CONFIRMED', 'RELEASED', 'EXPIRED')),
        expires_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT holds_no_overlap EXCLUDE USING gist (room_id WITH =, stay WITH &&)
            WHERE (status IN ('HELD', 'CONFIRMED'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS holds_expiry_idx ON holds (expires_at) WHERE status = 'HELD'",
    """
    CREATE TABLE IF NOT EXISTS processed_events (
        event_id uuid PRIMARY KEY,
        processed_at timestamptz NOT NULL DEFAULT now()
    )
    """,
]


async def init_db() -> None:
    async with engine.begin() as conn:
        for stmt in SCHEMA:
            await conn.execute(text(stmt))
