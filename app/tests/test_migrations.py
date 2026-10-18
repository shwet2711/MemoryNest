from sqlalchemy import create_engine, inspect, text

from app.db import migrations


def test_migrations_add_missing_columns_and_preserve_data(
    monkeypatch, tmp_path
):
    """Upgrade a legacy SQLite schema without losing existing records."""

    database_path = tmp_path / "legacy_memorynest.db"
    test_engine = create_engine(f"sqlite:///{database_path}")

    try:
        with test_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE documents (
                        id INTEGER PRIMARY KEY,
                        filename VARCHAR(255)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO documents (id, filename)
                    VALUES (1, 'existing.pdf')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE document_chunks (
                        id INTEGER PRIMARY KEY,
                        content TEXT
                    )
                    """
                )
            )
            connection.execute(
                text("CREATE TABLE conversations (id INTEGER PRIMARY KEY)")
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE detected_events (
                        id INTEGER PRIMARY KEY,
                        title VARCHAR(255)
                    )
                    """
                )
            )

        monkeypatch.setattr(migrations, "engine", test_engine)

        migrations.run_migrations()

        inspector = inspect(test_engine)
        expected_columns = {
            "documents": {"extraction_method", "ocr_confidence"},
            "document_chunks": {"page_number", "extraction_method"},
            "conversations": {"document_id"},
            "detected_events": {"event_end_date", "date_confidence"},
        }

        for table_name, expected in expected_columns.items():
            actual = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            assert expected.issubset(actual), (
                f"Missing columns in {table_name}: {expected - actual}"
            )

        with test_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT id, filename, extraction_method "
                    "FROM documents WHERE id = 1"
                )
            ).one()

            assert row.id == 1
            assert row.filename == "existing.pdf"
            assert row.extraction_method == "text"

            assert connection.execute(
                text("SELECT COUNT(*) FROM detected_events")
            ).scalar_one() == 0

        # Re-running migrations must not attempt to add existing columns.
        migrations.run_migrations()

    finally:
        test_engine.dispose()
