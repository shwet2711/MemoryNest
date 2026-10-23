
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class GoogleCalendarConnection(Base):
    """Encrypted Google OAuth credentials for one MemoryNest user."""

    __tablename__ = "google_calendar_connections"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    connected_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    encrypted_credentials: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    reauthorization_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class GoogleCalendarSync(Base):
    """Map a MemoryNest event to its Google Calendar event."""

    __tablename__ = "google_calendar_syncs"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "event_id",
            name="uq_google_sync_user_event",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("detected_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    google_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="primary",
    )

    synced_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
