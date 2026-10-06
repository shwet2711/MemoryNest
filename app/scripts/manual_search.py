
from __future__ import annotations

import argparse

from app.services.search_service import semantic_search


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search MemoryNest documents."
    )

    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    results = semantic_search(
        query=args.query,
        user_id=args.user_id,
        top_k=args.top_k,
    )

    print()
    print("MEMORYNEST SEMANTIC SEARCH")
    print("-------------------------")
    print("Question:", args.query)
    print("Results:", len(results))

    for index, result in enumerate(results, start=1):
        metadata = result["metadata"]

        print()
        print(f"RESULT {index}")
        print("Source:", metadata["source_filename"])
        print("Document ID:", metadata["document_id"])
        print("Chunk ID:", metadata["chunk_id"])
        print("Chunk index:", metadata["chunk_index"])
        print("Distance:", result["distance"])
        print("Content:")
        print(result["content"][:600])


if __name__ == "__main__":
    main()