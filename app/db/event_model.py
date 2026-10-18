
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DetectedEvent(Base):
    """A date-related event detected in a user's document."""

    __tablename__ = "detected_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="general",
    )

    event_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    event_end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    date_text: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    date_confidence: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="needs_review",
    )

    source_excerpt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Review state is kept separate from event lifecycle state.
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_review",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
