from app.db.database import Base, engine
from app.db.notification_preference_model import NotificationPreference  # noqa: F401
from app.db.notification_delivery_model import NotificationDelivery  # noqa: F401
from app.db.migrations import run_migrations

from app.models.user import User  # noqa: F401
from app.db.document_model import Document  # noqa: F401
from app.db.chunk_model import DocumentChunk  # noqa: F401
from app.db.embedding_model import ChunkEmbedding  # noqa: F401
from app.db.conversation_model import Conversation  # noqa: F401
from app.db.message_model import Message  # noqa: F401
from app.db.user_session_model import UserSession  # noqa: F401
from app.db.event_model import DetectedEvent  # noqa: F401
from app.db.knowledge_graph_sync_model import KnowledgeGraphSyncJob  # noqa: F401
from app.db.gmail_connection_model import GmailConnection  # noqa: F401
from app.db.google_calendar_model import (  # noqa: F401
    GoogleCalendarConnection,
    GoogleCalendarSync,
)


def init_database() -> None:
    """Create all database tables and run migrations."""

    Base.metadata.create_all(bind=engine)
    run_migrations()


if __name__ == "__main__":
    init_database()
    print("Database initialized successfully.")
