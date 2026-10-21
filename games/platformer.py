"""Mario-style platformer with a built-in level editor.

Pure logic (unit-testable without a display):

* :class:`PlatformerLevel` - tile map plus solidity/lookup queries
* :class:`PhysicsBody` / :class:`Enemy` - AABB movement and patrol AI
* :class:`SpriteAnimator` - frame timing behind the animated player sprite
* :class:`ActiveEffect` - timed power-ups (speed shoes, invincibility star)
* :class:`LevelEditor` - paint tiles, validate, save/load custom levels
* :class:`LevelManager` - built-in + user levels and level progression

Tile legend::

    '#' ground    'P' player start   'E' patrolling enemy   'o' coin
    'C' checkpoint 'S' speed shoes   'I' invincibility star 'F' goal flag
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pygame

import config
from base_game import BaseGame
from utils import draw_text

# --------------------------------------------------------------------------
# Built-in levels (rows may be shorter than the widest row; they are padded
# with '.' when the level loads).
# --------------------------------------------------------------------------
#: Level 1 - gentle intro: two small pits, a two-step climb, one enemy.
LEVEL_1: tuple[str, ...] = (
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "....................................o.o",          # coins over the high ledge
    "..................................#######",        # upper platform
    ".............................o.o",                  # coins over the low ledge
    "............................####",                  # lower platform
    "..P...ooo...........E..............C..ooo..................F",
    "##########################..################..##################",
    "##########################..################..##################",
    "##########################..################..##################",
)

#: Level 2 - longer pits, a platform staircase and two power-ups.
LEVEL_2: tuple[str, ...] = (
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "..................#######",                         # top of the staircase
    "...................o.o",                             # coins on it
    "............#####.........#####",                    # two mid platforms
    "........S.........................I",                # power-ups below
    "......#####.....................#####",              # ground-level ledges
    "..P............E...C....ooo...E........F",
    "####################...############...###",
    "####################...############...###",
    "####################...############...###",
)

#: Level 3 - a vertical climb, three enemies and a star finish.
LEVEL_3: tuple[str, ...] = (
    "",
    "................................o.o",                # coins on the summit
    "...............................#####",               # summit platform
    "...........................o.o",
    "..........................#####",
    ".....................o.o",
    "....................#####",
    "...................o.o",
    "..............#####",
    ".........o.o",
    "........#####",
    "..P...o....E......S.C.....E......I.....E.....o.o.....F",
    "##############...############...#########...##################",
    "##############...############...#########...##################",
    "##############...############...#########...##################",
)

BUILTIN_LEVELS: tuple[tuple[str, ...], ...] = (LEVEL_1, LEVEL_2, LEVEL_3)

#: Characters the editor understands, mapped to their hotkey in the UI.
EDITABLE_TILES: tuple[str, ...] = ("#", "o", "E", "C", "S", "I", "F", "P", ".")
#: Characters that are part of the level grammar (anything else is invalid).
KNOWN_TILES: frozenset[str] = frozenset("#oECSIFP.")

TILE = config.PLATFORMER_TILE_SIZE


# --------------------------------------------------------------------------
# Level data
# --------------------------------------------------------------------------
@dataclass
class PlatformerLevel:
    """Tile map plus helpers. Rows are padded to a uniform width on load."""

    rows: list[str] = field(default_factory=lambda: list(LEVEL_1))
    width: int = 0
    height: int = 0

    def __post_init__(self) -> None:
        # Ragged source maps (hand-authored, trailing spaces stripped) are
        # normalised here so every consumer can rely on width * height.
        width = max((len(r) for r in self.rows), default=0)
        self.rows = [r.ljust(width, ".") for r in self.rows]
        self.width = width
        self.height = len(self.rows)

    def tile_at(self, col: int, row: int) -> str:
        """Return the tile character at (col, row), '.' when outside."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.rows[row][col]
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

    def problems(self) -> list[str]:
        """Human-readable issues that make the level unplayable (empty = ok)."""
        issues: list[str] = []
        if not self.rows:
            return ["level has no rows"]
        unknown = sorted({c for row in self.rows for c in row if c not in KNOWN_TILES})
        if unknown:
            issues.append(f"unknown tiles: {''.join(unknown)}")
        if len(self.find_tiles("P")) != 1:
            issues.append("level needs exactly one player start (P)")
        if not self.find_tiles("F"):
            issues.append("level needs a goal flag (F)")
        if not any("#" in row for row in self.rows):
            issues.append("level has no ground")
        return issues


def level_from_rows(rows: Sequence[str]) -> PlatformerLevel:
    """Build a validated :class:`PlatformerLevel`; raises ValueError if bad."""
    level = PlatformerLevel(rows=list(rows))
    problems = level.problems()
    if problems:
        raise ValueError(problems[0])
    return level


# --------------------------------------------------------------------------
# Physics
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Animation and power-up effects
# --------------------------------------------------------------------------
class SpriteAnimator:
    """Cycles through *frame_count* frames at a fixed rate (pure timing)."""

    def __init__(self, frame_count: int, fps: float = config.PLATFORMER_ANIM_FPS) -> None:
        if frame_count < 1:
            raise ValueError("animator needs at least one frame")
        self.frame_count = frame_count
        self.fps = fps
        self._elapsed = 0.0

    def tick(self, dt: float) -> int:
        """Advance time and return the current frame index."""
        self._elapsed += dt
        return int(self._elapsed * self.fps) % self.frame_count

    def reset(self) -> None:
        """Restart the animation from frame 0."""
        self._elapsed = 0.0

    @property
    def frame(self) -> int:
        """Frame index implied by the time already elapsed."""
        return int(self._elapsed * self.fps) % self.frame_count


@dataclass
class ActiveEffect:
    """A power-up with a countdown, e.g. speed shoes or the invincibility star."""

    kind: str                      # "speed" or "star"
    remaining: float               # seconds left
    duration: float                # original duration (for HUD + re-pickups)

    @property
    def active(self) -> bool:
        """True while the effect still has time on the clock."""
        return self.remaining > 0.0

    def tick(self, dt: float) -> None:
        """Count the effect down; never goes negative."""
        self.remaining = max(0.0, self.remaining - dt)

    def extend(self, seconds: float) -> None:
        """Refresh the timer when the same power-up is picked up again."""
        self.remaining = min(self.duration, self.remaining + seconds)


# --------------------------------------------------------------------------
# Level manager (multiple levels + custom files)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class LevelSpec:
    """A named bundle of level rows (built-in or user-authored)."""

    title: str
    rows: tuple[str, ...]


def level_from_json(text: str) -> LevelSpec:
    """Parse a ``{"title": ..., "rows": [...]}`` document into a LevelSpec."""
    try:
        data = json.loads(text)
        title = str(data["title"])
        rows = [str(r) for r in data["rows"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid level file: {exc}") from exc
    if not rows:
        raise ValueError("level file contains no rows")
    return LevelSpec(title=title, rows=tuple(rows))


class LevelManager:
    """Built-in plus user-authored levels, with index-based progression.

    Custom levels live as JSON documents in ``extra_dir`` (written by the
    in-game editor). ``reload()`` re-reads that folder, so levels saved
    mid-session appear immediately.
    """

    def __init__(
        self,
        builtin: Sequence[Sequence[str]] = BUILTIN_LEVELS,
        extra_dir: Path | None = None,
    ) -> None:
        self.builtin: tuple[LevelSpec, ...] = tuple(
            LevelSpec(f"Level {i}", tuple(rows)) for i, rows in enumerate(builtin, start=1)
        )
        self.extra_dir = extra_dir
        self.index = 0
        self.levels: list[LevelSpec] = []
        self.reload()

    def reload(self) -> None:
        """Rebuild the level list: built-ins first, then custom files."""
        specs = list(self.builtin)
        if self.extra_dir is not None and self.extra_dir.is_dir():
            for path in sorted(self.extra_dir.glob("*.json")):
                try:
                    specs.append(level_from_json(path.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue  # skip broken files rather than crash the game
        self.levels = specs
        self.index = max(0, min(self.index, len(specs) - 1))

    @property
    def count(self) -> int:
        """Total number of playable levels."""
        return len(self.levels)

    @property
    def current(self) -> LevelSpec:
        """The level that should be played next."""
        return self.levels[self.index]

    def advance(self) -> bool:
        """Move to the next level; False when the run is already on the last."""
        if self.index + 1 >= self.count:
            return False
        self.index += 1
        return True

    def save_custom(self, name: str, rows: Sequence[str]) -> int:
        """Validate and persist a custom level; return its list index."""
        if self.extra_dir is None:
            raise ValueError("no custom level directory configured")
        level = PlatformerLevel(rows=list(rows))
        problems = level.problems()
        if problems:
            raise ValueError(problems[0])
        self.extra_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"title": name, "rows": level.rows})
        (self.extra_dir / f"{name}.json").write_text(payload, encoding="utf-8")
        self.reload()
        for i, spec in enumerate(self.levels):
            if spec.title == name:
                return i
        return len(self.levels) - 1


# --------------------------------------------------------------------------
# Level editor (pure logic)
# --------------------------------------------------------------------------
class LevelEditor:
    """Paint tiles onto a grid, then validate and (de)serialise the result."""

    def __init__(
        self,
        rows: Sequence[str] | None = None,
        width: int = 64,
        height: int = 16,
    ) -> None:
        if rows:
            pad = max((len(r) for r in rows), default=width)
            self.rows: list[str] = [r.ljust(pad, ".") for r in rows]
            self.width = pad
            self.height = len(self.rows)
        else:
            self.width = width
            self.height = height
            self.rows = ["." * width for _ in range(height)]
        self.brush = "#"
        self.message = ""  # status line shown in the editor UI

    # -- editing --------------------------------------------------------
    def set_brush(self, char: str) -> bool:
        """Select the active brush; False when *char* is not editable."""
        if char not in EDITABLE_TILES:
            return False
        self.brush = char
        return True

    def paint(self, col: int, row: int, erase: bool = False) -> str | None:
        """Stamp the brush at (col, row); returns the tile placed.

        Placing a player start ('P') clears any previous one, because a level
        with two starts is ambiguous. Out-of-bounds paints are ignored.
        """
        if not (0 <= row < self.height and 0 <= col < self.width):
            return None
        char = "." if erase else self.brush
        if char == "P":
            for r, line in enumerate(self.rows):
                if "P" in line:
                    self.rows[r] = line.replace("P", ".")
        line = self.rows[row]
        self.rows[row] = line[:col] + char + line[col + 1:]
        return char

    def clear(self) -> None:
        """Blank the whole grid."""
        self.rows = ["." * self.width for _ in range(self.height)]

    # -- validation & serialisation ------------------------------------
    def to_rows(self) -> list[str]:
        """A copy of the current rows (padded to equal width)."""
        pad = max((len(r) for r in self.rows), default=self.width)
        return [r.ljust(pad, ".") for r in self.rows]

    def problems(self) -> list[str]:
        """Validation issues for the current grid (empty list = playable)."""
        return PlatformerLevel(rows=self.to_rows()).problems()

    def to_dict(self) -> dict[str, object]:
        """JSON-ready representation of the level."""
        return {"title": "custom", "rows": self.to_rows()}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LevelEditor:
        """Rebuild an editor from :meth:`to_dict` output."""
        raw_rows = data.get("rows", [])
        if not isinstance(raw_rows, list):
            raise ValueError("rows must be a list")
        return cls(rows=[str(r) for r in raw_rows])

    def save(self, path: Path) -> None:
        """Write the level to *path* as JSON (does not validate)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"title": path.stem, "rows": self.to_rows()})
        path.write_text(payload, encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> LevelEditor:
        """Read a level back from *path*; raises ValueError when malformed."""
        spec = level_from_json(path.read_text(encoding="utf-8"))
        return cls(rows=list(spec.rows))


# --------------------------------------------------------------------------
# The game
# --------------------------------------------------------------------------
#: Leg offsets (left/right foot dx) for each walk-cycle frame.
_LEG_FRAMES: tuple[tuple[int, int], ...] = ((0, 5), (2, 3), (5, 0), (3, 2))


class PlatformerGame(BaseGame):
    """Playable side-scrolling platformer with checkpoints and an editor."""

    name = "Platformer"
    description = "Run, jump, collect power-ups and edit your own levels"
    score_key = "platformer"
    fps = config.PLATFORMER_FPS
    music_track = "overworld"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.levels = LevelManager(extra_dir=config.LEVELS_DIR)
        self.editor: LevelEditor | None = None  # non-None while editing
        self._load_level()

    # ------------------------------------------------------------------
    # Level / entity loading
    # ------------------------------------------------------------------
    def _load_level(self, keep_progress: bool = True) -> None:
        """(Re)build entities from the current level spec."""
        spec = self.levels.current
        self.level = level_from_rows(spec.rows)
        self.level_title = spec.title
        starts = self.level.find_tiles("P") or [(2, 2)]
        col, row = starts[0]
        self.player = PhysicsBody(x=col * TILE, y=row * TILE)
        self.enemies = [Enemy(x=c * TILE, y=r * TILE) for c, r in self.level.find_tiles("E")]
        self.coins: list[tuple[int, int]] = self.level.find_tiles("o")
        self.total_coins = len(self.coins)
        self.powerup_tiles: dict[tuple[int, int], str] = {
            cell: tile for tile in ("S", "I") for cell in self.level.find_tiles(tile)
        }
        self.checkpoint_tiles: list[tuple[int, int]] = self.level.find_tiles("C")
        self.collected_checkpoints: set[tuple[int, int]] = set()
        self.checkpoint: tuple[int, int] | None = None
        self.flags: list[tuple[int, int]] = self.level.find_tiles("F")
        self.effect: ActiveEffect | None = None
        self.camera_x = 0.0
        self.facing = 1
        self.animator = SpriteAnimator(frame_count=len(_LEG_FRAMES))
        self.banner: tuple[str, float] | None = None
        self.editor = None
        if not keep_progress:
            self.lives = 3
            self.score = 0

    def reset(self) -> None:
        super().reset()
        self.levels.index = 0
        self.lives = 3
        self.game_over = False
        self.won = False
        self._load_level(keep_progress=False)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
                    return True
                if event.key == pygame.K_e and not (self.game_over or self.won):
                    self._toggle_editor()
                    return True
            if self.editor is not None:
                self._handle_editor_events(event)
        if self.editor is not None or self.game_over or self.won:
            return True

        keys = pygame.key.get_pressed()
        self.player.vx = 0.0
        speed = config.PLATFORMER_MOVE_SPEED
        if self.effect and self.effect.kind == "speed":
            speed *= config.PLATFORMER_SPEED_MULTIPLIER
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player.vx = -speed
            self.facing = -1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player.vx = speed
            self.facing = 1
        if (keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]) and self.player.on_ground:
            self.player.vy = config.PLATFORMER_JUMP_STRENGTH
            self.audio.play("jump")
        return True

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.banner is not None:
            text, remaining = self.banner
            remaining -= dt
            self.banner = (text, remaining) if remaining > 0 else None
        if self.editor is not None:
            self._scroll_editor_camera()  # physics freeze while editing
            return
        if self.game_over or self.won:
            return
        p = self.player
        if self.effect is not None:
            self.effect.tick(dt)
            if not self.effect.active:
                self.effect = None
        p.vy = min(p.vy + config.PLATFORMER_GRAVITY, config.PLATFORMER_MAX_FALL)
        _move_axis(p, self.level, "x")
        _move_axis(p, self.level, "y")

        self._update_camera(dt)
        self._collect_items(p)
        if not self._update_enemies(p):
            return  # a life was lost this frame; skip the rest
        self._check_goal(p)

        # Fell out of the world (past the bottom of the map)
        if p.y > self.level.height * TILE + 100:
            self._lose_life()

        # Drive the walk-cycle animation from actual movement, so standing
        # still freezes the character mid-stride.
        if abs(p.vx) > 0.1 or not p.on_ground:
            self.animator.tick(dt)

    def _update_camera(self, dt: float) -> None:
        """Smoothly follow the player, clamped to the level's bounds."""
        level_px = self.level.width * TILE
        target = self.player.x - config.SCREEN_WIDTH * 0.4
        target = max(0.0, min(target, level_px - config.SCREEN_WIDTH))
        # Exponential approach: frame-rate independent catch-up that never
        # overshoots (the min(1, ...) keeps big dt values stable).
        self.camera_x += (target - self.camera_x) * min(1.0, dt * config.PLATFORMER_CAMERA_LERP)
        self.camera_x = max(0.0, min(self.camera_x, max(0.0, level_px - config.SCREEN_WIDTH)))

    def _collect_items(self, p: PhysicsBody) -> None:
        """Coins, power-ups and checkpoints."""
        p_rect = p.rect
        for coin in list(self.coins):
            if p_rect.colliderect(_tile_rect(coin).inflate(-8, -8)):
                self.coins.remove(coin)
                self.score += config.PLATFORMER_COIN_SCORE
                self.audio.play("coin")
        for cell, kind in list(self.powerup_tiles.items()):
            if p_rect.colliderect(_tile_rect(cell)):
                del self.powerup_tiles[cell]
                self.score += config.PLATFORMER_POWERUP_SCORE
                self.audio.play("powerup")
                self._apply_effect(kind)
        for cell in self.checkpoint_tiles:
            if cell in self.collected_checkpoints:
                continue
            if p_rect.colliderect(_tile_rect(cell)):
                self.collected_checkpoints.add(cell)
                self.checkpoint = cell
                self.score += config.PLATFORMER_CHECKPOINT_SCORE
                self.audio.play("checkpoint")
                self.banner = ("CHECKPOINT!", 1.2)

    def _apply_effect(self, kind: str) -> None:
        duration = config.PLATFORMER_POWERUP_DURATION
        if self.effect is not None and self.effect.kind == kind:
            self.effect.extend(duration)  # re-pickup refreshes the timer
        else:
            self.effect = ActiveEffect(kind=kind, remaining=duration, duration=duration)

    def _update_enemies(self, p: PhysicsBody) -> bool:
        """Move enemies and resolve stomp/star/side collisions.

        Returns False when the player lost a life this frame (the caller
        should stop processing the rest of the update).
        """
        p_rect = p.rect
        star = self.effect is not None and self.effect.kind == "star"
        for enemy in self.enemies:
            enemy.update(self.level)
            if not enemy.alive or not p_rect.colliderect(enemy.rect):
                continue
            # Stomp kill: only if the player is falling (vy > 0) AND their feet
            # are near the enemy's head. A small bounce rewards the stomp.
            stomping = p.vy > 0 and p_rect.bottom - enemy.rect.top < 16
            if stomping or star:
                enemy.alive = False
                self.score += config.PLATFORMER_STOMP_SCORE
                self.audio.play("stomp")
                if stomping:
                    p.vy = config.PLATFORMER_JUMP_STRENGTH * 0.5  # small bounce
            else:
                self._lose_life()
                return False
        return True

    def _check_goal(self, p: PhysicsBody) -> None:
        p_rect = p.rect
        for flag in self.flags:
            if p_rect.colliderect(_tile_rect(flag).inflate(0, TILE)):
                self._next_level()
                return

    # ------------------------------------------------------------------
    # Progression
    # ------------------------------------------------------------------
    def _next_level(self) -> None:
        self.score += config.PLATFORMER_FLAG_SCORE
        self.audio.play("level_clear")
        if self.levels.advance():
            self._load_level(keep_progress=True)
            self.banner = (f"{self.level_title.upper()}!", 2.0)
        else:
            self.won = True
            self.submit_score()

    def _lose_life(self) -> None:
        self.lives -= 1
        self.audio.play("hurt")
        self.effect = None
        if self.lives <= 0:
            self.game_over = True
            if self.highscores.is_top_n(self.score_key, self.score):
                self.submit_score()
            return
        # Respawn at the last checkpoint (or the level start when none hit).
        col, row = self.checkpoint or (self.level.find_tiles("P") or [(2, 2)])[0]
        self.player = PhysicsBody(x=col * TILE, y=row * TILE)
        self.animator.reset()

    # ------------------------------------------------------------------
    # Level editor
    # ------------------------------------------------------------------
    def _scroll_editor_camera(self) -> None:
        """Pan the camera with A/D or the arrow keys while editing."""
        keys = pygame.key.get_pressed()
        speed = 14.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.camera_x -= speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.camera_x += speed
        max_x = max(0.0, self.level.width * TILE - config.SCREEN_WIDTH)
        self.camera_x = max(0.0, min(self.camera_x, max_x))

    def _toggle_editor(self) -> None:
        if self.editor is None:
            self.editor = LevelEditor(self.level.rows)
            self.editor.message = "E: play  |  1-9: brush  |  S: save  |  X: clear"
        else:
            # Leaving the editor rebuilds the world from the painted grid so
            # the edited level is immediately playable.
            rows = self.editor.to_rows()
            self.editor = None
            self.level = level_from_rows(rows)
            starts = self.level.find_tiles("P") or [(2, 2)]
            col, row = starts[0]
            self.player = PhysicsBody(x=col * TILE, y=row * TILE)
            self.enemies = [Enemy(x=c * TILE, y=r * TILE) for c, r in self.level.find_tiles("E")]
            self.coins = self.level.find_tiles("o")
            self.total_coins = len(self.coins)
            self.powerup_tiles = {
                cell: tile for tile in ("S", "I") for cell in self.level.find_tiles(tile)
            }
            self.checkpoint_tiles = self.level.find_tiles("C")
            self.collected_checkpoints = set()
            self.checkpoint = None
            self.flags = self.level.find_tiles("F")

    def _handle_editor_events(self, event: pygame.event.Event) -> None:
        """Route editor input; only meaningful while :attr:`editor` is set."""
        editor = self.editor
        if editor is None:
            return
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_9:
                index = event.key - pygame.K_1
                if index < len(EDITABLE_TILES):
                    editor.set_brush(EDITABLE_TILES[index])
            elif event.key == pygame.K_s:
                self._save_editor_level()
            elif event.key == pygame.K_x:
                editor.clear()
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION):
            # Left button paints with the current brush, right erases.
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    erase = False
                elif event.button == 3:
                    erase = True
                else:
                    return
            else:  # MOUSEMOTION: only paint while a button is held
                buttons = getattr(event, "buttons", (0, 0, 0))
                if not (buttons[0] or buttons[1]):
                    return
                erase = bool(buttons[1])
            col = int((event.pos[0] + self.camera_x) // TILE)
            row = int(event.pos[1] // TILE)
            placed = editor.paint(col, row, erase=erase)
            if placed is not None:
                self.audio.play("brick", volume=0.3)

    def _save_editor_level(self) -> None:
        editor = self.editor
        if editor is None:
            return
        problems = editor.problems()
        if problems:
            editor.message = f"NOT SAVED: {problems[0]}"
            return
        name = f"custom_{self.levels.count - len(self.levels.builtin) + 1}"
        try:
            index = self.levels.save_custom(name, editor.to_rows())
        except ValueError as exc:
            editor.message = f"NOT SAVED: {exc}"
            return
        self.levels.index = index
        editor.message = f"SAVED as {name}.json - press E to play it"
        self.audio.play("confirm")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.PLATFORMER_SKY)
        cam = int(self.camera_x)
        self._draw_tiles(surface, cam)
        self._draw_collectibles(surface, cam)
        if self.editor is None:
            self._draw_enemies(surface, cam)
            self._draw_player(surface, cam)
        else:
            self._draw_editor_overlay(surface)
        self._draw_hud(surface)
        if self.banner is not None:
            draw_text(surface, self.banner[0], config.FONT_SIZE_LARGE, config.YELLOW,
                      center=(config.SCREEN_WIDTH // 2, 140))
        if self.won:
            self.draw_game_over(surface, message="ALL LEVELS CLEAR!", subtitle="+500 bonus")
        elif self.game_over:
            self.draw_game_over(surface)

    def _draw_tiles(self, surface: pygame.Surface, cam: int) -> None:
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
                        [(x + TILE // 2 + 2, y - TILE),
                         (x + TILE // 2 + 30, y - TILE + 12),
                         (x + TILE // 2 + 2, y - TILE + 24)],
                    )
                elif tile == "C":
                    # Checkpoint: a cyan post with a little pennant.
                    pygame.draw.rect(surface, config.CYAN, (x + TILE // 2 - 2, y - TILE // 2, 4, TILE))
                    pygame.draw.polygon(
                        surface,
                        config.CYAN,
                        [(x + TILE // 2 + 2, y - TILE // 2),
                         (x + TILE // 2 + 20, y - TILE // 2 + 8),
                         (x + TILE // 2 + 2, y - TILE // 2 + 16)],
                    )

    def _draw_collectibles(self, surface: pygame.Surface, cam: int) -> None:
        for coin in self.coins:
            pygame.draw.circle(surface, config.COIN_COLOR,
                               (coin[0] * TILE - cam + TILE // 2, coin[1] * TILE + TILE // 2),
                               TILE // 3)
        for (col, row), kind in self.powerup_tiles.items():
            rect = pygame.Rect(col * TILE - cam, row * TILE, TILE, TILE)
            if kind == "S":
                pygame.draw.rect(surface, config.ORANGE, rect.inflate(-10, -10), border_radius=6)
                draw_text(surface, "S", config.FONT_SIZE_SMALL, config.WHITE, center=rect.center)
            else:  # star / invincibility
                pygame.draw.circle(surface, config.YELLOW, rect.center, TILE // 3)
                draw_text(surface, "I", config.FONT_SIZE_SMALL, config.BLACK, center=rect.center)

    def _draw_enemies(self, surface: pygame.Surface, cam: int) -> None:
        for enemy in self.enemies:
            if enemy.alive:
                pygame.draw.rect(surface, config.ENEMY_COLOR, enemy.rect.move(-cam, 0), border_radius=6)

    def _draw_player(self, surface: pygame.Surface, cam: int) -> None:
        rect = self.player.rect.move(-cam, 0)
        self._draw_player_sprite(
            surface, rect, facing=self.facing, frame=self.animator.frame,
            airborne=not self.player.on_ground,
        )
        if self.effect is not None and self.effect.kind == "star":
            # Star power shows as a shimmering halo around the character.
            pygame.draw.rect(surface, config.YELLOW, rect.inflate(10, 10), 3, border_radius=8)

    @staticmethod
    def _draw_player_sprite(
        surface: pygame.Surface, rect: pygame.Rect, facing: int, frame: int, airborne: bool
    ) -> None:
        """Draw the (asset-free) animated player: cap, face, overalls, legs."""
        head = pygame.Rect(rect.x + 6, rect.y, rect.w - 12, 14)
        pygame.draw.rect(surface, config.RED, (head.x, head.y - 4, head.w, 7), border_radius=3)  # cap
        pygame.draw.rect(surface, (255, 220, 180), head, border_radius=4)                        # face
        eye_x = head.centerx + 3 * facing
        pygame.draw.circle(surface, config.BLACK, (eye_x, head.centery), 2)                      # eye
        body = pygame.Rect(rect.x + 3, rect.y + 15, rect.w - 6, rect.h - 22)
        pygame.draw.rect(surface, config.BLUE, body, border_radius=5)                            # overalls
        # Legs: the walk cycle alternates foot positions; in the air both legs
        # tuck together for a classic jump silhouette.
        if airborne:
            feet = (4, 8)
        else:
            feet = _LEG_FRAMES[frame % len(_LEG_FRAMES)]
        for dx in feet:
            pygame.draw.rect(surface, config.DARK_GREY,
                             (rect.x + dx, rect.bottom - 7, 5, 7), border_radius=2)

    def _draw_editor_overlay(self, surface: pygame.Surface) -> None:
        """Palette + status line + grid guides while editing."""
        editor = self.editor
        if editor is None:
            return
        # Subtle grid so tile boundaries are visible while painting.
        cam = int(self.camera_x)
        for col in range(0, self.level.width + 1):
            x = col * TILE - cam
            if 0 <= x <= config.SCREEN_WIDTH:
                pygame.draw.line(surface, (255, 255, 255), (x, 40), (x, config.SCREEN_HEIGHT), 1)
        for row in range(0, self.level.height + 1):
            y = row * TILE
            pygame.draw.line(surface, (255, 255, 255), (0, y), (config.SCREEN_WIDTH, y), 1)
        self._draw_hud(surface, editor=True)
        draw_text(surface, editor.message, config.FONT_SIZE_SMALL, config.WHITE,
                  center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 24))

    def _draw_hud(self, surface: pygame.Surface, editor: bool = False) -> None:
        if editor:
            items = ["EDITOR", "A/D: scroll"]
            self.draw_hud(surface, *items)
            self._draw_palette(surface)
            return
        collected = self.total_coins - len(self.coins)
        items = [
            f"Score: {self.score}",
            f"Lives: {self.lives}",
            f"Coins: {collected}",
            f"Level: {self.levels.index + 1}/{self.levels.count}",
            f"Best: {self.best_score}",
        ]
        if self.effect is not None:
            items.append(f"{self.effect.kind.upper()} {self.effect.remaining:.0f}s")
        self.draw_hud(surface, *items)

    def _draw_palette(self, surface: pygame.Surface) -> None:
        """Editor brush palette pinned under the HUD bar."""
        editor = self.editor
        if editor is None:
            return
        labels = {"#": "Ground", "o": "Coin", "E": "Enemy", "C": "Check",
                  "S": "Speed", "I": "Star", "F": "Flag", "P": "Start", ".": "Erase"}
        x = 10
        for i, tile in enumerate(EDITABLE_TILES):
            rect = pygame.Rect(x, 40, 96, 30)
            selected = editor.brush == tile
            pygame.draw.rect(surface, config.HOVER if selected else config.PANEL_BG,
                             rect, border_radius=6)
            pygame.draw.rect(surface, config.ACCENT if selected else config.LIGHT_GREY, rect, 2, border_radius=6)
            draw_text(surface, f"{i + 1} {labels[tile]}", config.FONT_SIZE_SMALL,
                      config.WHITE if selected else config.LIGHT_GREY, center=rect.center)
            x += 104


def _tile_rect(cell: tuple[int, int]) -> pygame.Rect:
    """Screen rectangle (no camera offset) for a tile cell."""
    return pygame.Rect(cell[0] * TILE, cell[1] * TILE, TILE, TILE)
