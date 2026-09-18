import enum
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Base(DeclarativeBase):
    pass


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guest_id: Mapped[str] = mapped_column(String(64), index=True)
    room_id: Mapped[int] = mapped_column(Integer)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus, name="booking_status"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    payment_received: Mapped[bool] = mapped_column(Boolean, default=False)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Outbox(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    topic: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB)
    trace_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


engine = create_async_engine(settings.dsn, pool_size=10, max_overflow=10, pool_pre_ping=True)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
