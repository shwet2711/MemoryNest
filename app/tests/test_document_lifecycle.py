from __future__ import annotations
from unittest.mock import MagicMock

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.chunk_model import DocumentChunk
from app.db.document_model import Document
from app.db.embedding_model import ChunkEmbedding
from app.services import (
    chunk_service,
    document_service,
    indexing_service,
    vector_store,
)
from io import BytesIO

import fitz
from PIL import Image, ImageDraw, ImageFont


class InMemoryVectorCollection:
    """Small isolated substitute for the Chroma collection."""

    def __init__(self):
        self.records = {}

    def upsert(
        self,
        ids,
        embeddings,
        documents,
        metadatas,
    ):
        for vector_id, embedding, content, metadata in zip(
            ids,
            embeddings,
            documents,
            metadatas,
            strict=True,
        ):
            self.records[vector_id] = {
                "embedding": embedding,
                "document": content,
                "metadata": metadata,
            }

    def get(self, ids=None, where=None, include=None):
        selected_ids = list(self.records)

        if ids is not None:
            requested = set(ids)
            selected_ids = [
                vector_id
                for vector_id in selected_ids
                if vector_id in requested
            ]

        if where is not None:
            conditions = where.get("$and", [where])

            selected_ids = [
                vector_id
                for vector_id in selected_ids
                if all(
                    self.records[vector_id]["metadata"].get(key)
                    == value
                    for condition in conditions
                    for key, value in condition.items()
                )
            ]

        result = {"ids": selected_ids}

        if include and "documents" in include:
            result["documents"] = [
                self.records[vector_id]["document"]
                for vector_id in selected_ids
            ]

        if include and "metadatas" in include:
            result["metadatas"] = [
                self.records[vector_id]["metadata"]
                for vector_id in selected_ids
            ]

        return result

    def delete(self, ids):
        for vector_id in ids:
            self.records.pop(vector_id, None)

    def count(self):
        return len(self.records)


@pytest.fixture
def lifecycle_setup(tmp_path, monkeypatch):
    """Create isolated SQL, file, vector and graph settings."""

    database_path = tmp_path / "lifecycle.sqlite"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    Base.metadata.create_all(engine)

    test_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    db = test_session_factory()

    upload_dir = tmp_path / "uploads"
    extracted_dir = tmp_path / "extracted"
    chunk_dir = tmp_path / "chunks"

    for directory in (upload_dir, extracted_dir, chunk_dir):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        document_service, "UPLOAD_DIR", upload_dir
    )
    monkeypatch.setattr(
        document_service, "EXTRACTED_DIR", extracted_dir
    )
    monkeypatch.setattr(
        document_service, "CHUNK_OUTPUT_DIR", chunk_dir
    )
    monkeypatch.setattr(
        chunk_service, "CHUNK_OUTPUT_DIR", chunk_dir
    )

    collection = InMemoryVectorCollection()
    monkeypatch.setattr(
        vector_store, "get_collection", lambda: collection
    )

    monkeypatch.setattr(
        indexing_service,
        "get_embedding_model_name",
        lambda: "test-embedding-model",
    )
    monkeypatch.setattr(
        indexing_service,
        "get_embedding_dimension",
        lambda: 3,
    )
    monkeypatch.setattr(
        indexing_service,
        "generate_embeddings",
        lambda texts: [
            [0.1, 0.2, 0.3] for _ in texts
        ],
    )

    # This lifecycle test does not connect to a real Neo4j database.
    monkeypatch.setattr(
        indexing_service, "NEO4J_ENABLED", False
    )
    monkeypatch.setattr(
        document_service, "NEO4J_ENABLED", False
    )

    yield {
        "db": db,
        "engine": engine,
        "collection": collection,
        "upload_dir": upload_dir,
        "extracted_dir": extracted_dir,
        "chunk_dir": chunk_dir,
    }

    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_document_lifecycle_creates_indexes_and_cleans_up(
    lifecycle_setup,
):
    setup = lifecycle_setup
    db = setup["db"]

    original_text = (
        "MemoryNest stores personal knowledge using Python and SQLite. "
        "The application divides documents into chunks for retrieval. "
        "Users can search their saved notes and receive grounded answers. "
    ) * 30

    # 1. Create a document and extract its text.
    document = document_service.create_document(
        db=db,
        user_id=987654321,
        filename="lifecycle_notes.txt",
        file_bytes=original_text.encode("utf-8"),
    )

    document_id = document.id
    user_id = document.user_id

    assert document.extraction_status == "completed"
    assert document.extracted_text_path is not None
    assert Path(document.file_path).exists()
    assert Path(document.extracted_text_path).exists()
    assert (
        Path(document.extracted_text_path).read_text(
            encoding="utf-8"
        )
        == original_text.strip()
    )

    # 2. Convert extracted text into persisted chunks.
    chunks = chunk_service.process_document_chunks(
        db=db,
        document=document,
        user_id=user_id,
        chunk_size=500,
        chunk_overlap=50,
    )

    assert len(chunks) > 1
    assert all(chunk.document_id == document_id for chunk in chunks)
    assert all(chunk.user_id == user_id for chunk in chunks)

    chunk_preview = (
        setup["chunk_dir"]
        / f"document_{document_id}_chunks.txt"
    )
    assert chunk_preview.exists()

    assert (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.user_id == user_id,
        )
        .count()
        == len(chunks)
    )

    # 3. Index the chunks using fake embeddings and an isolated vector store.
    indexing_result = indexing_service.index_document(
        db=db,
        document_id=document_id,
        user_id=user_id,
        batch_size=2,
    )

    assert indexing_result["status"] == "completed"
    assert indexing_result["total_chunks"] == len(chunks)
    assert indexing_result["indexed"] == len(chunks)
    assert indexing_result["knowledge_graph_status"] == "disabled"

    assert len(setup["collection"].records) == len(chunks)

    embedding_records = (
        db.query(ChunkEmbedding)
        .filter(
            ChunkEmbedding.document_id == document_id,
            ChunkEmbedding.user_id == user_id,
        )
        .all()
    )

    assert len(embedding_records) == len(chunks)

    for record in embedding_records:
        assert record.model_name == "test-embedding-model"
        assert record.dimension == 3
        assert record.vector_id in setup["collection"].records

    # 4. Delete the document through the actual service.
    deleted = document_service.delete_document(
        db=db,
        user_id=user_id,
        document_id=document_id,
    )

    assert deleted is True

    # 5. Verify that the SQL records and vectors are gone.
    assert (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .count()
        == 0
    )

    assert (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.user_id == user_id,
        )
        .count()
        == 0
    )

    remaining_embedding_count = (
        db.query(func.count(ChunkEmbedding.id))
        .filter(
            ChunkEmbedding.document_id == document_id,
            ChunkEmbedding.user_id == user_id,
        )
        .scalar()
    )

    assert remaining_embedding_count == 0, (
        "Deleting a document should also remove its SQL embedding metadata."
    )

    assert setup["collection"].count() == 0

    assert not Path(document.file_path).exists()
    assert not Path(document.extracted_text_path).exists()
    assert not chunk_preview.exists()

    # Repeated deletion should be harmless.
    assert (
        document_service.delete_document(
            db=db,
            user_id=user_id,
            document_id=document_id,
        )
        is False
    )

def test_document_lifecycle_indexes_and_cleans_up_knowledge_graph(
    lifecycle_setup,
    monkeypatch,
):
    setup = lifecycle_setup
    db = setup["db"]

    user_id = 987654321
    original_text = (
        "MemoryNest connects documents with entities and relationships. "
        "Python supports document processing and knowledge retrieval. "
        "SQLite stores document metadata and chunk information. "
    ) * 30

    # Enable graph integration without connecting to a real Neo4j server.
    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", True)
    monkeypatch.setattr(document_service, "NEO4J_ENABLED", True)

    monkeypatch.setattr(
        indexing_service,
        "check_neo4j_connection",
        lambda: {"enabled": True, "available": True},
    )

    graph_index_mock = MagicMock(
        side_effect=lambda **kwargs: {"stored_count": 1}
    )
    graph_delete_mock = MagicMock(return_value={})

    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        graph_index_mock,
    )
    monkeypatch.setattr(
        document_service,
        "delete_document_relationships",
        graph_delete_mock,
    )

    # 1. Create a document.
    document = document_service.create_document(
        db=db,
        user_id=user_id,
        filename="graph_lifecycle_notes.txt",
        file_bytes=original_text.encode("utf-8"),
    )

    document_id = document.id

    assert document.extraction_status == "completed"

    # 2. Create and persist chunks.
    chunks = chunk_service.process_document_chunks(
        db=db,
        document=document,
        user_id=user_id,
        chunk_size=500,
        chunk_overlap=50,
    )

    assert len(chunks) > 1

    # 3. Index vectors and process every chunk for the graph.
    result = indexing_service.index_document(
        db=db,
        document_id=document_id,
        user_id=user_id,
        batch_size=2,
    )

    assert result["status"] == "completed"
    assert result["indexed"] == len(chunks)
    assert result["knowledge_graph_status"] == "completed"
    assert result["knowledge_graph_processed_chunks"] == len(chunks)
    assert result["knowledge_graph_failed_chunks"] == 0
    assert result["knowledge_graph_relationships_stored"] == len(chunks)

    assert graph_index_mock.call_count == len(chunks)

    processed_chunk_indexes = {
        call.kwargs["chunk_index"]
        for call in graph_index_mock.call_args_list
    }

    assert processed_chunk_indexes == {
        chunk.chunk_index for chunk in chunks
    }

    for graph_call in graph_index_mock.call_args_list:
        assert graph_call.kwargs["user_id"] == user_id
        assert graph_call.kwargs["document_id"] == document_id
        assert graph_call.kwargs["text"].strip()
        assert graph_call.kwargs["source_filename"]

    # 4. Delete the document using the real deletion service.
    deleted = document_service.delete_document(
        db=db,
        user_id=user_id,
        document_id=document_id,
    )

    assert deleted is True

    # 5. Verify that graph cleanup receives the correct document scope.
    graph_delete_mock.assert_called_once_with(
        user_id=user_id,
        document_id=document_id,
    )

    # 6. Verify that relational and vector data are also removed.
    assert (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .count()
        == 0
    )

    assert (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.user_id == user_id,
        )
        .count()
        == 0
    )

    assert (
        db.query(ChunkEmbedding)
        .filter(
            ChunkEmbedding.document_id == document_id,
            ChunkEmbedding.user_id == user_id,
        )
        .count()
        == 0
    )

    assert setup["collection"].count() == 0

    assert not Path(document.file_path).exists()
    assert not Path(document.extracted_text_path).exists()

    chunk_preview = (
        setup["chunk_dir"]
        / f"document_{document_id}_chunks.txt"
    )
    assert not chunk_preview.exists()


def create_image_only_pdf_bytes() -> bytes:
    """Create a scanned-style PDF containing an image, not selectable text."""
    image = Image.new("RGB", (1600, 600), "white")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()

    draw.text(
        (60, 70),
        "MemoryNest Document Lifecycle",
        fill="black",
        font=font,
    )
    draw.text(
        (60, 190),
        "Python SQLite document search and retrieval",
        fill="black",
        font=font,
    )
    draw.text(
        (60, 310),
        "Personal knowledge management and reliable text extraction.",
        fill="black",
        font=font,
    )

    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")

    pdf_buffer = BytesIO()

    with fitz.open() as pdf:
        page = pdf.new_page(width=800, height=300)
        page.insert_image(
            page.rect,
            stream=image_buffer.getvalue(),
        )
        pdf_bytes = pdf.tobytes()

    return pdf_bytes


def test_scanned_pdf_lifecycle_indexes_ocr_text(
    lifecycle_setup,
):
    """Verify scanned PDF extraction, metadata, chunks, and vector indexing."""
    setup = lifecycle_setup
    db = setup["db"]

    from app.services.ocr_service import check_tesseract

    available, message = check_tesseract()
    if not available:
        pytest.skip(f"Tesseract is not available: {message}")

    pdf_bytes = create_image_only_pdf_bytes()

    document = document_service.create_document(
        db=db,
        user_id=987654321,
        filename="scanned_lifecycle.pdf",
        file_bytes=pdf_bytes,
    )

    document_id = document.id
    user_id = document.user_id

    assert document.extraction_status == "completed"
    assert document.extraction_method == "ocr"
    assert document.ocr_confidence is not None
    assert 0 <= document.ocr_confidence <= 100

    extracted_path = Path(document.extracted_text_path)
    assert extracted_path.exists()

    extracted_text = extracted_path.read_text(encoding="utf-8")

    assert "MemoryNest" in extracted_text
    assert "SQLite" in extracted_text

    chunks = chunk_service.process_document_chunks(
        db=db,
        document=document,
        user_id=user_id,
        chunk_size=500,
        chunk_overlap=50,
    )

    assert chunks
    assert all(chunk.document_id == document_id for chunk in chunks)
    assert all(chunk.extraction_method == "ocr" for chunk in chunks)

    result = indexing_service.index_document(
        db=db,
        document_id=document_id,
        user_id=user_id,
        batch_size=2,
    )

    assert result["status"] == "completed"
    assert result["indexed"] == len(chunks)
    assert result["knowledge_graph_status"] == "disabled"
    assert setup["collection"].count() == len(chunks)


def test_low_confidence_scanned_pdf_is_preserved_and_skipped_by_graph(
    lifecycle_setup,
    monkeypatch,
):
    """Preserve low-confidence OCR text while skipping graph extraction."""
    setup = lifecycle_setup
    db = setup["db"]

    user_id = 987654322
    expected_text = (
        "MemoryNest uses Python and SQLite to store personal knowledge. "
        "Documents are divided into chunks for search and retrieval. "
    ) * 5

    # Simulate a scanned PDF whose OCR returned text but low confidence.
    # This keeps the test deterministic and independent of OCR variability.
    monkeypatch.setattr(
        document_service,
        "extract_pdf_with_ocr",
        lambda file_path: [
            {
                "page_number": 1,
                "text": expected_text,
                "method": "ocr_low_confidence",
                "ocr_confidence": 25.0,
                "quality_score": 0.8,
                "quality_reasons": ["low_ocr_confidence"],
            }
        ],
    )

    document = document_service.create_document(
        db=db,
        user_id=user_id,
        filename="low_confidence_scan.pdf",
        file_bytes=create_image_only_pdf_bytes(),
    )

    document_id = document.id

    assert document.extraction_status == "completed"
    assert document.extraction_method == "ocr_low_confidence"
    assert document.ocr_confidence == 25.0

    extracted_path = Path(document.extracted_text_path)
    assert extracted_path.exists()

    extracted_text = extracted_path.read_text(encoding="utf-8")
    assert expected_text.strip() in extracted_text

    chunks = chunk_service.process_document_chunks(
        db=db,
        document=document,
        user_id=user_id,
        chunk_size=500,
        chunk_overlap=50,
    )

    assert chunks
    assert all(
        chunk.extraction_method == "ocr_low_confidence"
        for chunk in chunks
    )

    # Enable a mocked graph connection; never contact real Neo4j.
    monkeypatch.setattr(indexing_service, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        indexing_service,
        "check_neo4j_connection",
        lambda: {"enabled": True, "available": True},
    )

    graph_mock = MagicMock(return_value={"stored_count": 1})
    monkeypatch.setattr(
        indexing_service,
        "process_chunk_for_knowledge_graph",
        graph_mock,
    )

    result = indexing_service.index_document(
        db=db,
        document_id=document_id,
        user_id=user_id,
        batch_size=2,
    )

    assert result["status"] == "completed"
    assert result["indexed"] == len(chunks)
    assert result["knowledge_graph_status"] == "skipped_low_confidence"
    assert result["knowledge_graph_processed_chunks"] == 0
    assert (
        result["knowledge_graph_skipped_low_confidence_chunks"]
        == len(chunks)
    )

    # Low-confidence chunks remain indexed for vector retrieval.
    assert setup["collection"].count() == len(chunks)

    # Graph extraction must not run for these chunks.
    graph_mock.assert_not_called()