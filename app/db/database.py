from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
    }


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)