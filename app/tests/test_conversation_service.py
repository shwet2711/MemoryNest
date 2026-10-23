from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.document_model import Document
from app.db.session import SessionLocal
from app.models.user import User
from app.services import conversation_service


@pytest.fixture
def conversation_setup(tmp_path, monkeypatch):
    """Create an isolated database for conversation service tests."""

    database_path = tmp_path / "conversations.sqlite"

    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    # Import the models so their tables are registered.
    from app.db.conversation_model import Conversation  # noqa: F401
    from app.db.message_model import Message  # noqa: F401

    Base.metadata.create_all(engine)

    TestSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        conversation_service,
        "SessionLocal",
        TestSessionLocal,
    )

    db = TestSessionLocal()

    try:
        user = User(
            username="conversation_test_user",
            email="conversation_test_user@example.com",
            password_hash="test-only-password-hash",
        )
        db.add(user)
        db.flush()

        extracted_file = tmp_path / "document.txt"
        extracted_file.write_text(
            "Test document content for conversation scope tests.",
            encoding="utf-8",
        )

        document = Document(
            user_id=user.id,
            original_filename="conversation_test.txt",
            stored_filename="conversation_test.txt",
            file_path=str(extracted_file),
            file_type="txt",
            file_size=extracted_file.stat().st_size,
            extracted_text_path=str(extracted_file),
            extraction_status="completed",
            extraction_method="text",
        )
        db.add(document)
        db.commit()

        yield {
            "user_id": user.id,
            "document_id": document.id,
        }

    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_create_conversation():
    fake_conversation = {
        "id": 1,
        "user_id": 1,
        "title": "Test Conversation",
    }

    with patch(
        "app.services.conversation_service.SessionLocal"
    ) as session_factory:

        db = session_factory.return_value

        conversation = type(
            "Conversation",
            (),
            {
                "id": 1,
                "user_id": 1,
                "document_id": None,
                "title": "Test Conversation",
                "created_at": None,
                "updated_at": None,
            },
        )()

        db.refresh.side_effect = lambda obj: None
        db.add.side_effect = lambda obj: None

        with patch(
            "app.services.conversation_service.Conversation",
            return_value=conversation,
        ):
            result = conversation_service.create_conversation(
                user_id=1,
                title="Test Conversation",
            )

    assert result["id"] == fake_conversation["id"]
    assert result["user_id"] == fake_conversation["user_id"]
    assert result["title"] == fake_conversation["title"]
    assert result["document_id"] is None


def test_create_conversation_rejects_invalid_user():
    with pytest.raises(ValueError):
        conversation_service.create_conversation(user_id=0)


def test_add_message_rejects_invalid_role():
    with pytest.raises(ValueError):
        conversation_service.add_message(
            conversation_id=1,
            user_id=1,
            role="invalid",
            content="Hello",
        )


def test_create_conversation_with_document_scope(
    conversation_setup,
):
    user_id = conversation_setup["user_id"]
    document_id = conversation_setup["document_id"]

    conversation = conversation_service.create_conversation(
        user_id=user_id,
        title="Document Chat",
        document_id=document_id,
    )

    assert conversation["document_id"] == document_id
    assert conversation["user_id"] == user_id


def test_update_conversation_scope(conversation_setup):
    user_id = conversation_setup["user_id"]
    document_id = conversation_setup["document_id"]

    conversation = conversation_service.create_conversation(
        user_id=user_id,
        title="Scope Test",
    )

    updated = conversation_service.update_conversation_scope(
        conversation_id=conversation["id"],
        user_id=user_id,
        document_id=document_id,
    )

    assert updated is not None
    assert updated["document_id"] == document_id


def test_update_conversation_scope_to_all_documents(
    conversation_setup,
):
    user_id = conversation_setup["user_id"]
    document_id = conversation_setup["document_id"]

    conversation = conversation_service.create_conversation(
        user_id=user_id,
        title="All Documents Test",
        document_id=document_id,
    )

    updated = conversation_service.update_conversation_scope(
        conversation_id=conversation["id"],
        user_id=user_id,
        document_id=None,
    )

    assert updated is not None
    assert updated["document_id"] is None
