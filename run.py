#!/usr/bin/env python3
"""Friendly command-line launcher for the Game Hub.

``main.py`` boots straight into the interactive menu. This wrapper sits in
front of it so you can also drive the hub from a shell::

    python run.py                    # boot the hub menu (same as main.py)
    python run.py --list             # list the games and exit (no window)
    python run.py --game snake       # jump straight into Snake
    python run.py --game "Breakout"  # names are matched case-insensitively

Games are looked up in :data:`games.GAME_CLASSES` by their ``score_key`` or
``name``, so the launcher never drifts out of sync with the registry.
"""

from __future__ import annotations

import argparse
import sys

import pygame

import config
from base_game import BaseGame
from games import GAME_CLASSES
from menu import MainMenu
from utils import HighScoreStore, load_settings, save_settings


def build_parser(games: list[type[BaseGame]] | None = None) -> argparse.ArgumentParser:
    """Create the CLI parser. *games* is injectable so tests can pass a stub."""
    catalogue = games if games is not None else GAME_CLASSES
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Launch the Python Game Hub, or one of its games directly.",
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="list the available games (by key and name) and exit",
    )
    parser.add_argument(
        "-g", "--game",
        metavar="NAME",
        help="launch a single game by key or name, skipping the menu "
             f"(keys: {', '.join(cls.score_key for cls in catalogue)})",
    )
    return parser


def find_game(name: str, games: list[type[BaseGame]] | None = None) -> type[BaseGame] | None:
    """Resolve *name* (key or display name, case-insensitive) to a game class.

    Returns ``None`` when nothing matches; the caller decides how to report it.
    """
    catalogue = games if games is not None else GAME_CLASSES
    needle = name.strip().casefold()
    for game_cls in catalogue:
        if game_cls.score_key.casefold() == needle or game_cls.name.casefold() == needle:
            return game_cls
    return None


def list_games(games: list[type[BaseGame]] | None = None) -> str:
    """Render the game catalogue as aligned, human-readable text."""
    catalogue = games if games is not None else GAME_CLASSES
    width = max(len(cls.score_key) for cls in catalogue)
    lines = [f"{cls.score_key:<{width}}  {cls.name} - {cls.description}"
             for cls in catalogue]
    return "\n".join(lines)


def run_menu() -> int:
    """Boot pygame and enter the interactive menu; return an exit code."""
    pygame.init()
    pygame.display.set_caption(config.SCREEN_TITLE)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    settings = load_settings()
    highscores = HighScoreStore()

    # try/finally guarantees settings are saved and the DB closed even if a
    # game raises, so nothing is left locked or half-written.
    try:
        MainMenu(screen, clock, GAME_CLASSES, settings, highscores).run()
    finally:
        save_settings(settings)
        highscores.close()
        pygame.quit()
    return 0


def run_single(game_cls: type[BaseGame]) -> int:
    """Boot pygame and hand control straight to *game_cls*; return an exit code."""
    pygame.init()
    pygame.display.set_caption(game_cls.name)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    settings = load_settings()
    highscores = HighScoreStore()

    try:
        game = game_cls(screen=screen, clock=clock, settings=settings, highscores=highscores)
        game.run()  # returns when the player presses ESC in-game
    finally:
        save_settings(settings)
        highscores.close()
        pygame.quit()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch; return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # --list never opens a window, so it works headless (CI, ssh, etc.).
    if args.list:
        print(list_games())
        return 0

    if args.game:
        game_cls = find_game(args.game)
        if game_cls is None:
            parser.error(
                f"unknown game {args.game!r}; available: "
                f"{', '.join(cls.score_key for cls in GAME_CLASSES)}"
            )
        return run_single(game_cls)

    return run_menu()


if __name__ == "__main__":
    sys.exit(main())
