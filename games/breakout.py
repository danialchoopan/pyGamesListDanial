"""Breakout / Arkanoid.

Bounce the ball off a paddle to smash every destructible brick. Physics and
brick rules live in pure classes so they can be tested headless:

* :class:`Ball` - position, velocity and launch angle
* :class:`Brick` / :class:`BrickType` - normal, hard, steel (indestructible)
  and explosive bricks
* :class:`BreakoutPhysics` - vector reflection, wall/paddle/brick collisions
  and explosive chain reactions
* :class:`BallTrail` - recent positions behind the ball for a fading tail
* :class:`FallingPowerUp` / :class:`PowerUpType` - drops from broken bricks
* :func:`build_level` - level layouts that get harder as they rise
"""

from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

import pygame

import config
from base_game import BaseGame
from utils import draw_text


# --------------------------------------------------------------------------
# Bricks
# --------------------------------------------------------------------------
class BrickType(Enum):
    """The four brick behaviours."""

    NORMAL = "normal"              # one hit
    HARD = "hard"                  # several hits (cracks as it wears)
    INDESTRUCTIBLE = "indestructible"  # bounces the ball, never breaks
    EXPLOSIVE = "explosive"        # destroys its neighbours when broken


@dataclass
class Brick:
    """A single brick."""

    rect: pygame.Rect
    color: config.Color = config.RED
    hp: int = 1
    points: int = 10
    brick_type: BrickType = BrickType.NORMAL
    alive: bool = True

    def hit(self) -> bool:
        """Apply one hit; return True when the brick was destroyed.

        Indestructible bricks ignore damage entirely - that is what makes
        them useful as level furniture the ball bounces off forever.
        """
        if self.brick_type is BrickType.INDESTRUCTIBLE:
            return False
        self.hp -= 1
        if self.hp <= 0:
            self.alive = False
        return not self.alive


@dataclass
class BrickResolution:
    """Everything that happened when the ball touched a brick this frame."""

    points: int = 0
    destroyed: list[Brick] = field(default_factory=list)
    damaged: list[Brick] = field(default_factory=list)
    chain_count: int = 0  # extra bricks removed by explosive chain reactions

    @property
    def hit_any(self) -> bool:
        """True when at least one brick took damage (ball may have sped up)."""
        return bool(self.destroyed or self.damaged)


# --------------------------------------------------------------------------
# Ball, trail and power-ups
# --------------------------------------------------------------------------
class Ball:
    """The breakable ball."""

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.radius = config.BALL_SIZE // 2

    @property
    def rect(self) -> pygame.Rect:
        """Bounding rect of the ball."""
        d = self.radius * 2
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius), d, d)

    def launch(self, speed: float, rng_angle: float = 0.6, offset: float = 0.0) -> None:
        """Launch upward at a slightly randomised (optionally offset) angle."""
        angle = math.pi / 2 - rng_angle / 2 + random.random() * rng_angle + offset
        self.vx = speed * math.cos(angle)
        self.vy = -speed * math.sin(angle)

    @property
    def speed(self) -> float:
        """Current velocity magnitude."""
        return math.hypot(self.vx, self.vy)

    def rescale(self, speed: float) -> None:
        """Keep direction but set the velocity magnitude to *speed*."""
        magnitude = self.speed or 1.0
        self.vx *= speed / magnitude
        self.vy *= speed / magnitude

    def split_angles(self, count: int = config.MULTIBALL_COUNT,
                     angle: float = config.MULTIBALL_ANGLE) -> list[Ball]:
        """Return *count* new balls deflected from this one's path."""
        base = math.atan2(self.vy, self.vx)
        speed = self.speed
        out: list[Ball] = []
        for i in range(count):
            # Fan the extra balls evenly around the original direction.
            spread = (i - (count - 1) / 2) * angle
            new_ball = Ball(self.x, self.y)
            new_ball.vx = speed * math.cos(base + spread)
            new_ball.vy = speed * math.sin(base + spread)
            out.append(new_ball)
        return out


class BallTrail:
    """Recent ball positions, newest first, for the fading tail effect."""

    def __init__(self, length: int = config.BALL_TRAIL_LENGTH) -> None:
        self._points: deque[tuple[float, float]] = deque(maxlen=length)

    def record(self, x: float, y: float) -> None:
        self._points.appendleft((x, y))

    def points(self) -> list[tuple[float, float]]:
        """Positions newest -> oldest."""
        return list(self._points)

    def clear(self) -> None:
        self._points.clear()

    def __len__(self) -> int:
        return len(self._points)


class PowerUpType(Enum):
    """Power-ups that can drop from a destroyed brick."""

    WIDE = "wide"    # temporarily widen the paddle
    MULTI = "multi"  # split the ball into several
    LASER = "laser"  # temporarily arm the paddle with lasers
    LIFE = "life"    # extra life


#: Letter + colour used to draw each falling power-up.
POWERUP_STYLE: dict[PowerUpType, tuple[str, config.Color]] = {
    PowerUpType.WIDE: ("W", config.CYAN),
    PowerUpType.MULTI: ("M", config.GREEN),
    PowerUpType.LASER: ("L", config.ORANGE),
    PowerUpType.LIFE: ("+", config.RED),
}


@dataclass
class FallingPowerUp:
    """A power-up token drifting down toward the paddle."""

    x: float
    y: float
    kind: PowerUpType
    size: int = 22

    def update(self) -> None:
        self.y += config.POWERUP_FALL_SPEED

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.size // 2), int(self.y - self.size // 2),
                           self.size, self.size)


def roll_powerup(rng: random.Random) -> PowerUpType | None:
    """Chance-based drop roll; None when nothing drops."""
    if rng.random() >= config.POWERUP_DROP_CHANCE:
        return None
    return rng.choice(list(PowerUpType))


class LaserBolt:
    """A shot fired by an upgraded paddle."""

    LASER_SPEED = -12.0  # px/frame (negative = up the screen)

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.alive = True

    def update(self) -> None:
        self.y += self.LASER_SPEED
        if self.y < -10:
            self.alive = False
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - 2, int(self.y) - 8, 4, 12)


# --------------------------------------------------------------------------
# Physics
# --------------------------------------------------------------------------
class BreakoutPhysics:
    """Pure helpers for ball movement and collision resolution."""

    #: How close (px) two brick edges must be to count as touching for
    #: explosive chain reactions (bricks are drawn with a small gap).
    TOUCH_TOLERANCE = 8
    #: Cap on explosive chain depth so a wall of explosives resolves at once
    #: without recursing forever.
    MAX_CHAIN_DEPTH = 4

    # -- movement -------------------------------------------------------
    @staticmethod
    def integrate(ball: Ball) -> None:
        """Move the ball one step."""
        ball.x += ball.vx
        ball.y += ball.vy

    @staticmethod
    def bounce_walls(ball: Ball, bounds_w: int, bounds_h: int) -> bool:
        """Bounce off side/top walls; return False when the ball drops below."""
        if ball.x - ball.radius <= 0 and ball.vx < 0:
            ball.x = ball.radius
            ball.vx = -ball.vx
        elif ball.x + ball.radius >= bounds_w and ball.vx > 0:
            ball.x = bounds_w - ball.radius
            ball.vx = -ball.vx
        if ball.y - ball.radius <= 0 and ball.vy < 0:
            ball.y = ball.radius
            ball.vy = -ball.vy
        return ball.y + ball.radius < bounds_h

    @staticmethod
    def bounce_paddle(ball: Ball, paddle: pygame.Rect, speed: float) -> None:
        """Bounce off the paddle, angling based on hit position.

        This is the core Breakout skill: hitting with the paddle's edge steers
        the ball sharply, while a centre hit sends it straight back up.
        """
        # Only bounce when the ball is moving down and clips the TOP half of
        # the paddle; the centery check stops side-on passes from glitching.
        if ball.vy > 0 and ball.rect.colliderect(paddle) and ball.y < paddle.centery:
            ball.y = paddle.top - ball.radius  # rest the ball on the paddle
            # Horizontal offset of the impact, normalised to -1 (left edge)
            # .. +1 (right edge), then mapped to a deflection angle up to 60°.
            offset = (ball.x - paddle.centerx) / (paddle.width / 2)
            offset = max(-1.0, min(1.0, offset))
            angle = offset * (math.pi / 3)  # up to 60 degrees
            ball.vx = speed * math.sin(angle)
            ball.vy = -speed * math.cos(angle)  # negative = travel upward

    # -- reflection -----------------------------------------------------
    @staticmethod
    def reflect(ball: Ball, normal: tuple[float, float]) -> None:
        """Reflect the ball's velocity about *normal* (v' = v - 2(v.n)n).

        Using the real reflection formula (rather than "just flip one
        component") keeps the ball's speed exactly constant and generalises
        to the angled normals a corner hit can produce.
        """
        dot = ball.vx * normal[0] + ball.vy * normal[1]
        ball.vx -= 2.0 * dot * normal[0]
        ball.vy -= 2.0 * dot * normal[1]

    @staticmethod
    def contact_normal(ball: Ball, brick: Brick) -> tuple[float, float]:
        """Unit normal of the face the ball grazed.

        The ball reflects off whichever axis it penetrated least - that's the
        face it actually hit, so it bounces back out the way it came instead
        of getting wedged into a corner.
        """
        overlap_x = min(ball.rect.right - brick.rect.left, brick.rect.right - ball.rect.left)
        overlap_y = min(ball.rect.bottom - brick.rect.top, brick.rect.bottom - ball.rect.top)
        if overlap_x < overlap_y:
            # Side hit: the normal points back against the horizontal motion.
            return (1.0 if ball.vx < 0 else -1.0, 0.0)
        return (0.0, 1.0 if ball.vy < 0 else -1.0)

    # -- bricks ---------------------------------------------------------
    @staticmethod
    def bounce_bricks(ball: Ball, bricks: list[Brick], speed: float) -> int:
        """Resolve brick collisions; return points earned (compat wrapper)."""
        return BreakoutPhysics.resolve_bricks(ball, bricks, speed).points

    @staticmethod
    def resolve_bricks(ball: Ball, bricks: list[Brick], speed: float) -> BrickResolution:
        """Bounce the ball off the first brick it touches and resolve damage.

        Explosive bricks drag their neighbours (and any further explosives
        they reach) into the blast, so one well-aimed hit can clear a corner.
        """
        result = BrickResolution()
        for brick in bricks:
            if not brick.alive or not ball.rect.colliderect(brick.rect):
                continue
            # Reflect first so the ball is already moving away when the
            # (possibly multi-brick) explosion resolves below.
            BreakoutPhysics.reflect(ball, BreakoutPhysics.contact_normal(ball, brick))
            BreakoutPhysics.damage_brick(brick, bricks, result, depth=0)
            break  # one bounce per frame keeps collisions stable
        return result

    @staticmethod
    def damage_brick(brick: Brick, bricks: list[Brick], result: BrickResolution,
                     depth: int = 0) -> None:
        """Damage *brick*, chaining through explosives. Fills *result*."""
        if not brick.alive:
            return
        if brick.hit():
            result.destroyed.append(brick)
            result.points += brick.points
            if brick.brick_type is BrickType.EXPLOSIVE and depth < BreakoutPhysics.MAX_CHAIN_DEPTH:
                for neighbour in BreakoutPhysics.neighbours(brick, bricks):
                    result.chain_count += 1
                    BreakoutPhysics.damage_brick(neighbour, bricks, result, depth + 1)
        else:
            # Surviving a hit (hard brick, or indestructible which never dies)
            # still counts as contact for scoring/feedback purposes.
            result.damaged.append(brick)

    @staticmethod
    def neighbours(brick: Brick, bricks: list[Brick]) -> list[Brick]:
        """Alive bricks orthogonally touching *brick* (for explosive chains)."""
        out: list[Brick] = []
        tol = BreakoutPhysics.TOUCH_TOLERANCE
        for other in bricks:
            if other is brick or not other.alive:
                continue
            side_touch = (
                abs(brick.rect.right - other.rect.left) <= tol
                or abs(other.rect.right - brick.rect.left) <= tol
            )
            vertical_touch = (
                abs(brick.rect.bottom - other.rect.top) <= tol
                or abs(other.rect.bottom - brick.rect.top) <= tol
            )
            overlaps_y = brick.rect.top < other.rect.bottom and other.rect.top < brick.rect.bottom
            overlaps_x = brick.rect.left < other.rect.right and other.rect.left < brick.rect.right
            if (side_touch and overlaps_y) or (vertical_touch and overlaps_x):
                out.append(other)
        return out


# --------------------------------------------------------------------------
# Level generation
# --------------------------------------------------------------------------
def _brick_style(brick_type: BrickType, row: int) -> tuple[config.Color, int, int]:
    """(colour, hp, points) for a brick of *type* in *row*."""
    if brick_type is BrickType.HARD:
        return config.LIGHT_GREY, 2 + row // 3, 25
    if brick_type is BrickType.INDESTRUCTIBLE:
        return config.GREY, 1, 0
    if brick_type is BrickType.EXPLOSIVE:
        return config.RED, 1, 30
    return config.BRICK_COLORS[row % len(config.BRICK_COLORS)], 1, 10


def build_level(level: int, rng: random.Random | None = None) -> list[Brick]:
    """Generate the brick layout for *level* (1-based); harder as it rises.

    Level 1 is a gentle wall of normal bricks with a hard top row; higher
    levels add steel (indestructible) blockers and explosive bricks, plus
    extra rows - so clearing deep runs genuinely ramps up the challenge.
    """
    rng = rng or random.Random()
    rows = min(config.BREAKOUT_BRICK_ROWS + (level - 1) // 2, 8)
    cols = config.BREAKOUT_BRICK_COLS
    side = config.BRICK_SIDE_MARGIN
    top = config.BRICK_TOP_OFFSET
    avail_w = config.SCREEN_WIDTH - side * 2
    bw = avail_w // cols
    bh = config.BREAKOUT_BRICK_HEIGHT

    bricks: list[Brick] = []
    for r in range(rows):
        for c in range(cols):
            brick_type = BrickType.NORMAL
            if r == 0:
                # Top row: level 1 uses tough bricks, later levels use a
                # checkerboard of indestructible steel that the ball ricochets off.
                brick_type = BrickType.HARD if level == 1 else (
                    BrickType.INDESTRUCTIBLE if (r + c) % 2 == 0 else BrickType.HARD
                )
            elif level >= 3 and rng.random() < 0.12:
                brick_type = BrickType.EXPLOSIVE
            elif level >= 2 and rng.random() < 0.15:
                brick_type = BrickType.HARD
            color, hp, points = _brick_style(brick_type, r)
            rect = pygame.Rect(side + c * bw + 2, top + r * bh + 2, bw - 4, bh - 4)
            bricks.append(Brick(rect, color, hp=hp, points=points, brick_type=brick_type))
    return bricks


def destructible_left(bricks: list[Brick]) -> int:
    """How many bricks still need breaking to clear the level."""
    return sum(1 for b in bricks if b.alive and b.brick_type is not BrickType.INDESTRUCTIBLE)


# --------------------------------------------------------------------------
# The game
# --------------------------------------------------------------------------
class BreakoutGame(BaseGame):
    """Playable Breakout with power-ups and multi-level progression."""

    name = "Breakout"
    description = "Smash every brick, catch power-ups and clear 5 levels"
    score_key = "breakout"
    fps = config.BREAKOUT_FPS
    music_track = "arcade"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.rng = random.Random()
        self._build_level()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _build_level(self) -> None:
        self.paddle_base_width = config.PADDLE_WIDTH
        self.paddle = pygame.Rect(
            (config.SCREEN_WIDTH - self.paddle_base_width) // 2,
            config.SCREEN_HEIGHT - 50,
            self.paddle_base_width,
            config.PADDLE_HEIGHT,
        )
        self.balls: list[Ball] = []
        self.trails: list[BallTrail] = []
        self.lasers: list[LaserBolt] = []
        self.powerups: list[FallingPowerUp] = []
        self.level = 1
        self.ball_speed = self._base_speed_for(self.level)
        self.lives = config.BREAKOUT_LIVES
        self.game_over = False
        self.won = False
        self.score = 0
        self._stuck = True  # ball waits on the paddle until launch
        self._wide_timer = 0.0
        self._laser_timer = 0.0
        self._last_laser = 0
        self._clear_timer = 0.0   # banner countdown between levels
        self.phase = "playing"    # "playing" | "clear"
        self.bricks = build_level(self.level, self.rng)
        self._reset_ball()

    @staticmethod
    def _base_speed_for(level: int) -> float:
        """Ball speed baseline; each level plays a little faster."""
        return config.BALL_BASE_SPEED + (level - 1) * config.BREAKOUT_SPEED_PER_LEVEL

    def reset(self) -> None:
        super().reset()
        self._build_level()

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
                elif event.key in (pygame.K_SPACE, pygame.K_UP) and not self.game_over:
                    self._launch()
        return True

    def _launch(self) -> None:
        if not self._stuck or not self.balls:
            return
        self.balls[0].launch(self.ball_speed)
        self._stuck = False

    def _reset_ball(self) -> None:
        """Back to a single ball resting on the paddle."""
        self.balls = [Ball(self.paddle.centerx, self.paddle.top - config.BALL_SIZE)]
        self.trails = [BallTrail()]
        self.lasers.clear()
        self.powerups.clear()
        self._stuck = True

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.game_over or self.won:
            return
        if self.phase == "clear":
            # Short breather between levels while the banner is up.
            self._clear_timer -= dt
            if self._clear_timer <= 0:
                self._advance_level()
            return

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.paddle.x -= 8
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.paddle.x += 8
        self.paddle.left = max(0, min(self.paddle.left, config.SCREEN_WIDTH - self.paddle.width))

        # Timed paddle upgrades
        if self._wide_timer > 0:
            self._wide_timer -= dt
            if self._wide_timer <= 0:
                self._restore_paddle()
        if self._laser_timer > 0:
            self._laser_timer -= dt
            if keys[pygame.K_SPACE]:
                self._fire_laser()
        elif keys[pygame.K_SPACE] and self._stuck:
            self._launch()

        if self._stuck:
            # While "stuck" the ball rides the paddle until the player
            # launches it, so they can aim before play starts.
            ball = self.balls[0]
            ball.x = float(self.paddle.centerx)
            ball.y = float(self.paddle.top - config.BALL_SIZE)
            return

        self._update_balls()
        self._update_lasers()
        self._update_powerups()

        if destructible_left(self.bricks) == 0:
            self._clear_level()

    def _update_balls(self) -> None:
        lost: list[Ball] = []
        for ball in self.balls:
            BreakoutPhysics.integrate(ball)
            if not BreakoutPhysics.bounce_walls(ball, config.SCREEN_WIDTH, config.SCREEN_HEIGHT):
                lost.append(ball)
                continue
            before = ball.speed
            BreakoutPhysics.bounce_paddle(ball, self.paddle, self.ball_speed)
            if before != ball.speed:
                self.audio.play("paddle")
            resolution = BreakoutPhysics.resolve_bricks(ball, self.bricks, self.ball_speed)
            if resolution.hit_any:
                self._on_brick_hit(resolution)
        if lost:
            # Keep trails aligned with their balls when one drops off-screen.
            survivors = [b for b in self.balls if b not in lost]
            self.trails = [t for b, t in zip(self.balls, self.trails, strict=False) if b not in lost]
            self.balls = survivors
            if not self.balls:
                self._lose_life()
                return
        # Speed up without changing course: rescale to the new magnitude
        # while preserving every ball's direction.
        if self.balls and self.ball_speed != self.balls[0].speed:
            for ball in self.balls:
                ball.rescale(self.ball_speed)
        for ball, trail in zip(self.balls, self.trails, strict=False):
            trail.record(ball.x, ball.y)

    def _on_brick_hit(self, resolution: BrickResolution) -> None:
        self.score += resolution.points
        if resolution.destroyed:
            self.ball_speed += config.BALL_SPEEDUP_PER_HIT
            for brick in resolution.destroyed:
                if brick.brick_type is BrickType.EXPLOSIVE:
                    self.audio.play("explode")
                else:
                    self.audio.play("brick")
                kind = roll_powerup(self.rng)
                if kind is not None:
                    self.powerups.append(
                        FallingPowerUp(brick.rect.centerx, brick.rect.centery, kind)
                    )
        elif resolution.damaged:
            self.audio.play("brick_hard")  # a hard brick shrugged the hit off

    def _fire_laser(self) -> None:
        now = pygame.time.get_ticks()
        if now - self._last_laser < config.LASER_COOLDOWN_MS:
            return
        self._last_laser = now
        self.lasers.append(LaserBolt(self.paddle.left + 6, self.paddle.top))
        self.lasers.append(LaserBolt(self.paddle.right - 6, self.paddle.top))
        self.audio.play("laser")

    def _update_lasers(self) -> None:
        for laser in self.lasers:
            laser.update()
            for brick in self.bricks:
                if brick.alive and laser.rect.colliderect(brick.rect):
                    laser.alive = False
                    resolution = BrickResolution()
                    BreakoutPhysics.damage_brick(brick, self.bricks, resolution)
                    self._on_brick_hit(resolution)
                    break
        self.lasers = [bolt for bolt in self.lasers if bolt.alive]

    def _update_powerups(self) -> None:
        caught: list[FallingPowerUp] = []
        for powerup in self.powerups:
            powerup.update()
            if powerup.rect.colliderect(self.paddle):
                caught.append(powerup)
                self._apply_powerup(powerup.kind)
            elif powerup.y - powerup.size > config.SCREEN_HEIGHT:
                caught.append(powerup)
        self.powerups = [p for p in self.powerups if p not in caught]

    def _apply_powerup(self, kind: PowerUpType) -> None:
        self.audio.play("powerup")
        if kind is PowerUpType.WIDE:
            self._widen_paddle()
        elif kind is PowerUpType.MULTI:
            self._split_balls()
        elif kind is PowerUpType.LASER:
            self._laser_timer = config.LASER_SECONDS
        elif kind is PowerUpType.LIFE:
            self.lives += 1

    # -- power-up effects ------------------------------------------------
    def _widen_paddle(self) -> None:
        """Widen the paddle (keeping its centre) for a few seconds."""
        center = self.paddle.centerx
        new_width = int(self.paddle_base_width * config.PADDLE_WIDE_SCALE)
        self.paddle.width = new_width
        self.paddle.centerx = center
        self._wide_timer = config.PADDLE_WIDE_SECONDS

    def _restore_paddle(self) -> None:
        center = self.paddle.centerx
        self.paddle.width = self.paddle_base_width
        self.paddle.centerx = center

    def _split_balls(self) -> None:
        """Turn each live ball into several deflected copies (capped)."""
        extra: list[Ball] = []
        for ball in self.balls:
            if len(self.balls) + len(extra) >= 4:
                break
            extra.extend(ball.split_angles())
        if not extra:
            return
        self.balls.extend(extra)
        self.trails.extend(BallTrail() for _ in extra)
        self._stuck = False

    # -- lives / levels --------------------------------------------------
    def _lose_life(self) -> None:
        self.lives -= 1
        self.audio.play("life_lost")
        self._restore_paddle()
        self._wide_timer = 0.0
        self._laser_timer = 0.0
        if self.lives <= 0:
            self.game_over = True
            if self.highscores.is_top_n(self.score_key, self.score):
                self.submit_score()
        else:
            self.ball_speed = self._base_speed_for(self.level)
            self._reset_ball()

    def _clear_level(self) -> None:
        """Enter the between-level banner phase."""
        self.phase = "clear"
        self._clear_timer = 1.8
        self.score += 250
        self.audio.play("level_clear")

    def _advance_level(self) -> None:
        if self.level >= config.BREAKOUT_LEVEL_COUNT:
            self.won = True
            self.submit_score()
            return
        self.level += 1
        self.ball_speed = self._base_speed_for(self.level)
        self.bricks = build_level(self.level, self.rng)
        self._restore_paddle()
        self._wide_timer = 0.0
        self._laser_timer = 0.0
        self._reset_ball()
        self.phase = "playing"

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BREAKOUT_BG)
        self._draw_bricks(surface)
        self._draw_paddle(surface)
        self._draw_balls(surface)
        self._draw_lasers(surface)
        self._draw_powerups(surface)

        items = [
            f"Score: {self.score}",
            f"Lives: {self.lives}",
            f"Level: {self.level}/{config.BREAKOUT_LEVEL_COUNT}",
            f"Best: {self.best_score}",
        ]
        if self._laser_timer > 0:
            items.append(f"LASER {self._laser_timer:.0f}s")
        if self._wide_timer > 0:
            items.append(f"WIDE {self._wide_timer:.0f}s")
        self.draw_hud(surface, *items)

        if self.phase == "clear":
            draw_text(surface, f"LEVEL {self.level} CLEAR!", config.FONT_SIZE_LARGE,
                      config.YELLOW, center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2))
        if self._stuck and not (self.game_over or self.won):
            draw_text(surface, "SPACE to launch  |  A/D or arrows to move",
                      config.FONT_SIZE_SMALL, config.LIGHT_GREY,
                      center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 100))
        if self.won:
            self.draw_game_over(surface, message="YOU CLEARED THE BOARD!", subtitle="+250 bonus")
        elif self.game_over:
            self.draw_game_over(surface)

    def _draw_bricks(self, surface: pygame.Surface) -> None:
        for brick in self.bricks:
            if not brick.alive:
                continue
            pygame.draw.rect(surface, brick.color, brick.rect, border_radius=3)
            if brick.brick_type is BrickType.HARD:
                # White outline + a crack per hit already taken.
                pygame.draw.rect(surface, config.WHITE, brick.rect, 2, border_radius=3)
                for i in range(max(0, 3 - brick.hp)):
                    x = brick.rect.left + 10 + i * 14
                    pygame.draw.line(surface, config.DARK_GREY,
                                     (x, brick.rect.top + 3), (x + 6, brick.rect.bottom - 3), 2)
            elif brick.brick_type is BrickType.INDESTRUCTIBLE:
                pygame.draw.rect(surface, config.DARK_GREY, brick.rect, 2, border_radius=3)
                # Rivets make steel bricks read as "unbreakable" at a glance.
                for cx in (brick.rect.left + 6, brick.rect.right - 6):
                    for cy in (brick.rect.top + 5, brick.rect.bottom - 5):
                        pygame.draw.circle(surface, config.DARK_GREY, (cx, cy), 2)
            elif brick.brick_type is BrickType.EXPLOSIVE:
                pygame.draw.polygon(surface, config.YELLOW, [
                    (brick.rect.centerx, brick.rect.top + 4),
                    (brick.rect.right - 6, brick.rect.centery),
                    (brick.rect.centerx, brick.rect.bottom - 4),
                    (brick.rect.left + 6, brick.rect.centery),
                ])

    def _draw_paddle(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, config.PADDLE_COLOR, self.paddle, border_radius=8)
        if self._laser_timer > 0:
            # Laser emitters on the paddle tips while armed.
            for x in (self.paddle.left + 4, self.paddle.right - 8):
                pygame.draw.rect(surface, config.ORANGE, (x, self.paddle.top - 6, 4, 8))

    def _draw_balls(self, surface: pygame.Surface) -> None:
        for ball, trail in zip(self.balls, self.trails, strict=False):
            # Tail: oldest points are smallest/faintest.
            points = trail.points()
            for i, (x, y) in enumerate(reversed(points)):
                ratio = (i + 1) / (len(points) + 1)
                radius = max(1, int(ball.radius * ratio))
                br, bg, bb = config.BALL_COLOR
                color = (int(br * ratio), int(bg * ratio), int(bb * ratio))
                pygame.draw.circle(surface, color, (int(x), int(y)), radius)
            pygame.draw.circle(surface, config.BALL_COLOR,
                               (int(ball.x), int(ball.y)), ball.radius)

    def _draw_lasers(self, surface: pygame.Surface) -> None:
        for laser in self.lasers:
            pygame.draw.rect(surface, config.ORANGE, laser.rect, border_radius=2)

    def _draw_powerups(self, surface: pygame.Surface) -> None:
        for powerup in self.powerups:
            letter, color = POWERUP_STYLE[powerup.kind]
            pygame.draw.rect(surface, color, powerup.rect, border_radius=6)
            draw_text(surface, letter, config.FONT_SIZE_SMALL, config.WHITE,
                      center=powerup.rect.center)
