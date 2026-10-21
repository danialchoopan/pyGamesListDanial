"""Snake game.

Grid-based snake: eat food to grow, avoid walls and yourself, and grab
power-ups for a temporary edge. Game logic lives in :class:`SnakeLogic`
so it can be unit-tested without a display.

Features
- Grid movement, wall + self collision
- Progressive speed-up as the score climbs (and a temporary speed boost)
- Power-ups: SPEED (faster movement) and INVINCIBILITY (pass through
  walls and yourself for a few steps)
- High-score persistence via the shared SQLite store
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import pygame

import config
from base_game import BaseGame
from utils import draw_text


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


class PowerType(Enum):
    """Collectible power-up kinds."""

    SPEED = "speed"            # temporary movement speed boost
    INVINCIBILITY = "invincible"  # temporary immunity to walls & self


@dataclass(frozen=True)
class PowerUp:
    """A single power-up sitting on the grid."""

    x: int
    y: int
    kind: PowerType

    @property
    def cell(self) -> Cell:
        """Grid cell occupied by this power-up."""
        return (self.x, self.y)


class SnakeLogic:
    """Pure game state for Snake, decoupled from pygame."""

    def __init__(
        self,
        grid_size: int = config.SNAKE_GRID_SIZE,
        rng: random.Random | None = None,
        powerup_chance: float = config.SNAKE_POWERUP_CHANCE,
    ) -> None:
        self.grid_size = grid_size
        self.rng = rng or random.Random()
        self.powerup_chance = powerup_chance
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
        # Power-up state must be initialised before spawning food, because
        # _spawn_food() consults the occupied cells (which include power-ups).
        self.powerup: PowerUp | None = None
        self._powerup_ttl: int = 0
        self.invincible_steps: int = 0  # remaining steps of immunity
        self.speed_boost_steps: int = 0  # remaining steps of speed boost
        self.food: Cell = self._spawn_food()

    # ------------------------------------------------------------------
    # Spawning helpers
    # ------------------------------------------------------------------
    def _occupied(self) -> set[Cell]:
        """Cells taken by the snake and any live power-up."""
        occ = set(self.snake)
        if self.powerup is not None:
            occ.add(self.powerup.cell)
        return occ

    def _free_for(self, exclude_food: bool = False) -> list[Cell]:
        """All empty cells, optionally also excluding the current food."""
        occ = self._occupied()
        if exclude_food:
            occ.add(self.food)
        return [
            (x, y)
            for x in range(self.grid_size)
            for y in range(self.grid_size)
            if (x, y) not in occ
        ]

    def _spawn_food(self) -> Cell:
        """Place food on a random free cell."""
        free = self._free_for()
        return self.rng.choice(free) if free else (0, 0)

    def _maybe_spawn_powerup(self) -> None:
        """Drop a power-up on a free cell with probability ``powerup_chance``."""
        if self.powerup is not None:
            return  # only one power-up at a time
        if self.rng.random() >= self.powerup_chance:
            return
        free = self._free_for(exclude_food=True)
        if not free:
            return
        x, y = self.rng.choice(free)
        kind = self.rng.choice(list(PowerType))
        self.powerup = PowerUp(x, y, kind)
        self._powerup_ttl = config.SNAKE_POWERUP_TTL

    def _collect_powerup(self) -> None:
        """Apply the effect of the power-up the head just moved onto."""
        if self.powerup is None:
            return
        self.score += config.SNAKE_POWERUP_SCORE
        if self.powerup.kind is PowerType.INVINCIBILITY:
            self.invincible_steps = config.SNAKE_INVINCIBILITY_STEPS
        else:
            self.speed_boost_steps = config.SNAKE_SPEED_STEPS
        self.powerup = None

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def queue_direction(self, direction: Direction) -> None:
        """Queue a turn, ignoring reversals of the current heading."""
        # Compare against the direction we're *actually* heading (a pending
        # turn counts), so two rapid key presses in one tick can't reverse the
        # snake into its own neck. Only the last legal turn is kept.
        target = self.direction if self._queued is None else self._queued
        if direction != target and _OPPOSITES.get(target) != direction:
            self._queued = direction

    def step(self) -> None:
        """Advance one tick; ends the game on collision (unless invincible)."""
        if not self.alive:
            return
        if self._queued is not None:
            self.direction = self._queued
            self._queued = None
        dx, dy = self.direction.value
        head_x, head_y = self.snake[0]
        nx, ny = head_x + dx, head_y + dy

        # Wall collision: wrap around while invincible, otherwise die.
        if not (0 <= nx < self.grid_size and 0 <= ny < self.grid_size):
            if self.invincible_steps > 0:
                nx %= self.grid_size
                ny %= self.grid_size
            else:
                self.alive = False
                return
        new_head: Cell = (nx, ny)

        # Self collision: ignored while invincible. Otherwise the tail cell
        # will vacate this same tick when we're not growing, so sliding into
        # the current tail position is legal - exclude it in that case.
        if self.invincible_steps == 0:
            body = self.snake[:-1] if self.grow_pending == 0 else self.snake
            if new_head in body:
                self.alive = False
                return

        # Prepend the new head.
        self.snake.insert(0, new_head)

        # Eat food -> grow + score, and maybe drop a power-up nearby.
        if new_head == self.food:
            self.score += 10
            self.grow_pending += 1  # grow one cell on a later tick
            self.food = self._spawn_food()
            self._maybe_spawn_powerup()

        # Eat a power-up -> apply its effect.
        if self.powerup is not None and new_head == self.powerup.cell:
            self._collect_powerup()

        # Consume a queued growth (keep the tail) or pop to hold length.
        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.snake.pop()

        # Tick down the power-up timers.
        if self.invincible_steps > 0:
            self.invincible_steps -= 1
        if self.speed_boost_steps > 0:
            self.speed_boost_steps -= 1
        if self.powerup is not None:
            self._powerup_ttl -= 1
            if self._powerup_ttl <= 0:
                self.powerup = None  # expired uncollected

    # ------------------------------------------------------------------
    # Speed
    # ------------------------------------------------------------------
    def effective_fps(
        self, base: int = config.SNAKE_FPS, max_fps: int = config.SNAKE_MAX_FPS
    ) -> int:
        """Frames-per-second for the current score and active boosts.

        The snake speeds up by 1 FPS for every ``SNAKE_SPEEDUP_INTERVAL``
        points (progressive difficulty), plus a temporary bump while the SPEED
        power-up is active - capped at ``max_fps``.
        """
        fps = base + self.score // config.SNAKE_SPEEDUP_INTERVAL
        if self.speed_boost_steps > 0:
            fps += config.SNAKE_SPEED_BONUS_FPS
        return min(fps, max_fps)

    @property
    def filled_cells(self) -> int:
        """Total cells on the board (grid_size x grid_size)."""
        return self.grid_size * self.grid_size


class SnakeGame(BaseGame):
    """Playable Snake with rendering, input and power-ups."""

    name = "Snake"
    description = "Eat food, grab power-ups, and don't hit anything"
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
        self.fps = config.SNAKE_FPS
        self.game_over = False

    def _cell_rect(self, cx: int, cy: int) -> pygame.Rect:
        """Screen rectangle for a grid cell."""
        return pygame.Rect(
            self.origin_x + cx * self.cell,
            self.origin_y + cy * self.cell,
            self.cell,
            self.cell,
        )

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
        # Dynamic speed: raise/lower the target FPS based on score + boosts.
        self.fps = self.logic.effective_fps()
        if not self.logic.alive:
            self.game_over = True
            if self.highscores.is_top_n(self.score_key, self.score):
                self.submit_score()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_powerup(self, surface: pygame.Surface, powerup: PowerUp) -> None:
        """Draw a power-up as a coloured diamond with an icon letter."""
        color = (
            config.SNAKE_SPEED_COLOR
            if powerup.kind is PowerType.SPEED
            else config.SNAKE_INVINCIBLE_COLOR
        )
        rect = self._cell_rect(powerup.x, powerup.y)
        cx, cy = rect.center
        r = self.cell // 2 - 3
        points = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        pygame.draw.polygon(surface, color, points)
        icon = "S" if powerup.kind is PowerType.SPEED else "I"
        draw_text(surface, icon, 14, config.BLACK, center=(cx, cy))

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.SNAKE_BG)
        grid = self.logic.grid_size
        # Grid lines
        for i in range(grid + 1):
            x = self.origin_x + i * self.cell
            y = self.origin_y + i * self.cell
            pygame.draw.line(surface, config.SNAKE_GRID, (x, self.origin_y), (x, self.origin_y + grid * self.cell))
            pygame.draw.line(surface, config.SNAKE_GRID, (self.origin_x, y), (self.origin_x + grid * self.cell, y))

        # Food
        pygame.draw.ellipse(surface, config.SNAKE_FOOD, self._cell_rect(*self.logic.food).inflate(-4, -4))

        # Power-up (if one is on the board)
        if self.logic.powerup is not None:
            self._draw_powerup(surface, self.logic.powerup)

        # Snake body + head.
        # self.logic.snake is ordered head-first, so we iterate reversed() to
        # draw tail->head (head ends up on top). In that reversed order the
        # head is the LAST item, i.e. index len-1, which is what we test below.
        invincible = self.logic.invincible_steps > 0
        for i, (cx, cy) in enumerate(reversed(self.logic.snake)):
            is_head = i == len(self.logic.snake) - 1
            color = config.SNAKE_HEAD if is_head else config.SNAKE_BODY
            rect = self._cell_rect(cx, cy)
            pygame.draw.rect(surface, color, rect.inflate(-2, -2), border_radius=4)
            if is_head and invincible:
                # Shield aura while invincible.
                pygame.draw.rect(surface, config.SNAKE_INVINCIBLE_COLOR, rect.inflate(-2, -2), 2, border_radius=4)

        # HUD with live power-up status.
        items = [
            f"Score: {self.score}",
            f"Best: {self.best_score}",
            f"Length: {len(self.logic.snake)}",
            f"Speed: {self.fps}",
        ]
        if invincible:
            items.append(f"INVINCIBLE {self.logic.invincible_steps}")
        if self.logic.speed_boost_steps > 0:
            items.append(f"BOOST {self.logic.speed_boost_steps}")
        self.draw_hud(surface, *items)
        if self.game_over:
            self.draw_game_over(surface)
