from app.db.database import Base, engine
from app.db.migrations import run_migrations

from app.models.user import User  # noqa: F401
from app.db.document_model import Document  # noqa: F401
from app.db.chunk_model import DocumentChunk  # noqa: F401
from app.db.embedding_model import ChunkEmbedding  # noqa: F401
from app.db.conversation_model import Conversation  # noqa: F401
from app.db.message_model import Message  # noqa: F401


def init_database() -> None:
    """Create all database tables and run migrations."""

    Base.metadata.create_all(bind=engine)

    run_migrations()


if __name__ == "__main__":
    init_database()

    print("Database initialized successfully.")