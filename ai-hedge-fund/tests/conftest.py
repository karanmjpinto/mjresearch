"""Shared fixtures.

The run store and methodology memory both persist to the application database.
Tests must never touch the real book, so `isolated_db` swaps in a temporary
SQLite file and rebinds the session factory each module imported at load time.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hedge_fund.db.session import Base


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the run store and memory at a throwaway database."""
    import hedge_fund.agents.memory as memory
    import hedge_fund.runs.store as store
    from hedge_fund.db import models  # noqa: F401  (register tables)

    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # These names were bound at import time, so patch them where they are used.
    monkeypatch.setattr(store, "SessionLocal", factory)
    monkeypatch.setattr(store, "_ensure_schema", lambda: None)
    monkeypatch.setattr(memory, "SessionLocal", factory)
    monkeypatch.setattr(memory, "_ensure_schema", lambda: None)

    yield factory

    engine.dispose()
