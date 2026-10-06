
from app.db.chunk_model import DocumentChunk


def test_document_chunk_columns():

    columns = DocumentChunk.__table__.columns

    assert "id" in columns
    assert "document_id" in columns
    assert "user_id" in columns
    assert "chunk_index" in columns
    assert "source_filename" in columns
    assert "file_type" in columns
    assert "page_number" in columns
    assert "extraction_method" in columns
    assert "content" in columns
    assert "character_count" in columns
    assert "created_at" in columns


def test_document_chunk_metadata():

    chunk = DocumentChunk(
        document_id=1,
        user_id=1,
        chunk_index=0,
        source_filename="MindSync.docx",
        file_type="docx",
        page_number=None,
        extraction_method="text",
        content="MemoryNest test content.",
        character_count=25,
    )

    assert chunk.document_id == 1
    assert chunk.user_id == 1
    assert chunk.chunk_index == 0
    assert chunk.source_filename == "MindSync.docx"
    assert chunk.file_type == "docx"
    assert chunk.page_number is None
    assert chunk.extraction_method == "text"
    assert chunk.content == "MemoryNest test content."
    assert chunk.character_count == 25
