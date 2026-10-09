
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


# Optional Neo4j knowledge graph configuration.
NEO4J_ENABLED = os.getenv(
    "NEO4J_ENABLED",
    "False",
).strip().lower() in {"true", "1", "yes", "on"}

NEO4J_URI = os.getenv(
    "NEO4J_URI",
    "bolt://localhost:7687",
).strip()

NEO4J_USERNAME = os.getenv(
    "NEO4J_USERNAME",
    "neo4j",
).strip()

NEO4J_PASSWORD = os.getenv(
    "NEO4J_PASSWORD",
    "",
)

NEO4J_DATABASE = os.getenv(
    "NEO4J_DATABASE",
    "neo4j",
).strip()


if NEO4J_ENABLED:
    if not NEO4J_URI:
        raise ValueError(
            "NEO4J_URI is required when Neo4j is enabled."
        )

    if not NEO4J_USERNAME:
        raise ValueError(
            "NEO4J_USERNAME is required when Neo4j is enabled."
        )

    if not NEO4J_PASSWORD:
        raise ValueError(
            "NEO4J_PASSWORD is required when Neo4j is enabled."
        )

    if not NEO4J_DATABASE:
        raise ValueError(
            "NEO4J_DATABASE is required when Neo4j is enabled."
        )


# Make sure required local directories exist.
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
PROCESSED_DIRECTORY.mkdir(parents=True, exist_ok=True)
CHROMA_PERSIST_DIRECTORY.mkdir(parents=True, exist_ok=True)
