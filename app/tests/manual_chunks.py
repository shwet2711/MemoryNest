from app.db.database import engine
from sqlalchemy.orm import Session
from app.db.chunk_model import DocumentChunk

db = Session(engine)

try:
    rows = (
        db.query(DocumentChunk)
        .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        .limit(5)
        .all()
    )

    print(f"Chunks found: {len(rows)}")
    print("-" * 100)

    for r in rows:
        content = r.content[:150].replace("\n", " ")

        print(
            f"ID={r.id} | "
            f"Document={r.document_id} | "
            f"Chunk={r.chunk_index} | "
            f"Characters={r.character_count}"
        )
        print(f"Content: {content}")
        print("-" * 100)

finally:
    db.close()