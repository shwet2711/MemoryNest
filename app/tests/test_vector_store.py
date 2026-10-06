from app.services.vector_config import (
    get_chroma_path,
    get_collection_name,
)
from app.services.vector_store import (
    get_chroma_client,
    get_collection,
    get_collection_count,
)


def test_chroma_path_exists():
    path = get_chroma_path()

    assert path.exists()
    assert path.is_dir()


def test_collection_name():
    name = get_collection_name()

    assert isinstance(name, str)
    assert len(name) > 0


def test_chroma_client():
    client = get_chroma_client()

    assert client is not None


def test_chroma_collection():
    collection = get_collection()

    assert collection is not None
    assert collection.name == get_collection_name()


def test_collection_count():
    count = get_collection_count()

    assert isinstance(count, int)
    assert count >= 0


import pytest

from app.services.vector_store import add_embeddings


def test_add_embeddings_rejects_mismatched_lists():
    with pytest.raises(ValueError):
        add_embeddings(
            vector_ids=["test_1"],
            embeddings=[[0.1, 0.2]],
            document_ids=[1],
            chunk_ids=[],
            user_ids=[1],
            source_filenames=["test.txt"],
            chunk_indexes=[0],
            contents=["MemoryNest test"],
        )


def test_add_embeddings_rejects_empty_content():
    with pytest.raises(ValueError):
        add_embeddings(
            vector_ids=["test_2"],
            embeddings=[[0.1, 0.2]],
            document_ids=[1],
            chunk_ids=[1],
            user_ids=[1],
            source_filenames=["test.txt"],
            chunk_indexes=[0],
            contents=["   "],
        )
