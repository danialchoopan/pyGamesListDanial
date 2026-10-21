"""Shared pytest fixtures.

The SDL environment variables are set *before* any test (or game module)
initialises pygame so the suite never touches a real audio or video device -
important both in CI (no display at all) and locally (no surprise beeps while
running ``pytest``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Must happen at import time: pygame reads these when the drivers first open.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from utils import HighScoreStore, Settings  # noqa: E402  (after env setup on purpose)


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
