#!/usr/bin/env python3
"""Python Game Hub - entry point.

Initialises pygame, loads settings and the high score database, then
starts the main menu loop. Every game is registered in ``games.GAME_CLASSES``.
"""

from __future__ import annotations

import sys

import pygame

import config
from games import GAME_CLASSES
from menu import MainMenu
from utils import HighScoreStore, load_settings, save_settings


def main() -> int:
    """Boot the hub; return a process exit code."""
    pygame.init()
    pygame.display.set_caption(config.SCREEN_TITLE)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    settings = load_settings()
    highscores = HighScoreStore()

    try:
        menu = MainMenu(screen, clock, GAME_CLASSES, settings, highscores)
        menu.run()
    finally:
        save_settings(settings)
        highscores.close()
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
