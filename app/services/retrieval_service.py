
from __future__ import annotations

from app.services.embedding_service import generate_embedding
from app.services.vector_store import get_collection


def retrieve_chunks(
    query: str,
    user_id: int,
    top_k: int = 5,
    document_id: int | None = None,
) -> list[dict]:
    """
    Retrieve relevant chunks from the current user's knowledge base.

    Results include source metadata and cosine distance.
    """

    if not isinstance(query, str):
        raise TypeError("Query must be a string.")

    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty.")

    if user_id < 1:
        raise ValueError("User ID must be positive.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    if document_id is not None and document_id < 1:
        raise ValueError("Document ID must be positive.")

    collection = get_collection()

    total = collection.count()

    if total == 0:
        return []

    filters = [{"user_id": user_id}]

    if document_id is not None:
        filters.append({"document_id": document_id})

    where = filters[0] if len(filters) == 1 else {"$and": filters}

    # Find how many vectors belong to this filter.
    matching = collection.get(
        where=where,
        include=[],
    )

    matching_count = len(matching.get("ids", []))

    if matching_count == 0:
        return []

    query_embedding = generate_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, matching_count),
        where=where,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    documents = results.get("documents", [[]])[0] or []
    metadatas = results.get("metadatas", [[]])[0] or []
    distances = results.get("distances", [[]])[0] or []
    ids = results.get("ids", [[]])[0] or []

    output = []

    for vector_id, content, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
        strict=True,
    ):
        output.append(
            {
                "vector_id": vector_id,
                "content": content,
                "metadata": metadata,
                "distance": float(distance),
            }
        )

    return output