from app.db.database import Base, engine

# Import models so SQLAlchemy knows about them.
from app.models.user import User  # noqa: F401


def init_database() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_database()
    print("Database initialized successfully.")