from app.scripts import knowledge_graph_worker as cli


def test_worker_refuses_to_run_when_neo4j_is_disabled(monkeypatch):
    monkeypatch.setattr(cli, "NEO4J_ENABLED", False)

    def unexpected_init():
        raise AssertionError("Database initialization should not run.")

    monkeypatch.setattr(cli, "init_database", unexpected_init)

    assert cli.run_worker(once=True) == 2


def test_once_mode_initializes_database_and_processes_one_batch(monkeypatch):
    calls = []

    monkeypatch.setattr(cli, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        cli, "init_database", lambda: calls.append("initialized")
    )
    monkeypatch.setattr(
        cli,
        "process_due_jobs",
        lambda *, limit: calls.append(("processed", limit)) or 3,
    )

    result = cli.run_worker(once=True, batch_size=4)

    assert result == 0
    assert calls == ["initialized", ("processed", 4)]


def test_continuous_mode_stops_cleanly_on_keyboard_interrupt(monkeypatch):
    calls = []

    monkeypatch.setattr(cli, "NEO4J_ENABLED", True)
    monkeypatch.setattr(
        cli, "init_database", lambda: calls.append("initialized")
    )
    monkeypatch.setattr(
        cli,
        "process_due_jobs",
        lambda *, limit: calls.append(("processed", limit)) or 0,
    )

    def stop_worker(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", stop_worker)

    result = cli.run_worker(
        once=False,
        poll_interval=1,
        batch_size=2,
    )

    assert result == 0
    assert calls == ["initialized", ("processed", 2)]


def test_cli_rejects_invalid_batch_size():
    parser = cli.build_parser()

    try:
        parser.parse_args(["--batch-size", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected invalid batch size to be rejected.")
