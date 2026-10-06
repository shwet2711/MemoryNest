from sqlalchemy import inspect, text

from app.db.database import engine


def add_column_if_missing(
    table_name: str,
    column_name: str,
    column_definition: str,
) -> bool:
    inspector = inspect(engine)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    if column_name in existing_columns:
        return False

    with engine.begin() as connection:
        connection.execute(
            text(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} "
                f"{column_definition}"
            )
        )

    return True


def run_migrations() -> None:
    """Run lightweight SQLite-compatible schema migrations."""

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "document_chunks" in tables:
        add_column_if_missing(
            "document_chunks",
            "page_number",
            "INTEGER",
        )

        add_column_if_missing(
            "document_chunks",
            "extraction_method",
            "VARCHAR(30) NOT NULL DEFAULT 'text'",
        )

    if "conversations" in tables:
        add_column_if_missing(
            "conversations",
            "document_id",
            "INTEGER",
        )