from app.db.database import engine
from app.db.chunk_model import DocumentChunk
from app.db.embedding_model import ChunkEmbedding
from app.services.embedding_service import generate_embeddings
from app.services.embedding_config import (
    get_embedding_model_name,
)
from app.services.vector_store import (
    add_embeddings,
    get_collection,
)
from app.services.search_service import semantic_search
from sqlalchemy.orm import Session


def test_real_document_chunk_to_chromadb():
    """Index one real MemoryNest chunk into ChromaDB."""

    db = Session(engine)

    try:
        chunk = (
            db.query(DocumentChunk)
            .order_by(DocumentChunk.id)
            .first()
        )

        assert chunk is not None, (
            "No document chunks found. "
            "Upload and process a document first."
        )

        embedding = generate_embeddings(
            [chunk.content]
        )[0]

        vector_id = f"real_test_chunk_{chunk.id}"

        add_embeddings(
            vector_ids=[vector_id],
            embeddings=[embedding],
            document_ids=[chunk.document_id],
            chunk_ids=[chunk.id],
            user_ids=[chunk.user_id],
            source_filenames=[chunk.source_filename],
            chunk_indexes=[chunk.chunk_index],
            contents=[chunk.content],
        )

        collection = get_collection()

        result = collection.get(
            ids=[vector_id],
            include=[
                "documents",
                "metadatas",
            ],
        )

        assert result["ids"] == [vector_id]
        assert len(result["documents"]) == 1
        assert result["documents"][0] == chunk.content

        metadata = result["metadatas"][0]

        assert metadata["document_id"] == chunk.document_id
        assert metadata["chunk_id"] == chunk.id
        assert metadata["user_id"] == chunk.user_id
        assert metadata["source_filename"] == chunk.source_filename

        print()
        print("REAL CHROMADB TEST")
        print("-------------------")
        print("Chunk ID:", chunk.id)
        print("Document ID:", chunk.document_id)
        print("Source:", chunk.source_filename)
        print("Vector ID:", vector_id)
        print("Embedding dimension:", len(embedding))
        print("Stored successfully: YES")

    finally:
        db.close()


def test_real_semantic_search():
    """Search ChromaDB using a real document chunk."""

    db = Session(engine)

    try:
        chunk = (
            db.query(DocumentChunk)
            .order_by(DocumentChunk.id)
            .first()
        )

        assert chunk is not None

        results = semantic_search(
            query=chunk.content[:200],
            user_id=chunk.user_id,
            top_k=3,
        )

        assert isinstance(results, list)
        assert len(results) > 0

        print()
        print("REAL SEMANTIC SEARCH TEST")
        print("-------------------------")
        print("Query:", chunk.content[:200])
        print("Results:", len(results))

        for index, result in enumerate(results, start=1):
            print()
            print(f"Result {index}")
            print("Source:", result["metadata"]["source_filename"])
            print("Chunk:", result["metadata"]["chunk_id"])
            print("Distance:", result["distance"])
            print("Content:", result["content"][:200])

    finally:
        db.close()