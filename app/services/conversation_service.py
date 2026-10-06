from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.conversation_model import Conversation
from app.db.message_model import Message
from app.db.session import SessionLocal
from app.models.user import User  # noqa: F401
from app.db.document_model import Document  # noqa: F401


def _get_session() -> Session:
    return SessionLocal()


def _validate_user_id(user_id: int) -> None:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")


def _validate_document_access(
    *,
    user_id: int,
    document_id: int | None,
) -> None:
    _validate_user_id(user_id)

    if document_id is None:
        return

    if not isinstance(document_id, int) or document_id <= 0:
        raise ValueError(
            "document_id must be a positive integer."
        )

    db = _get_session()

    try:
        statement = (
            select(Document.id)
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )

        document = db.scalar(statement)

        if document is None:
            raise ValueError(
                "The selected document is not available to this user."
            )

    finally:
        db.close()


def create_conversation(
    *,
    user_id: int,
    title: str = "New Conversation",
    document_id: int | None = None,
) -> dict[str, Any]:
    _validate_user_id(user_id)

    _validate_document_access(
        user_id=user_id,
        document_id=document_id,
    )

    title = str(title).strip() or "New Conversation"

    db = _get_session()

    try:
        conversation = Conversation(
            user_id=user_id,
            document_id=document_id,
            title=title[:200],
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation_to_dict(conversation)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_conversations(
    *,
    user_id: int,
) -> list[dict[str, Any]]:
    _validate_user_id(user_id)

    db = _get_session()

    try:
        statement = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id
            )
            .order_by(
                Conversation.updated_at.desc()
            )
        )

        conversations = db.scalars(statement).all()

        return [
            conversation_to_dict(conversation)
            for conversation in conversations
        ]

    finally:
        db.close()


def get_conversation(
    *,
    conversation_id: int,
    user_id: int,
) -> dict[str, Any] | None:
    if conversation_id <= 0:
        raise ValueError(
            "conversation_id must be positive."
        )

    _validate_user_id(user_id)

    db = _get_session()

    try:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

        if conversation is None:
            return None

        return conversation_to_dict(
            conversation,
            include_messages=True,
        )

    finally:
        db.close()


def update_conversation_scope(
    *,
    conversation_id: int,
    user_id: int,
    document_id: int | None,
) -> dict[str, Any] | None:
    if conversation_id <= 0:
        raise ValueError(
            "conversation_id must be positive."
        )

    _validate_user_id(user_id)

    _validate_document_access(
        user_id=user_id,
        document_id=document_id,
    )

    db = _get_session()

    try:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

        if conversation is None:
            return None

        conversation.document_id = document_id
        conversation.updated_at = datetime.now(
            timezone.utc
        )

        db.commit()
        db.refresh(conversation)

        return conversation_to_dict(conversation)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def rename_conversation(
    *,
    conversation_id: int,
    user_id: int,
    title: str,
) -> dict[str, Any] | None:
    if conversation_id <= 0:
        raise ValueError(
            "conversation_id must be positive."
        )

    _validate_user_id(user_id)

    title = str(title).strip()

    if not title:
        raise ValueError(
            "Conversation title cannot be empty."
        )

    db = _get_session()

    try:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

        if conversation is None:
            return None

        conversation.title = title[:200]
        conversation.updated_at = datetime.now(
            timezone.utc
        )

        db.commit()
        db.refresh(conversation)

        return conversation_to_dict(conversation)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def add_message(
    *,
    conversation_id: int,
    user_id: int,
    role: str,
    content: str,
    mode: str | None = None,
    sources: list[str] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    if conversation_id <= 0:
        raise ValueError(
            "conversation_id must be positive."
        )

    _validate_user_id(user_id)

    allowed_roles = {
        "user",
        "assistant",
        "system",
    }

    if role not in allowed_roles:
        raise ValueError(
            "role must be user, assistant, or system."
        )

    content = str(content).strip()

    if not content:
        raise ValueError(
            "Message content cannot be empty."
        )

    db = _get_session()

    try:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

        if conversation is None:
            raise ValueError(
                "Conversation not found."
            )

        now = datetime.now(timezone.utc)

        serialized_sources = None

        if sources:
            serialized_sources = json.dumps(
                [str(source) for source in sources]
            )

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            mode=mode,
            sources=serialized_sources,
            top_k=top_k,
            created_at=now,
        )

        conversation.updated_at = now

        db.add(message)

        db.commit()
        db.refresh(message)

        return message_to_dict(message)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def delete_conversation(
    *,
    conversation_id: int,
    user_id: int,
) -> bool:
    if conversation_id <= 0:
        raise ValueError(
            "conversation_id must be positive."
        )

    _validate_user_id(user_id)

    db = _get_session()

    try:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

        if conversation is None:
            return False

        db.delete(conversation)
        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def conversation_to_dict(
    conversation: Conversation,
    *,
    include_messages: bool = False,
) -> dict[str, Any]:
    data = {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "document_id": getattr(
            conversation,
            "document_id",
            None,
        ),
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }

    if include_messages:
        data["messages"] = [
            message_to_dict(message)
            for message in conversation.messages
        ]

    return data


def message_to_dict(
    message: Message,
) -> dict[str, Any]:
    sources: list[str] = []

    if message.sources:
        try:
            decoded = json.loads(message.sources)

            if isinstance(decoded, list):
                sources = [
                    str(source)
                    for source in decoded
                ]

        except json.JSONDecodeError:
            sources = []

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "mode": message.mode,
        "sources": sources,
        "top_k": message.top_k,
        "created_at": message.created_at,
    }