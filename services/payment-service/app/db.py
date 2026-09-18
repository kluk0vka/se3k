from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.dsn, pool_size=10, max_overflow=10, pool_pre_ping=True)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS payments (
        id uuid PRIMARY KEY,
        booking_id uuid NOT NULL,
        amount_minor bigint NOT NULL,
        currency char(3) NOT NULL,
        status text NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED', 'REFUNDED')),
        psp_reference text,
        failure_reason text,
        idempotency_key text UNIQUE,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS payments_one_success ON payments (booking_id) WHERE status IN ('SUCCEEDED', 'REFUNDED')",
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
