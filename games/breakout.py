"""Breakout / Arkanoid.

Bounce the ball off a paddle to smash all the bricks. Ball physics live
in :class:`BreakoutPhysics` for headless testing.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pygame

import config
from base_game import BaseGame
from utils import draw_text


class Ball:
    """The breakable ball."""

    def __init__(self, x: float, y: float) -> None:
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

    def launch(self, speed: float, rng_angle: float = 0.6) -> None:
        """Launch upward at a slightly randomised angle."""
        import random

        angle = math.pi / 2 - rng_angle / 2 + random.random() * rng_angle
        self.vx = speed * math.cos(angle)
        self.vy = -speed * math.sin(angle)


class Brick:
    """A single breakable brick."""

    def __init__(self, rect: pygame.Rect, color: config.Color, hp: int = 1, points: int = 10) -> None:
        self.rect = rect
        self.color = color
        self.hp = hp
        self.points = points
        self.alive = True

    def hit(self) -> bool:
        """Take one hit; return True when destroyed."""
        self.hp -= 1
        if self.hp <= 0:
            self.alive = False
        return not self.alive


class BreakoutPhysics:
    """Pure helpers for ball movement and collision resolution."""

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
        """Bounce off the paddle, angling based on hit position."""
        if ball.vy > 0 and ball.rect.colliderect(paddle) and ball.y < paddle.centery:
            ball.y = paddle.top - ball.radius
            offset = (ball.x - paddle.centerx) / (paddle.width / 2)
            offset = max(-1.0, min(1.0, offset))
            angle = offset * (math.pi / 3)  # up to 60 degrees
            ball.vx = speed * math.sin(angle)
            ball.vy = -speed * math.cos(angle)

    @staticmethod
    def bounce_bricks(ball: Ball, bricks: list[Brick], speed: float) -> int:
        """Resolve brick collisions; return points earned."""
        earned = 0
        for brick in bricks:
            if not brick.alive or not ball.rect.colliderect(brick.rect):
                continue
            # Determine minimal penetration axis for the bounce direction
            overlap_x = min(ball.rect.right - brick.rect.left, brick.rect.right - ball.rect.left)
            overlap_y = min(ball.rect.bottom - brick.rect.top, brick.rect.bottom - ball.rect.top)
            if overlap_x < overlap_y:
                ball.vx = -ball.vx
            else:
                ball.vy = -ball.vy
            if brick.hit():
                earned += brick.points
            break  # one brick per frame keeps collisions stable
        return earned


class BreakoutGame(BaseGame):
    """Playable Breakout."""

    name = "Breakout"
    description = "Smash every brick with your paddle and ball"
    score_key = "breakout"
    fps = config.BREAKOUT_FPS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._build_level()

    def _build_level(self) -> None:
        self.paddle = pygame.Rect(
            (config.SCREEN_WIDTH - config.PADDLE_WIDTH) // 2,
            config.SCREEN_HEIGHT - 50,
            config.PADDLE_WIDTH,
            config.PADDLE_HEIGHT,
        )
        self.ball = Ball(config.SCREEN_WIDTH / 2, self.paddle.top - config.BALL_SIZE)
        self.ball_speed = config.BALL_BASE_SPEED
        self.lives = config.BREAKOUT_LIVES
        self.game_over = False
        self.won = False
        self.score = 0
        self._stuck = True  # ball waits on the paddle until launch
        self.bricks: list[Brick] = []
        rows = config.BREAKOUT_BRICK_ROWS
        cols = config.BREAKOUT_BRICK_COLS
        side = config.BRICK_SIDE_MARGIN
        top = config.BRICK_TOP_OFFSET
        avail_w = config.SCREEN_WIDTH - side * 2
        bw = avail_w // cols
        bh = config.BREAKOUT_BRICK_HEIGHT
        for r in range(rows):
            color = config.BRICK_COLORS[r % len(config.BRICK_COLORS)]
            for c in range(cols):
                rect = pygame.Rect(side + c * bw + 2, top + r * bh + 2, bw - 4, bh - 4)
                # Top rows take two hits for extra challenge
                hp = 2 if r == 0 else 1
                points = 20 if hp == 2 else 10
                self.bricks.append(Brick(rect, color, hp=hp, points=points))

    def reset(self) -> None:
        super().reset()
        self._build_level()

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
        if self._stuck:
            self.ball.launch(self.ball_speed)
            self._stuck = False

    def _reset_ball(self) -> None:
        self.ball = Ball(self.paddle.centerx, self.paddle.top - config.BALL_SIZE)
        self.ball_speed = config.BALL_BASE_SPEED
        self._stuck = True

    def update(self, dt: float) -> None:
        if self.game_over or self.won:
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.paddle.x -= 8
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.paddle.x += 8
        self.paddle.left = max(0, min(self.paddle.left, config.SCREEN_WIDTH - self.paddle.width))

        if self._stuck:
            self.ball.x = float(self.paddle.centerx)
            self.ball.y = float(self.paddle.top - config.BALL_SIZE)
            return

        BreakoutPhysics.integrate(self.ball)
        if not BreakoutPhysics.bounce_walls(self.ball, config.SCREEN_WIDTH, config.SCREEN_HEIGHT):
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                if self.highscores.is_top_n(self.score_key, self.score):
                    self.submit_score()
            else:
                self._reset_ball()
            return
        BreakoutPhysics.bounce_paddle(self.ball, self.paddle, self.ball_speed)
        earned = BreakoutPhysics.bounce_bricks(self.ball, self.bricks, self.ball_speed)
        if earned:
            self.score += earned
            self.ball_speed += config.BALL_SPEEDUP_PER_HIT
            # Preserve direction while scaling speed
            mag = math.hypot(self.ball.vx, self.ball.vy) or 1.0
            self.ball.vx *= self.ball_speed / mag
            self.ball.vy *= self.ball_speed / mag

        if all(not b.alive for b in self.bricks):
            self.won = True
            self.score += 250
            self.submit_score()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BREAKOUT_BG)
        for brick in self.bricks:
            if brick.alive:
                pygame.draw.rect(surface, brick.color, brick.rect, border_radius=3)
                if brick.hp > 1:
                    pygame.draw.rect(surface, config.WHITE, brick.rect, 2, border_radius=3)
        pygame.draw.rect(surface, config.PADDLE_COLOR, self.paddle, border_radius=8)
        pygame.draw.circle(surface, config.BALL_COLOR, (int(self.ball.x), int(self.ball.y)), self.ball.radius)

        self.draw_hud(
            surface,
            f"Score: {self.score}",
            f"Lives: {self.lives}",
            f"Best: {self.best_score}",
        )
        if self._stuck and not (self.game_over or self.won):
            draw_text(surface, "SPACE to launch  |  A/D or arrows to move",
                      config.FONT_SIZE_SMALL, config.LIGHT_GREY,
                      center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 100))
        if self.won:
            self.draw_game_over(surface, message="YOU CLEARED THE BOARD!", subtitle="+250 bonus")
        elif self.game_over:
            self.draw_game_over(surface)
