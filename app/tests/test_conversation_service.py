from unittest.mock import patch

import pytest

from app.services.conversation_service import (
    create_conversation,
)


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
            result = create_conversation(
                user_id=1,
                title="Test Conversation",
            )

    assert result["id"] == fake_conversation["id"]
    assert result["user_id"] == fake_conversation["user_id"]
    assert result["title"] == fake_conversation["title"]
    assert result["document_id"] is None


def test_create_conversation_rejects_invalid_user():
    with pytest.raises(ValueError):
        create_conversation(user_id=0)


def test_add_message_rejects_invalid_role():
    from app.services.conversation_service import add_message

    with pytest.raises(ValueError):
        add_message(
            conversation_id=1,
            user_id=1,
            role="invalid",
            content="Hello",
        )


def test_create_conversation_with_document_scope():
    conversation = create_conversation(
        user_id=1,
        title="Document Chat",
        document_id=6,
    )

    assert conversation["document_id"] == 6


def test_update_conversation_scope():
    from app.services.conversation_service import (
        create_conversation,
        update_conversation_scope,
    )

    conversation = create_conversation(
        user_id=1,
        title="Scope Test",
    )

    updated = update_conversation_scope(
        conversation_id=conversation["id"],
        user_id=1,
        document_id=6,
    )

    assert updated is not None
    assert updated["document_id"] == 6


def test_update_conversation_scope_to_all_documents():
    from app.services.conversation_service import (
        create_conversation,
        update_conversation_scope,
    )

    conversation = create_conversation(
        user_id=1,
        title="All Documents Test",
        document_id=6,
    )

    updated = update_conversation_scope(
        conversation_id=conversation["id"],
        user_id=1,
        document_id=None,
    )

    assert updated is not None
    assert updated["document_id"] is None