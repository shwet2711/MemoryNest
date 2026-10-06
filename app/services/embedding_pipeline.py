# from __future__ import annotations

# from sqlalchemy.orm import Session

# from app.db.chunk_model import DocumentChunk
# from app.db.embedding_model import ChunkEmbedding
# from app.services.embedding_config import get_embedding_model_name
# from app.services.embedding_service import (
#     generate_embeddings,
#     get_embedding_dimension,
# )
# from app.services.vector_store import add_embeddings


# def embed_document_chunks(
#     db: Session,
#     document_id: int,
#     user_id: int,
# ) -> int:
#     """
#     Generate embeddings for document chunks and store them in ChromaDB.
#     """

#     chunks = (
#         db.query(DocumentChunk)
#         .filter(
#             DocumentChunk.document_id == document_id,
#             DocumentChunk.user_id == user_id,
#         )
#         .order_by(DocumentChunk.chunk_index)
#         .all()
#     )

#     if not chunks:
#         return 0

#     existing_embeddings = (
#         db.query(ChunkEmbedding)
#         .filter(
#             ChunkEmbedding.document_id == document_id,
#             ChunkEmbedding.user_id == user_id,
#         )
#         .all()
#     )

#     existing_chunk_ids = {
#         record.chunk_id
#         for record in existing_embeddings
#     }

#     pending_chunks = [
#         chunk
#         for chunk in chunks
#         if chunk.id not in existing_chunk_ids
#     ]

#     if not pending_chunks:
#         return 0

#     texts = [
#         chunk.content
#         for chunk in pending_chunks
#     ]

#     embeddings = generate_embeddings(texts)

#     model_name = get_embedding_model_name()
#     dimension = get_embedding_dimension()

#     vector_ids = [
#         f"chunk_{chunk.id}"
#         for chunk in pending_chunks
#     ]

#     add_embeddings(
#         vector_ids=vector_ids,
#         embeddings=embeddings,
#         document_ids=[
#             chunk.document_id
#             for chunk in pending_chunks
#         ],
#         chunk_ids=[
#             chunk.id
#             for chunk in pending_chunks
#         ],
#         user_ids=[
#             chunk.user_id
#             for chunk in pending_chunks
#         ],
#         source_filenames=[
#             chunk.source_filename
#             for chunk in pending_chunks
#         ],
#         chunk_indexes=[
#             chunk.chunk_index
#             for chunk in pending_chunks
#         ],
#         contents=texts,
#     )

#     for chunk, vector_id in zip(
#         pending_chunks,
#         vector_ids,
#         strict=True,
#     ):
#         record = ChunkEmbedding(
#             chunk_id=chunk.id,
#             document_id=chunk.document_id,
#             user_id=chunk.user_id,
#             model_name=model_name,
#             dimension=dimension,
#             vector_store="chroma",
#             vector_id=vector_id,
#         )

#         db.add(record)

#     db.commit()

#     return len(pending_chunks)


from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.indexing_service import index_document


def embed_document_chunks(
    db: Session,
    document_id: int,
    user_id: int,
) -> int:
    """
    Compatibility wrapper for the existing MemoryNest code.
    """

    result = index_document(
        db=db,
        document_id=document_id,
        user_id=user_id,
    )

    return result["indexed"]