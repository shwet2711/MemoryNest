from unittest.mock import MagicMock, patch

import pytest

from app.services.tts_service import (
    generate_speech_audio,
)


def test_generate_speech_audio_rejects_empty_text():
    with pytest.raises(ValueError):
        generate_speech_audio(
            text=""
        )


def test_generate_speech_audio_rejects_invalid_rate():
    with pytest.raises(ValueError):
        generate_speech_audio(
            text="Hello MemoryNest.",
            rate=50,
        )


def test_generate_speech_audio_rejects_invalid_volume():
    with pytest.raises(ValueError):
        generate_speech_audio(
            text="Hello MemoryNest.",
            volume=2.0,
        )


def test_generate_speech_audio_returns_bytes():
    fake_engine = MagicMock()

    def fake_save_to_file(
        text,
        path,
    ):
        with open(path, "wb") as audio_file:
            audio_file.write(
                b"fake-wav-audio-data"
            )

    fake_engine.save_to_file.side_effect = (
        fake_save_to_file
    )

    with patch(
        "app.services.tts_service._create_engine",
        return_value=fake_engine,
    ):
        result = generate_speech_audio(
            text="MemoryNest is working.",
        )

    assert isinstance(result, bytes)
    assert result == b"fake-wav-audio-data"

    fake_engine.setProperty.assert_any_call(
        "rate",
        165,
    )

    fake_engine.setProperty.assert_any_call(
        "volume",
        1.0,
    )

    fake_engine.runAndWait.assert_called_once()
    fake_engine.stop.assert_called_once()


def test_generate_speech_audio_uses_custom_settings():
    fake_engine = MagicMock()

    def fake_save_to_file(
        text,
        path,
    ):
        with open(path, "wb") as audio_file:
            audio_file.write(
                b"custom-audio"
            )

    fake_engine.save_to_file.side_effect = (
        fake_save_to_file
    )

    with patch(
        "app.services.tts_service._create_engine",
        return_value=fake_engine,
    ):
        result = generate_speech_audio(
            text="Custom speech settings.",
            rate=190,
            volume=0.7,
        )

    assert result == b"custom-audio"

    fake_engine.setProperty.assert_any_call(
        "rate",
        190,
    )

    fake_engine.setProperty.assert_any_call(
        "volume",
        0.7,
    )


def test_generate_speech_audio_handles_engine_failure():
    fake_engine = MagicMock()

    fake_engine.runAndWait.side_effect = (
        RuntimeError("Speech engine failed")
    )

    with patch(
        "app.services.tts_service._create_engine",
        return_value=fake_engine,
    ):
        with pytest.raises(RuntimeError):
            generate_speech_audio(
                text="MemoryNest test.",
            )