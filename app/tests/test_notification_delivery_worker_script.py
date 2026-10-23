
from types import SimpleNamespace

from app.scripts import notification_delivery_worker as worker


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_worker_runs_without_smtp_configuration(monkeypatch, caplog):
    caplog.set_level("INFO")
    monkeypatch.setattr(
        worker,
        "parse_args",
        lambda: SimpleNamespace(
            watch=False,
            interval_seconds=30,
            batch_size=25,
        ),
    )
    monkeypatch.setattr(worker, "SessionLocal", FakeSession)
    monkeypatch.setattr(
        worker,
        "process_due_notifications",
        lambda db, batch_size: {"claimed": 0, "sent": 0},
    )

    assert worker.main() == 0

    assert "Notification worker results" in caplog.text
