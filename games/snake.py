"""Snake game.

Grid-based snake: eat food to grow, avoid walls and yourself.
Game logic lives in :class:`SnakeLogic` so it can be unit-tested
without a display.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from enum import Enum

import pygame

import config
from base_game import BaseGame


class Direction(Enum):
    """Cardinal movement directions."""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


#: Direction that cannot immediately follow its opposite (no 180-degree turns).
_OPPOSITES: dict[Direction, Direction] = {
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}

Cell = tuple[int, int]


class SnakeLogic:
    """Pure game state for Snake, decoupled from pygame."""

    def __init__(self, grid_size: int = config.SNAKE_GRID_SIZE, rng: random.Random | None = None) -> None:
        self.grid_size = grid_size
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        """Reset the board: 3-length snake in the middle, one food item."""
        mid = self.grid_size // 2
        self.snake: list[Cell] = [(mid, i) for i in range(2, -1, -1)]
        self.direction: Direction = Direction.RIGHT
        self._queued: Direction | None = None
        self.grow_pending: int = 0
        self.score: int = 0
        self.alive: bool = True
        self.food: Cell = self._spawn_food()

    def _spawn_food(self) -> Cell:
        """Place food on a random free cell."""
        occupied = set(self.snake)
        free = [
            (x, y)
            for x in range(self.grid_size)
            for y in range(self.grid_size)
            if (x, y) not in occupied
        ]
        return self.rng.choice(free) if free else (0, 0)

    def queue_direction(self, direction: Direction) -> None:
        """Queue a turn, ignoring reversals of the current heading."""
        # Compare against the direction we're *actually* heading (a pending
        # turn counts), so two rapid key presses in one tick can't reverse the
        # snake into its own neck. Only the last legal turn is kept.
        target = self.direction if self._queued is None else self._queued
        if direction != target and _OPPOSITES.get(target) != direction:
            self._queued = direction

    def step(self) -> None:
        """Advance one tick; ends the game on collision."""
        if not self.alive:
            return
        if self._queued is not None:
            self.direction = self._queued
            self._queued = None
        dx, dy = self.direction.value
        head_x, head_y = self.snake[0]
        new_head: Cell = (head_x + dx, head_y + dy)

        # Wall collision
        if not (0 <= new_head[0] < self.grid_size and 0 <= new_head[1] < self.grid_size):
            self.alive = False
            return
        # Self collision. When we're NOT growing, the tail cell will vacate
        # this same tick, so sliding into the current tail position is legal -
        # hence we exclude the tail from the collision set in that case.
        body = self.snake[:-1] if self.grow_pending == 0 else self.snake
        if new_head in body:
            self.alive = False
            return

        # Prepend the new head, then either consume a queued growth (keep the
        # tail) or pop the tail to maintain a constant length.
        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 10
            self.grow_pending += 1  # grow one cell on a later tick
            self.food = self._spawn_food()
        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.snake.pop()

    @property
    def filled_cells(self) -> int:
        """Total cells on the board (grid_size x grid_size)."""
        return self.grid_size * self.grid_size


class SnakeGame(BaseGame):
    """Playable Snake with rendering and input."""

    name = "Snake"
    description = "Eat food, grow, don't hit walls or yourself"
    score_key = "snake"
    fps = config.SNAKE_FPS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        cell = config.SNAKE_CELL_SIZE
        self.cell = cell
        self.logic = SnakeLogic()
        # Centre the grid inside the screen below the HUD bar
        board_px = cell * self.logic.grid_size
        self.origin_x = (config.SCREEN_WIDTH - board_px) // 2
        self.origin_y = 40 + (config.SCREEN_HEIGHT - 40 - board_px) // 2
        self.game_over = False

    def reset(self) -> None:
        super().reset()
        self.logic.reset()
        self.score = 0
        self.game_over = False

    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if self.game_over and event.key == pygame.K_r:
                    self.reset()
                elif not self.game_over:
                    key_map = {
                        pygame.K_UP: Direction.UP,
                        pygame.K_w: Direction.UP,
                        pygame.K_DOWN: Direction.DOWN,
                        pygame.K_s: Direction.DOWN,
                        pygame.K_LEFT: Direction.LEFT,
                        pygame.K_a: Direction.LEFT,
                        pygame.K_RIGHT: Direction.RIGHT,
                        pygame.K_d: Direction.RIGHT,
                    }
                    if event.key in key_map:
                        self.logic.queue_direction(key_map[event.key])
        return True

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        self.logic.step()
        self.score = self.logic.score
        if not self.logic.alive:
            self.game_over = True
            if self.highscores.is_top_n(self.score_key, self.score):
                self.submit_score()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.SNAKE_BG)
        grid = self.logic.grid_size
        # Grid lines
        for i in range(grid + 1):
            x = self.origin_x + i * self.cell
            y = self.origin_y + i * self.cell
            pygame.draw.line(surface, config.SNAKE_GRID, (x, self.origin_y), (x, self.origin_y + grid * self.cell))
            pygame.draw.line(surface, config.SNAKE_GRID, (self.origin_x, y), (self.origin_x + grid * self.cell, y))

        def cell_rect(cx: int, cy: int) -> pygame.Rect:
            return pygame.Rect(
                self.origin_x + cx * self.cell,
                self.origin_y + cy * self.cell,
                self.cell,
                self.cell,
            )

        # Food
        pygame.draw.ellipse(surface, config.SNAKE_FOOD, cell_rect(*self.logic.food).inflate(-4, -4))
        # Snake body + head.
        # self.logic.snake is ordered head-first, so we iterate reversed() to
        # draw tail->head (head ends up on top). In that reversed order the
        # head is the LAST item, i.e. index len-1, which is what we test below.
        for i, (cx, cy) in enumerate(reversed(self.logic.snake)):
            color = config.SNAKE_HEAD if i == len(self.logic.snake) - 1 else config.SNAKE_BODY
            pygame.draw.rect(surface, color, cell_rect(cx, cy).inflate(-2, -2), border_radius=4)

        self.draw_hud(
            surface,
            f"Score: {self.score}",
            f"Best: {self.best_score}",
            f"Length: {len(self.logic.snake)}",
        )
        if self.game_over:
            self.draw_game_over(surface)
