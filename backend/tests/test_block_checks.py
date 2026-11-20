from scripts import block_checks


def test_the_checks_run_in_order_and_stop_at_the_first_failure(monkeypatch):
    calls = []

    def fake_call(command, env=None):
        calls.append(command[-1])
        return 3 if command[-1] == "-rxX" else 0

    monkeypatch.setattr(block_checks.subprocess, "call", fake_call)
    monkeypatch.setattr(block_checks, "bootstrap_environment", lambda: {})

    assert block_checks.main() == 3
    assert calls == [".", "scripts/prepare_test_database.py", "-rxX"]


def test_only_the_development_database_is_touched(monkeypatch):
    monkeypatch.setattr(
        block_checks.settings, "MIGRATION_DATABASE_URL", "postgresql+psycopg://a:b@db.example:5432/prod"
    )
    monkeypatch.setattr(
        block_checks.settings, "DATABASE_URL", "postgresql+psycopg://c:d@db.example:5432/prod"
    )
    assert block_checks.bootstrap_environment() is None
