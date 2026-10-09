
from unittest.mock import MagicMock, patch

import pytest

from app.services import knowledge_graph_service as graph



@pytest.fixture
def mock_driver():
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session

    graph._driver = driver

    with patch.object(graph, "NEO4J_ENABLED", True):
        yield driver, session

    graph._driver = None



def test_get_driver_requires_neo4j_enabled():
    with patch.object(graph, "NEO4J_ENABLED", False):
        with pytest.raises(RuntimeError, match="Neo4j is disabled"):
            graph.get_driver()


def test_get_driver_creates_driver_once():
    graph._driver = None

    with patch.object(graph, "NEO4J_ENABLED", True), patch.object(
        graph.GraphDatabase,
        "driver",
        return_value=MagicMock(),
    ) as create_driver:
        first = graph.get_driver()
        second = graph.get_driver()

        assert first is second
        create_driver.assert_called_once_with(
            graph.NEO4J_URI,
            auth=(graph.NEO4J_USERNAME, graph.NEO4J_PASSWORD),
        )

    graph._driver = None


def test_close_driver_closes_and_resets_driver(mock_driver):
    driver, _ = mock_driver

    graph.close_driver()

    driver.close.assert_called_once()
    assert graph._driver is None


def test_connection_check_when_disabled():
    with patch.object(graph, "NEO4J_ENABLED", False):
        result = graph.check_neo4j_connection()

    assert result["enabled"] is False
    assert result["available"] is False


def test_connection_check_when_available(mock_driver):
    with patch.object(graph, "NEO4J_ENABLED", True):
        result = graph.check_neo4j_connection()

    assert result["enabled"] is True
    assert result["available"] is True
    mock_driver[0].verify_connectivity.assert_called_once()


def test_connection_check_when_unavailable(mock_driver):
    mock_driver[0].verify_connectivity.side_effect = OSError(
        "Connection refused"
    )

    with patch.object(graph, "NEO4J_ENABLED", True):
        result = graph.check_neo4j_connection()

    assert result["enabled"] is True
    assert result["available"] is False


def test_store_relationship_validates_user_id():
    with pytest.raises(ValueError, match="user_id"):
        graph.store_entity_relationship(
            user_id=0,
            document_id=1,
            chunk_index=0,
            subject="MemoryNest",
            subject_type="Project",
            relationship="USES",
            object_name="ChromaDB",
            object_type="Technology",
            source_filename="notes.txt",
        )


def test_store_relationship_rejects_empty_subject():
    with pytest.raises(ValueError, match="subject"):
        graph.store_entity_relationship(
            user_id=1,
            document_id=1,
            chunk_index=0,
            subject=" ",
            subject_type="Project",
            relationship="USES",
            object_name="ChromaDB",
            object_type="Technology",
            source_filename="notes.txt",
        )


def test_store_relationship_rejects_negative_chunk_index():
    with pytest.raises(ValueError, match="chunk_index"):
        graph.store_entity_relationship(
            user_id=1,
            document_id=1,
            chunk_index=-1,
            subject="MemoryNest",
            subject_type="Project",
            relationship="USES",
            object_name="ChromaDB",
            object_type="Technology",
            source_filename="notes.txt",
        )


def test_store_relationship_returns_source_information(mock_driver):
    _, session = mock_driver

    expected = {
        "subject": "MemoryNest",
        "subject_type": "Project",
        "relationship": "USES",
        "object": "ChromaDB",
        "object_type": "Technology",
        "source_filename": "notes.txt",
        "document_id": 4,
        "chunk_index": 2,
    }

    session.run.return_value.single.return_value = expected

    result = graph.store_entity_relationship(
        user_id=1,
        document_id=4,
        chunk_index=2,
        subject="MemoryNest",
        subject_type="Project",
        relationship="USES",
        object_name="ChromaDB",
        object_type="Technology",
        source_filename="notes.txt",
    )

    assert result == expected

    query, parameters = session.run.call_args.args

    assert "MERGE (s:Entity" in query
    assert "MERGE (o:Entity" in query
    assert "MERGE (s)-[r:RELATED_TO" in query
    assert "$source_filename" in query
    assert parameters["user_id"] == 1
    assert parameters["document_id"] == 4
    assert parameters["chunk_index"] == 2


def test_store_relationship_rejects_boolean_user_id():
    with pytest.raises(ValueError, match="user_id"):
        graph.store_entity_relationship(
            user_id=True,
            document_id=1,
            chunk_index=0,
            subject="MemoryNest",
            subject_type="Project",
            relationship="USES",
            object_name="ChromaDB",
            object_type="Technology",
            source_filename="notes.txt",
        )


def test_store_relationship_raises_when_no_record_is_returned(
    mock_driver,
):
    _, session = mock_driver
    session.run.return_value.single.return_value = None

    with pytest.raises(RuntimeError, match="did not return"):
        graph.store_entity_relationship(
            user_id=1,
            document_id=1,
            chunk_index=0,
            subject="MemoryNest",
            subject_type="Project",
            relationship="USES",
            object_name="ChromaDB",
            object_type="Technology",
            source_filename="notes.txt",
        )


def test_find_relationships_returns_records(mock_driver):
    _, session = mock_driver

    expected = [{
        "subject": "MemoryNest",
        "subject_type": "Project",
        "relationship": "USES",
        "object": "ChromaDB",
        "object_type": "Technology",
        "source_filename": "notes.txt",
        "document_id": 4,
        "chunk_index": 2,
    }]

    session.run.return_value = expected

    result = graph.find_entity_relationships(
        user_id=1,
        entity_name="MemoryNest",
    )

    assert result == expected

    query = session.run.call_args.args[0]
    parameters = session.run.call_args.kwargs

    assert "(s:Entity {user_id: $user_id})" in query
    assert "(o:Entity {user_id: $user_id})" in query
    assert parameters["user_id"] == 1
    assert parameters["entity_name"] == "MemoryNest"


def test_find_relationships_validates_limit():
    with pytest.raises(ValueError, match="limit"):
        graph.find_entity_relationships(
            user_id=1,
            entity_name="MemoryNest",
            limit=0,
        )


def test_find_relationships_rejects_empty_entity_name():
    with pytest.raises(ValueError, match="entity_name"):
        graph.find_entity_relationships(
            user_id=1,
            entity_name=" ",
        )
