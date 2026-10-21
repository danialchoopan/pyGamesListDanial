"""Shared utilities for the Game Hub.

Provides:
- Settings persistence (JSON file with defaults fallback)
- High score storage (SQLite)
- Small pygame helpers used by every game (fonts, text drawing, clamping)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pygame

import config

# --------------------------------------------------------------------------
# Settings management
# --------------------------------------------------------------------------


@dataclass
class Settings:
    """User-editable application settings, persisted as JSON."""

    music_volume: float = config.DEFAULT_MUSIC_VOLUME
    sfx_volume: float = config.DEFAULT_SFX_VOLUME
    fullscreen: bool = False
    show_fps: bool = False

    def clamp(self) -> Settings:
        """Return a copy with volumes bounded to the valid range."""
        return Settings(
            music_volume=max(config.MIN_VOLUME, min(config.MAX_VOLUME, self.music_volume)),
            sfx_volume=max(config.MIN_VOLUME, min(config.MAX_VOLUME, self.sfx_volume)),
            fullscreen=self.fullscreen,
            show_fps=self.show_fps,
        )


def load_settings(path: Path = config.SETTINGS_FILE) -> Settings:
    """Load settings from *path*, falling back to defaults on any error."""
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # OSError = file missing/unreadable; JSONDecodeError = corrupt file.
        # Either way we silently fall back to factory defaults.
        return Settings()
    # Only forward keys that match a known field so a settings file written by
    # an older/newer version (with extra keys) can't crash construction.
    known = {f for f in Settings.__dataclass_fields__}
    return Settings(**{k: v for k, v in raw.items() if k in known}).clamp()


def save_settings(settings: Settings, path: Path = config.SETTINGS_FILE) -> None:
    """Persist *settings* to *path* as JSON, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings.clamp()), indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# High score storage (SQLite)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HighScore:
    """A single high score entry."""

    game: str
    name: str
    score: int


class HighScoreStore:
    """SQLite-backed store for per-game high scores.

    Usage::

        store = HighScoreStore()          # uses config.HIGHSCORES_DB
        store.add_score("snake", "DAN", 420)
        top = store.top_scores("snake", limit=5)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else config.HIGHSCORES_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS highscores (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                game    TEXT NOT NULL,
                name    TEXT NOT NULL,
                score   INTEGER NOT NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.execute(
            # Composite index on (game, score DESC) makes the frequent
            # "top N for a game" queries in top_scores() a fast index-only
            # scan instead of a full table sort.
            "CREATE INDEX IF NOT EXISTS idx_hs_game ON highscores (game, score DESC)"
        )
        self._conn.commit()

    def add_score(self, game: str, name: str, score: int) -> None:
        """Insert a score. Empty names are stored as 'AAA'."""
        clean_name = (name.strip() or "AAA")[:12].upper()
        self._conn.execute(
            "INSERT INTO highscores (game, name, score) VALUES (?, ?, ?)",
            (game, clean_name, int(score)),
        )
        self._conn.commit()

    def top_scores(self, game: str, limit: int = 5) -> list[HighScore]:
        """Return the highest scores for *game*, best first."""
        rows = self._conn.execute(
            "SELECT game, name, score FROM highscores "
            "WHERE game = ? ORDER BY score DESC, created ASC LIMIT ?",
            (game, int(limit)),
        ).fetchall()
        return [HighScore(game=r["game"], name=r["name"], score=r["score"]) for r in rows]

    def best_score(self, game: str) -> int:
        """Return the best score for *game*, or 0 if none recorded."""
        row = self._conn.execute(
            "SELECT MAX(score) AS best FROM highscores WHERE game = ?", (game,)
        ).fetchone()
        return int(row["best"]) if row and row["best"] is not None else 0

    def is_top_n(self, game: str, score: int, limit: int = 5) -> bool:
        """Return True when *score* would crack the top *limit* for *game*."""
        if score <= 0:
            return False  # zero/negative scores never qualify
        scores = self.top_scores(game, limit=limit)
        if len(scores) < limit:
            return True  # board isn't full yet, so any positive score gets in
        # Board is full: only beat the current last-place score.
        return score > scores[-1].score

    def clear(self, game: str | None = None) -> None:
        """Delete all scores, or only those for *game* when given."""
        if game is None:
            self._conn.execute("DELETE FROM highscores")
        else:
            self._conn.execute("DELETE FROM highscores WHERE game = ?", (game,))
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> HighScoreStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# --------------------------------------------------------------------------
# pygame helpers
# --------------------------------------------------------------------------

_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Return a cached font of the given *size*.

    Building a Font object is relatively expensive, so we cache one per
    (size, bold) pair and reuse it across frames and games.
    """
    key = (size, bold)
    if key not in _FONT_CACHE:
        font = pygame.font.SysFont(config.FONT_NAME, size, bold=bold)
        _FONT_CACHE[key] = font
    return _FONT_CACHE[key]


def draw_text(
    surface: pygame.Surface,
    text: str,
    size: int,
    color: config.Color,
    center: tuple[int, int] | None = None,
    topleft: tuple[int, int] | None = None,
    bold: bool = False,
) -> pygame.Rect:
    """Render *text* onto *surface* at *center* or *topleft*; return its rect."""
    rendered = get_font(size, bold).render(text, True, color)
    rect = rendered.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    surface.blit(rendered, rect)
    return rect


def clamp(value: float, low: float, high: float) -> float:
    """Constrain *value* to the inclusive range [*low*, *high*]."""
    return max(low, min(high, value))


def format_score(score: int) -> str:
    """Format an integer score with thousands separators."""
    return f"{score:,}"


def format_timer(seconds: float) -> str:
    """Format *seconds* as an M:SS string."""
    total = max(0, int(seconds))
    return f"{total // 60}:{total % 60:02d}"
