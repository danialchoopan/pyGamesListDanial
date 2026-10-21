"""Tests for the ``run.py`` command-line launcher.

The pure-logic parts (game lookup, catalogue rendering, argument parsing) are
tested directly; they need no display. ``--list`` is exercised end-to-end
because it must work headless (CI, ssh) without opening a window.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import run
from games import GAME_CLASSES
from games.breakout import BreakoutGame
from games.memory import MemoryGame
from games.snake import SnakeGame
from games.space_shooter import SpaceShooterGame
from games.tictactoe import TicTacToeGame

REPO = Path(__file__).resolve().parent.parent


def test_find_game_matches_score_key() -> None:
    assert run.find_game("snake") is SnakeGame
    assert run.find_game("space_shooter") is SpaceShooterGame


def test_find_game_matches_display_name() -> None:
    assert run.find_game("Breakout") is BreakoutGame
    assert run.find_game("Memory Cards") is MemoryGame
    assert run.find_game("Space Shooter") is SpaceShooterGame


def test_find_game_is_case_and_whitespace_insensitive() -> None:
    assert run.find_game("SNAKE") is SnakeGame
    assert run.find_game("  tictactoe  ") is TicTacToeGame


def test_find_game_unknown_returns_none() -> None:
    assert run.find_game("nonexistent") is None
    assert run.find_game("") is None


def test_find_game_respects_injected_catalogue() -> None:
    stub = type("Stub", (), {"score_key": "stub", "name": "Stub", "description": ""})()
    cls = type(stub)
    assert run.find_game("stub", games=[cls]) is cls
    assert run.find_game("snake", games=[cls]) is None


def test_list_games_covers_every_registered_game() -> None:
    text = run.list_games()
    for game_cls in GAME_CLASSES:
        assert game_cls.score_key in text
        assert game_cls.name in text


def test_build_parser_defaults() -> None:
    args = run.build_parser().parse_args([])
    assert args.list is False
    assert args.game is None


def test_build_parser_accepts_short_and_long_flags() -> None:
    parser = run.build_parser()
    assert parser.parse_args(["-l"]).list is True
    assert parser.parse_args(["--list"]).list is True
    assert parser.parse_args(["-g", "snake"]).game == "snake"
    assert parser.parse_args(["--game", "breakout"]).game == "breakout"


def test_main_list_prints_catalogue_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert run.main(["--list"]) == 0
    out = capsys.readouterr().out
    for game_cls in GAME_CLASSES:
        assert game_cls.score_key in out


def test_main_unknown_game_exits_with_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        run.main(["--game", "nope"])
    assert excinfo.value.code == 2  # argparse error code


def test_main_list_works_headless_in_subprocess() -> None:
    """--list must not require a display, so run it in a bare subprocess."""
    result = subprocess.run(
        [sys.executable, "run.py", "--list"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={"PATH": "/usr/bin:/bin", "SDL_VIDEODRIVER": "dummy",
             "SDL_AUDIODRIVER": "dummy", "PYTHONPATH": str(REPO)},
        timeout=60,
    )
    assert result.returncode == 0
    for game_cls in GAME_CLASSES:
        assert game_cls.score_key in result.stdout
