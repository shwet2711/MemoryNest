from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now_naive() -> datetime:
    """Return the current UTC time as a timezone-naive datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


class NotificationPreference(Base):
    """Store notification choices and contact verification per user."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    email_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    browser_push_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    whatsapp_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    whatsapp_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    whatsapp_opted_in_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    reminder_minutes_before: Mapped[int] = mapped_column(
        Integer,
        default=1440,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        nullable=False,
    )
