
import sys

from app.scripts.dev_launcher import build_commands


def test_build_commands_starts_all_three_processes():
    commands = build_commands()

    assert [name for name, _ in commands] == [
        "Knowledge Graph worker",
        "Notification delivery worker",
        "Streamlit",
    ]


def test_notification_worker_runs_continuously():
    commands = dict(build_commands())
    command = commands["Notification delivery worker"]

    assert command[0] == sys.executable
    assert command[1:3] == [
        "-m",
        "app.scripts.notification_delivery_worker",
    ]
    assert "--watch" in command
    assert command[command.index("--interval-seconds") + 1] == "30"
    assert command[command.index("--batch-size") + 1] == "25"
