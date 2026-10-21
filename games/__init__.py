"""Game package: each module exposes one concrete :class:`BaseGame` subclass."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from base_game import BaseGame

from games.breakout import BreakoutGame
from games.memory import MemoryGame
from games.platformer import PlatformerGame
from games.snake import SnakeGame
from games.space_shooter import SpaceShooterGame
from games.tictactoe import TicTacToeGame

#: Ordered registry used by the main menu. Each entry is a BaseGame subclass.
GAME_CLASSES: list[type[BaseGame]] = [
    SnakeGame,
    TicTacToeGame,
    MemoryGame,
    PlatformerGame,
    SpaceShooterGame,
    BreakoutGame,
]

__all__ = [
    "GAME_CLASSES",
    "SnakeGame",
    "TicTacToeGame",
    "MemoryGame",
    "PlatformerGame",
    "SpaceShooterGame",
    "BreakoutGame",
]
