"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from utils import HighScoreStore, Settings


@pytest.fixture
def settings() -> Settings:
    """A default Settings instance."""
    return Settings()


@pytest.fixture
def store(tmp_path) -> Iterator[HighScoreStore]:
    """An isolated HighScoreStore backed by a temp SQLite file."""
    s = HighScoreStore(tmp_path / "test.db")
    yield s
    s.close()
