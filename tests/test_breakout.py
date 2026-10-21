"""Tests for Breakout physics."""

from __future__ import annotations

import pygame

import config
from games.breakout import Ball, BreakoutPhysics, Brick


def test_bounce_side_walls() -> None:
    ball = Ball(2, 100)
    ball.vx = -5.0
    ball.vy = -3.0
    alive = BreakoutPhysics.bounce_walls(ball, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    assert alive is True
    assert ball.vx > 0  # reflected
    assert ball.x >= ball.radius


def test_bounce_top_wall() -> None:
    ball = Ball(100, 1)
    ball.vy = -5.0
    BreakoutPhysics.bounce_walls(ball, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    assert ball.vy > 0


def test_ball_drops_below() -> None:
    ball = Ball(100, config.SCREEN_HEIGHT + 50)
    ball.vy = 5.0
    alive = BreakoutPhysics.bounce_walls(ball, config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    assert alive is False


def test_bounce_paddle_center_straight_up() -> None:
    paddle = pygame.Rect(400, 700, config.PADDLE_WIDTH, config.PADDLE_HEIGHT)
    ball = Ball(paddle.centerx, paddle.top - 1)
    ball.vy = 5.0
    speed = 6.0
    BreakoutPhysics.bounce_paddle(ball, paddle, speed)
    assert ball.vy < 0  # bounced upward
    assert abs(ball.vx) < 0.5  # dead centre -> nearly vertical


def test_bounce_paddle_edge_angles() -> None:
    paddle = pygame.Rect(400, 700, config.PADDLE_WIDTH, config.PADDLE_HEIGHT)
    ball = Ball(paddle.right - 2, paddle.top - 1)
    ball.vy = 5.0
    BreakoutPhysics.bounce_paddle(ball, paddle, 6.0)
    assert ball.vy < 0
    assert ball.vx > 0  # right edge kicks right


def test_brick_destroyed_awards_points() -> None:
    rect = pygame.Rect(100, 100, 60, 26)
    brick = Brick(rect, config.RED, hp=1, points=10)
    ball = Ball(rect.centerx, rect.bottom - 1)
    ball.vy = 5.0
    earned = BreakoutPhysics.bounce_bricks(ball, [brick], speed=6.0)
    assert earned == 10
    assert brick.alive is False


def test_tough_brick_takes_two_hits() -> None:
    rect = pygame.Rect(100, 100, 60, 26)
    brick = Brick(rect, config.RED, hp=2, points=20)
    ball = Ball(rect.centerx, rect.bottom - 1)
    ball.vy = 5.0
    assert BreakoutPhysics.bounce_bricks(ball, [brick], 6.0) == 0  # hp 2->1
    assert brick.alive is True
    assert BreakoutPhysics.bounce_bricks(ball, [brick], 6.0) == 20
    assert brick.alive is False


def test_ball_launch_angle_within_range() -> None:
    ball = Ball(500, 700)
    ball.launch(speed=6.0, rng_angle=0.6)
    assert ball.vy < 0  # upward
    assert abs(ball.vx) < 6.0
