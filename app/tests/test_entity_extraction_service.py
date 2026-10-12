
import json
from unittest.mock import MagicMock

import pytest
import requests

from app.services import entity_extraction_service as extraction


def fake_ollama_response(data):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": json.dumps(data)}
    return response


def test_extracts_valid_relationship(monkeypatch):
    monkeypatch.setattr(
        extraction.requests,
        "post",
        lambda *args, **kwargs: fake_ollama_response(
            {
                "relationships": [
                    {
                        "subject": "MemoryNest",
                        "subject_type": "project",
                        "relationship": "uses",
                        "object": "Python",
                        "object_type": "technology",
                    }
                ]
            }
        ),
    )

    result = extraction.extract_relationships(
        "MemoryNest uses Python."
    )

    assert result == [
        {
            "subject": "MemoryNest",
            "subject_type": "project",
            "relationship": "uses",
            "object": "Python",
            "object_type": "technology",
        }
    ]


def test_empty_text_is_rejected_without_calling_ollama(monkeypatch):
    def fail_if_called(*args, **kwargs):
        pytest.fail("Ollama should not be called for empty text.")

    monkeypatch.setattr(extraction.requests, "post", fail_if_called)

    with pytest.raises(ValueError, match="text"):
        extraction.extract_relationships("   ")


def test_duplicate_relationships_are_removed(monkeypatch):
    item = {
        "subject": "MemoryNest",
        "subject_type": "project",
        "relationship": "uses",
        "object": "Python",
        "object_type": "technology",
    }

    monkeypatch.setattr(
        extraction.requests,
        "post",
        lambda *args, **kwargs: fake_ollama_response(
            {"relationships": [item, item]}
        ),
    )

    result = extraction.extract_relationships("MemoryNest uses Python.")

    assert len(result) == 1


def test_invalid_relationship_items_are_skipped(monkeypatch):
    monkeypatch.setattr(
        extraction.requests,
        "post",
        lambda *args, **kwargs: fake_ollama_response(
            {
                "relationships": [
                    None,
                    {"subject": "Only a subject"},
                    {
                        "subject": "MemoryNest",
                        "subject_type": "made_up_type",
                        "relationship": "uses",
                        "object": "Python",
                        "object_type": "technology",
                    },
                ]
            }
        ),
    )

    result = extraction.extract_relationships("MemoryNest uses Python.")

    assert len(result) == 1
    assert result[0]["subject_type"] == "other"


def test_missing_relationship_list_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        extraction.requests,
        "post",
        lambda *args, **kwargs: fake_ollama_response({}),
    )

    assert extraction.extract_relationships("A factual paragraph.") == []


def test_invalid_relationship_list_raises_value_error(monkeypatch):
    monkeypatch.setattr(
        extraction.requests,
        "post",
        lambda *args, **kwargs: fake_ollama_response(
            {"relationships": "not a list"}
        ),
    )

    with pytest.raises(ValueError, match="JSON list"):
        extraction.extract_relationships("Some document text.")


def test_invalid_model_json_raises_value_error(monkeypatch):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": "not valid JSON"}

    monkeypatch.setattr(
        extraction.requests,
        "post",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(ValueError, match="valid JSON"):
        extraction.extract_relationships("Some document text.")


def test_ollama_connection_error_becomes_runtime_error(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("connection failed")

    monkeypatch.setattr(
        extraction.requests,
        "post",
        raise_connection_error,
    )

    with pytest.raises(RuntimeError, match="Could not contact Ollama"):
        extraction.extract_relationships("MemoryNest uses Python.")


def test_model_request_uses_configured_model_and_json_format(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return fake_ollama_response({"relationships": []})

    monkeypatch.setattr(extraction.requests, "post", fake_post)

    extraction.extract_relationships("MemoryNest uses Python.")

    assert captured["url"].endswith("/api/generate")
    assert captured["json"]["model"] == extraction.OLLAMA_MODEL
    assert captured["json"]["format"] == "json"
    assert captured["json"]["stream"] is False


def test_extraction_input_is_bounded(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["prompt"] = kwargs["json"]["prompt"]
        return fake_ollama_response({"relationships": []})

    monkeypatch.setattr(extraction.requests, "post", fake_post)

    long_text = "A" * (extraction.MAX_INPUT_CHARACTERS + 500)
    extraction.extract_relationships(long_text)

    assert len(captured["prompt"]) < (
        extraction.MAX_INPUT_CHARACTERS + 2_000
    )
