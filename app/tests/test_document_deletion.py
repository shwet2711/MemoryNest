
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import document_service as service


@pytest.fixture
def deletion_setup(monkeypatch, tmp_path):
    uploaded_file = tmp_path / "uploaded.pdf"
    uploaded_file.write_text("test upload", encoding="utf-8")

    extracted_file = tmp_path / "extracted.txt"
    extracted_file.write_text("test text", encoding="utf-8")

    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()

    chunk_preview = chunk_dir / "document_12_chunks.txt"
    chunk_preview.write_text("test chunks", encoding="utf-8")

    document = SimpleNamespace(
        id=12,
        user_id=7,
        file_path=str(uploaded_file),
        extracted_text_path=str(extracted_file),
    )

    chunk = SimpleNamespace(id=45)

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        chunk
    ]

    monkeypatch.setattr(
        service,
        "get_document",
        lambda db_arg, user_id, document_id: (
            document
            if user_id == 7 and document_id == 12
            else None
        ),
    )
    monkeypatch.setattr(service, "CHUNK_OUTPUT_DIR", chunk_dir)
    monkeypatch.setattr(
        service,
        "delete_document_embeddings",
        MagicMock(return_value=1),
    )
    monkeypatch.setattr(
        service,
        "delete_document_relationships",
        MagicMock(return_value={
            "deleted_relationships": 1,
            "deleted_entities": 0,
        }),
    )
    monkeypatch.setattr(service, "NEO4J_ENABLED", False)

    return SimpleNamespace(
        db=db,
        document=document,
        chunk=chunk,
        uploaded_file=uploaded_file,
        extracted_file=extracted_file,
        chunk_preview=chunk_preview,
    )


def test_delete_document_removes_database_records_and_files(
    deletion_setup,
):
    setup = deletion_setup

    result = service.delete_document(
        setup.db,
        user_id=7,
        document_id=12,
    )

    assert result is True
    setup.db.delete.assert_any_call(setup.chunk)
    setup.db.delete.assert_any_call(setup.document)
    setup.db.commit.assert_called_once()

    assert not setup.uploaded_file.exists()
    assert not setup.extracted_file.exists()
    assert not setup.chunk_preview.exists()

    service.delete_document_embeddings.assert_called_once_with(
        document_id=12,
        user_id=7,
    )
    service.delete_document_relationships.assert_not_called()


def test_delete_document_cleans_graph_when_enabled(
    deletion_setup,
    monkeypatch,
):
    setup = deletion_setup
    monkeypatch.setattr(service, "NEO4J_ENABLED", True)

    result = service.delete_document(
        setup.db,
        user_id=7,
        document_id=12,
    )

    assert result is True
    service.delete_document_relationships.assert_called_once_with(
        user_id=7,
        document_id=12,
    )


def test_delete_missing_document_does_nothing(
    deletion_setup,
    monkeypatch,
):
    setup = deletion_setup

    monkeypatch.setattr(
        service,
        "get_document",
        lambda db, user_id, document_id: None,
    )

    result = service.delete_document(
        setup.db,
        user_id=7,
        document_id=12,
    )

    assert result is False
    setup.db.delete.assert_not_called()
    setup.db.commit.assert_not_called()
    service.delete_document_embeddings.assert_not_called()
    service.delete_document_relationships.assert_not_called()


def test_delete_document_continues_if_vector_cleanup_fails(
    deletion_setup,
    monkeypatch,
):
    setup = deletion_setup

    monkeypatch.setattr(
        service,
        "delete_document_embeddings",
        MagicMock(side_effect=RuntimeError("Chroma unavailable")),
    )

    result = service.delete_document(
        setup.db,
        user_id=7,
        document_id=12,
    )

    assert result is True
    setup.db.commit.assert_called_once()
    assert not setup.uploaded_file.exists()


def test_delete_document_does_not_remove_files_if_commit_fails(
    deletion_setup,
):
    setup = deletion_setup
    setup.db.commit.side_effect = RuntimeError("Commit failed")

    with pytest.raises(RuntimeError, match="Commit failed"):
        service.delete_document(
            setup.db,
            user_id=7,
            document_id=12,
        )

    assert setup.uploaded_file.exists()
    assert setup.extracted_file.exists()
    assert setup.chunk_preview.exists()

    service.delete_document_embeddings.assert_not_called()
