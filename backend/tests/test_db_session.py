
from unittest.mock import Mock

import pytest

import app.db.session as database_session


def test_get_db_closes_session(monkeypatch):
    mock_session = Mock()

    monkeypatch.setattr(
        database_session,
        "SessionLocal",
        lambda: mock_session,
    )

    db_generator = database_session.get_db()

    yielded_session = next(db_generator)

    assert yielded_session is mock_session

    with pytest.raises(StopIteration):
        next(db_generator)

    mock_session.close.assert_called_once()

def test_get_db_closes_session_when_exception_occurs(monkeypatch):
    mock_session = Mock()

    monkeypatch.setattr(
        database_session,
        "SessionLocal",
        lambda: mock_session,
    )

    db_generator = database_session.get_db()

    yielded_session = next(db_generator)

    assert yielded_session is mock_session

    with pytest.raises(RuntimeError, match="Database operation failed"):
        db_generator.throw(RuntimeError("Database operation failed"))

    mock_session.close.assert_called_once()
