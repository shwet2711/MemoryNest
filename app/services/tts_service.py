from __future__ import annotations

import os
import tempfile
from pathlib import Path


DEFAULT_SPEECH_RATE = 165
DEFAULT_VOLUME = 1.0


def _validate_text(text: str) -> None:
    if not isinstance(text, str):
        raise ValueError("text must be a string.")

    if not text.strip():
        raise ValueError("text cannot be empty.")


def _validate_rate(rate: int) -> None:
    if not isinstance(rate, int):
        raise ValueError("rate must be an integer.")

    if rate < 80 or rate > 300:
        raise ValueError(
            "rate must be between 80 and 300."
        )


def _validate_volume(volume: float) -> None:
    if not isinstance(volume, (int, float)):
        raise ValueError(
            "volume must be a number."
        )

    if volume < 0.0 or volume > 1.0:
        raise ValueError(
            "volume must be between 0.0 and 1.0."
        )


def _create_engine():
    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError(
            "pyttsx3 is not installed. "
            "Run: python -m pip install pyttsx3"
        ) from exc

    try:
        return pyttsx3.init()
    except Exception as exc:
        raise RuntimeError(
            "Unable to initialize the local text-to-speech engine."
        ) from exc


def generate_speech_audio(
    *,
    text: str,
    rate: int = DEFAULT_SPEECH_RATE,
    volume: float = DEFAULT_VOLUME,
) -> bytes:
    """
    Convert text into a WAV audio file using the
    local operating-system speech engine.

    The generated audio is returned as bytes so the
    Streamlit UI can play it directly.
    """

    _validate_text(text)
    _validate_rate(rate)
    _validate_volume(volume)

    engine = _create_engine()

    temp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name

        engine.setProperty(
            "rate",
            rate,
        )

        engine.setProperty(
            "volume",
            float(volume),
        )

        engine.save_to_file(
            text.strip(),
            temp_path,
        )

        engine.runAndWait()

        audio_path = Path(temp_path)

        if not audio_path.exists():
            raise RuntimeError(
                "The text-to-speech engine did not create the audio file."
            )

        audio_bytes = audio_path.read_bytes()

        if not audio_bytes:
            raise RuntimeError(
                "The generated audio file is empty."
            )

        return audio_bytes

    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise

        raise RuntimeError(
            "Unable to generate speech audio."
        ) from exc

    finally:
        try:
            engine.stop()
        except Exception:
            pass

        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass