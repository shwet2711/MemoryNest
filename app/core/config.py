import os
from pathlib import Path

from dotenv import load_dotenv


# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")


APP_NAME = os.getenv("APP_NAME", "MemoryNest")
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./data/memorynest.db"
)

UPLOAD_DIRECTORY = os.getenv(
    "UPLOAD_DIRECTORY",
    "./data/uploads"
)

PROCESSED_DIRECTORY = os.getenv(
    "PROCESSED_DIRECTORY",
    "./data/processed"
)

CHROMA_PERSIST_DIRECTORY = os.getenv(
    "CHROMA_PERSIST_DIRECTORY",
    "./data/chroma"
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    ""
)