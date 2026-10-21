"""Mario-style platformer.

Tile-based level with gravity, jumping, patrolling enemies, coins and a
goal flag. :class:`PlatformerLevel` holds the pure level/physics data so
it can be tested without a display.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pygame

import config
from base_game import BaseGame

# Tile legend used by the level string map:
#   '#' ground   'P' player start   'E' enemy   'o' coin   'F' goal flag
LEVEL_MAP: list[str] = [
    "................................................................",
    "................................................................",
    "................................................................",
    ".....................o.o..............o.........................F",
    "....................#####............###.....................####",
    "..........o...................o..o...............................",
    ".........###.................#########...........................",
    "....o......................................o..o........o..o......",
    "...####....................E...............#####......#####.....",
    ".....................................................E..........",
    "..............o..o...............................##########.....",
    ".............#####..........E....................................",
    ".........................................o..o....................",
    "#####...............................############.................",
    "#####...E............................############.................",
    "#####..#####.........................############.................",
]

TILE = config.PLATFORMER_TILE_SIZE


@dataclass
class PhysicsBody:
    """A simple AABB physics body."""

    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    w: int = TILE - 8
    h: int = TILE - 6
    on_ground: bool = False

    @property
    def rect(self) -> pygame.Rect:
        """Axis-aligned bounding box as a pygame Rect."""
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)


@dataclass
class Enemy(PhysicsBody):
    """A patrolling enemy that turns around at ledges and walls."""

    direction: int = -1
    alive: bool = True
    speed: float = 2.0

    def update(self, level: PlatformerLevel) -> None:
        """Move horizontally, flipping at walls or ledge edges."""
        if not self.alive:
            return
        self.vx = self.direction * self.speed
        _move_axis(self, level, axis="x")
        # Turn around at ledges and walls. Probe a tiny 2x2 rect just ahead:
        #  - at foot level: if there's no ground below (a drop-off), turn back;
        #  - full height:   if there's a wall directly ahead, turn back.
        ahead_x = self.rect.right + 2 if self.direction > 0 else self.rect.left - 2
        foot_probe = pygame.Rect(ahead_x, self.rect.bottom + 2, 2, 2)
        if not level.solid_at(foot_probe) or level.solid_at(
            pygame.Rect(ahead_x, self.rect.top, 2, self.rect.height)
        ):
            self.direction *= -1


@dataclass
class PlatformerLevel:
    """Tile map plus entities."""

    rows: list[str] = field(default_factory=lambda: list(LEVEL_MAP))
    width: int = 0
    height: int = 0

    def __post_init__(self) -> None:
        self.width = max(len(r) for r in self.rows)
        self.height = len(self.rows)

    def tile_at(self, col: int, row: int) -> str:
        """Return the tile character at (col, row), '.' when outside."""
        if 0 <= row < self.height and 0 <= col < self.width:
            line = self.rows[row]
            if 0 <= col < len(line):
                return line[col]
        return "."

    def solid_at(self, rect: pygame.Rect) -> bool:
        """True when *rect* overlaps any solid tile."""
        # Convert the rect's pixel edges to tile coordinates. We subtract 1
        # from right/bottom because pygame rects treat those edges as
        # exclusive - without it, a rect that merely abuts the next tile would
        # wrongly count as overlapping it.
        left = rect.left // TILE
        right = (rect.right - 1) // TILE
        top = rect.top // TILE
        bottom = (rect.bottom - 1) // TILE
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if self.tile_at(col, row) == "#":
                    return True
        return False

    def find_tiles(self, char: str) -> list[tuple[int, int]]:
        """Coordinates of every *char* tile."""
        return [
            (col, row)
            for row, line in enumerate(self.rows)
            for col, c in enumerate(line)
            if c == char
        ]


def _move_axis(body: PhysicsBody, level: PlatformerLevel, axis: str) -> None:
    """Move *body* along one axis, resolving solid-tile collisions.

    Classic "move, then un-penetrate" AABB approach: apply the velocity, and
    if the body ended up overlapping a solid tile, snap it back to the tile
    boundary it crossed and zero that axis of velocity. Axes are handled one
    at a time so wall vs floor collisions stay independent.
    """
    if axis == "x":
        body.x += body.vx
        rect = body.rect
        if level.solid_at(rect):
            if body.vx > 0:
                # Moving right: push the body's left edge just left of the tile
                # it entered. The -1 keeps it a pixel clear so it won't
                # re-register as overlapping on the next frame.
                rect.left = (rect.left // TILE) * TILE - 1
            elif body.vx < 0:
                rect.right = (rect.right // TILE + 1) * TILE + 1
            body.x = float(rect.x)
            body.vx = 0.0  # kill horizontal speed on impact
    else:
        body.y += body.vy
        rect = body.rect
        body.on_ground = False  # assume airborne until proven otherwise
        if level.solid_at(rect):
            if body.vy > 0:
                # Falling and hit a floor: rest exactly on top of the tile and
                # flag that we're standing on ground (enables jumping).
                rect.bottom = (rect.bottom // TILE) * TILE
                body.on_ground = True
            elif body.vy < 0:
                # Rising and hit a ceiling: stop just below it.
                rect.top = (rect.top // TILE) * TILE + TILE
            body.y = float(rect.y)
            body.vy = 0.0  # kill vertical speed on impact


class PlatformerGame(BaseGame):
    """Playable side-scrolling platformer."""

    name = "Platformer"
    description = "Run, jump, stomp enemies and reach the flag"
    score_key = "platformer"
    fps = config.PLATFORMER_FPS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.level = PlatformerLevel()
        self._setup_level()

    def _setup_level(self) -> None:
        self.level = PlatformerLevel()
        starts = self.level.find_tiles("P") or [(2, 2)]
        col, row = starts[0]
        self.player = PhysicsBody(x=col * TILE, y=row * TILE)
        self.enemies = [
            Enemy(x=c * TILE, y=r * TILE) for c, r in self.level.find_tiles("E")
        ]
        self.coins: list[tuple[int, int]] = self.level.find_tiles("o")
        self.flags: list[tuple[int, int]] = self.level.find_tiles("F")
        self.camera_x = 0.0
        self.game_over = False
        self.won = False
        self.lives = 3
        self.score = 0

    def reset(self) -> None:
        super().reset()
        self._setup_level()

    # ------------------------------------------------------------------
    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        keys = pygame.key.get_pressed()
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
                    return True
        if self.game_over or self.won:
            return True
        self.player.vx = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player.vx = -config.PLATFORMER_MOVE_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player.vx = config.PLATFORMER_MOVE_SPEED
        if (keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]) and self.player.on_ground:
            self.player.vy = config.PLATFORMER_JUMP_STRENGTH
        return True

    def update(self, dt: float) -> None:
        if self.game_over or self.won:
            return
        p = self.player
        p.vy = min(p.vy + config.PLATFORMER_GRAVITY, 18.0)
        _move_axis(p, self.level, "x")
        _move_axis(p, self.level, "y")

        # Camera follows the player, keeping them ~40% from the left edge, but
        # is clamped so it never scrolls past the level's start or end.
        level_px = self.level.width * TILE
        target = p.x - config.SCREEN_WIDTH * 0.4
        self.camera_x = max(0.0, min(target, level_px - config.SCREEN_WIDTH))

        # Coins
        p_rect = p.rect
        for coin in list(self.coins):
            coin_rect = pygame.Rect(coin[0] * TILE + 8, coin[1] * TILE + 8, TILE - 16, TILE - 16)
            if p_rect.colliderect(coin_rect):
                self.coins.remove(coin)
                self.score += 50

        # Enemies
        for enemy in self.enemies:
            enemy.update(self.level)
            if not enemy.alive:
                continue
            if p_rect.colliderect(enemy.rect):
                # Stomp kill: only if the player is falling (vy > 0) AND their
                # feet are near the enemy's head, i.e. landing on top. A small
                # bounce rewards the stomp. Otherwise it's a side hit = lose a life.
                if p.vy > 0 and p_rect.bottom - enemy.rect.top < 16:
                    enemy.alive = False
                    self.score += 100
                    p.vy = config.PLATFORMER_JUMP_STRENGTH * 0.5  # small bounce
                else:
                    self._lose_life()
                    return

        # Goal
        for flag in self.flags:
            flag_rect = pygame.Rect(flag[0] * TILE, flag[1] * TILE - TILE, TILE, TILE * 2)
            if p_rect.colliderect(flag_rect):
                self.won = True
                self.score += 500
                self.submit_score()
                return

        # Fell out of the world
        if p.y > self.level.height * TILE + 100:
            self._lose_life()

    def _lose_life(self) -> None:
        self.lives -= 1
        if self.lives <= 0:
            self.game_over = True
            if self.highscores.is_top_n(self.score_key, self.score):
                self.submit_score()
        else:
            starts = self.level.find_tiles("P") or [(2, 2)]
            col, row = starts[0]
            self.player = PhysicsBody(x=col * TILE, y=row * TILE)

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.PLATFORMER_SKY)
        cam = int(self.camera_x)

        # Tiles
        for row in range(self.level.height):
            for col in range(self.level.width):
                tile = self.level.tile_at(col, row)
                if tile == ".":
                    continue
                x = col * TILE - cam
                if x < -TILE or x > config.SCREEN_WIDTH:
                    continue
                y = row * TILE
                if tile == "#":
                    pygame.draw.rect(surface, config.PLATFORMER_GROUND, (x, y, TILE, TILE))
                    pygame.draw.rect(surface, config.PLATFORMER_GRASS, (x, y, TILE, 8))
                elif tile == "F":
                    pygame.draw.rect(surface, config.GREY, (x + TILE // 2 - 2, y - TILE, 4, TILE * 2))
                    pygame.draw.polygon(
                        surface,
                        config.RED,
                        [(x + TILE // 2 + 2, y - TILE), (x + TILE // 2 + 30, y - TILE + 12), (x + TILE // 2 + 2, y - TILE + 24)],
                    )

        # Coins
        for coin in self.coins:
            pygame.draw.circle(surface, config.COIN_COLOR, (coin[0] * TILE - cam + TILE // 2, coin[1] * TILE + TILE // 2), TILE // 3)

        # Enemies
        for enemy in self.enemies:
            if enemy.alive:
                pygame.draw.rect(surface, config.ENEMY_COLOR, enemy.rect.move(-cam, 0), border_radius=6)

        # Player
        pygame.draw.rect(surface, config.BLUE, self.player.rect.move(-cam, 0), border_radius=4)
        pygame.draw.rect(surface, config.YELLOW, (self.player.rect.x - cam + 4, self.player.rect.y + 4, 8, 8))

        self.draw_hud(
            surface,
            f"Score: {self.score}",
            f"Lives: {self.lives}",
            f"Coins: {len(self.level.find_tiles('o')) - len(self.coins)}",
            f"Best: {self.best_score}",
        )
        if self.won:
            self.draw_game_over(surface, message="LEVEL COMPLETE!", subtitle="+500 bonus")
        elif self.game_over:
            self.draw_game_over(surface)
