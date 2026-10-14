from unittest.mock import patch

from app.ui import summary


def test_clear_document_specific_state_clears_summary_and_audio():
    fake_state = {
        "summary_result": {
            "document_id": 6,
            "summary": "Old summary",
        },
        "summary_audio": b"old-audio",
        "summary_audio_document_id": 6,
    }

    with patch.object(summary.st, "session_state", fake_state):
        summary._clear_document_specific_state()

    assert fake_state["summary_result"] is None
    assert fake_state["summary_audio"] is None
    assert fake_state["summary_audio_document_id"] is None


def test_render_summary_audio_only_for_matching_document():
    fake_state = {
        "summary_audio": b"audio-for-document-6",
        "summary_audio_document_id": 6,
    }

    with (
        patch.object(summary.st, "session_state", fake_state),
        patch.object(summary.st, "markdown") as mock_markdown,
        patch.object(summary.st, "audio") as mock_audio,
    ):
        summary._render_summary_audio(document_id=7)

    mock_audio.assert_not_called()
    mock_markdown.assert_not_called()