import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


APP_NAME = os.getenv("APP_NAME", "MemoryNest")
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'data' / 'memorynest.db'}",
)


UPLOAD_DIRECTORY = BASE_DIR / os.getenv(
    "UPLOAD_DIRECTORY",
    "data/uploads",
)

PROCESSED_DIRECTORY = BASE_DIR / os.getenv(
    "PROCESSED_DIRECTORY",
    "data/processed",
)

CHROMA_PERSIST_DIRECTORY = BASE_DIR / os.getenv(
    "CHROMA_PERSIST_DIRECTORY",
    "data/chroma",
)


OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "",
)


RAG_GROUNDING_DISTANCE = float(
    os.getenv(
        "MEMORYNEST_RAG_GROUNDING_DISTANCE",
        "0.65",
    )
)


if RAG_GROUNDING_DISTANCE < 0:
    raise ValueError(
        "MEMORYNEST_RAG_GROUNDING_DISTANCE cannot be negative."
    )


# Make sure required directories exist
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
PROCESSED_DIRECTORY.mkdir(parents=True, exist_ok=True)
CHROMA_PERSIST_DIRECTORY.mkdir(parents=True, exist_ok=True)