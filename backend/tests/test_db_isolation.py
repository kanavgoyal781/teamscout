"""DATABASE_URL must be in-memory during pytest (conftest force-override)."""

from app.db import session as db_session


def test_pytest_uses_memory_database() -> None:
    assert ":memory:" in db_session.DATABASE_URL
