
import pytest
from unittest.mock import MagicMock

from app.services.indexing_service import index_document


def test_index_document_rejects_invalid_document_id():
    with pytest.raises(ValueError):
        index_document(
            db=MagicMock(),
            document_id=0,
            user_id=1,
        )


def test_index_document_rejects_invalid_user_id():
    with pytest.raises(ValueError):
        index_document(
            db=MagicMock(),
            document_id=1,
            user_id=0,
        )


def test_index_document_rejects_invalid_batch_size():
    with pytest.raises(ValueError):
        index_document(
            db=MagicMock(),
            document_id=1,
            user_id=1,
            batch_size=0,
        )


def test_index_document_returns_no_chunks():
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    result = index_document(
        db=db,
        document_id=999999,
        user_id=999999,
    )

    assert result == {
        "document_id": 999999,
        "total_chunks": 0,
        "indexed": 0,
        "status": "no_chunks",
    }