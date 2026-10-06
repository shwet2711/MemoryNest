
from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.db.database import engine
from app.db.document_model import Document
from app.services.indexing_service import index_document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index a MemoryNest document into ChromaDB."
    )

    parser.add_argument(
        "--document-id",
        type=int,
        required=True,
        help="Document ID to index.",
    )

    parser.add_argument(
        "--user-id",
        type=int,
        required=True,
        help="Owner user ID.",
    )

    args = parser.parse_args()

    with Session(engine) as db:
        document = (
            db.query(Document)
            .filter(
                Document.id == args.document_id,
                Document.user_id == args.user_id,
            )
            .first()
        )

        if document is None:
            raise SystemExit(
                "Document not found for the specified user."
            )

        result = index_document(
            db=db,
            document_id=args.document_id,
            user_id=args.user_id,
        )

        print()
        print("MEMORYNEST DOCUMENT INDEXING")
        print("----------------------------")
        print("Document:", document.original_filename)
        print("Document ID:", result["document_id"])
        print("Total chunks:", result["total_chunks"])
        print("Indexed:", result["indexed"])
        print("Status:", result["status"])


if __name__ == "__main__":
    main()