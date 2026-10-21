"""Tests for Breakout physics and the newer mechanics (brick types, explosive
chains, reflection, ball trail, power-ups and level generation)."""

from __future__ import annotations

import random

import pygame
import pytest

import config
from games.breakout import (
    Ball,
    BallTrail,
    BreakoutPhysics,
    Brick,
    BrickResolution,
    BrickType,
    FallingPowerUp,
    LaserBolt,
    PowerUpType,
    build_level,
    destructible_left,
    roll_powerup,
)


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


# --------------------------------------------------------------------------
# Brick types
# --------------------------------------------------------------------------
def _brick(x: int, y: int, brick_type: BrickType = BrickType.NORMAL,
           hp: int = 1, points: int = 10) -> Brick:
    return Brick(pygame.Rect(x, y, 60, 26), config.RED, hp=hp, points=points,
                 brick_type=brick_type)


def test_indestructible_brick_never_breaks() -> None:
    brick = _brick(100, 100, BrickType.INDESTRUCTIBLE, hp=1, points=0)
    assert brick.hit() is False
    assert brick.hit() is False  # still alive no matter how many hits
    assert brick.alive is True
    assert brick.hp == 1  # hp untouched


def test_hard_brick_takes_extra_hits() -> None:
    brick = _brick(100, 100, BrickType.HARD, hp=3, points=25)
    assert brick.hit() is False and brick.alive is True  # 3 -> 2
    assert brick.hit() is False and brick.alive is True  # 2 -> 1
    assert brick.hit() is True and brick.alive is False   # 1 -> 0


def test_indestructible_shows_up_in_damaged_not_destroyed() -> None:
    ball = Ball(130, 100)
    ball.vx, ball.vy = 0.0, 5.0
    steel = _brick(100, 100, BrickType.INDESTRUCTIBLE)
    res = BreakoutPhysics.resolve_bricks(ball, [steel], speed=6.0)
    assert res.hit_any is True
    assert steel in res.damaged
    assert res.destroyed == []
    assert res.points == 0


# --------------------------------------------------------------------------
# Reflection
# --------------------------------------------------------------------------
def test_reflect_preserves_speed() -> None:
    ball = Ball(0, 0)
    ball.vx, ball.vy = 3.0, 4.0
    before = ball.speed
    BreakoutPhysics.reflect(ball, (1.0, 0.0))  # bounce off a vertical wall
    assert ball.vx == pytest.approx(-3.0)
    assert ball.vy == pytest.approx(4.0)
    assert ball.speed == pytest.approx(before)  # magnitude unchanged


def test_reflect_about_diagonal_normal() -> None:
    ball = Ball(0, 0)
    ball.vx, ball.vy = 5.0, 0.0
    inv = 2 ** -0.5
    BreakoutPhysics.reflect(ball, (inv, inv))  # 45-degree mirror
    # v' = v - 2(v.n)n with v=(5,0), n=(1,1)/sqrt2 -> (0,-5).
    assert ball.vx == pytest.approx(0.0)
    assert ball.vy == pytest.approx(-5.0)


def test_contact_normal_side_hit_picks_horizontal_face() -> None:
    brick = _brick(100, 100)
    # Ball grazes the brick's LEFT face (small horizontal overlap).
    ball = Ball(brick.rect.left - 2, brick.rect.centery)
    ball.vx = -4.0
    normal = BreakoutPhysics.contact_normal(ball, brick)
    assert normal == (1.0, 0.0)  # push back to the right


def test_contact_normal_top_hit_picks_vertical_face() -> None:
    brick = _brick(100, 100)
    # Ball grazes the brick's TOP face (small vertical overlap).
    ball = Ball(brick.rect.centerx, brick.rect.top - 2)
    ball.vy = 4.0
    normal = BreakoutPhysics.contact_normal(ball, brick)
    assert normal == (0.0, -1.0)  # push back upward


# --------------------------------------------------------------------------
# Explosive chains
# --------------------------------------------------------------------------
def test_explosive_destroys_neighbours() -> None:
    # Three bricks side by side; the middle is explosive.
    left = _brick(100, 100)
    boom = _brick(164, 100, BrickType.EXPLOSIVE, points=30)
    right = _brick(228, 100)
    ball = Ball(boom.rect.centerx, boom.rect.bottom - 1)
    ball.vy = 5.0
    res = BreakoutPhysics.resolve_bricks(ball, [left, boom, right], speed=6.0)
    assert boom.alive is False and left.alive is False and right.alive is False
    assert res.points == 30 + 10 + 10  # explosive + both neighbours
    assert res.chain_count == 2


def test_chain_stops_at_max_depth() -> None:
    # A long row of explosives: the chain is capped at MAX_CHAIN_DEPTH.
    bricks = [_brick(100 + i * 64, 100, BrickType.EXPLOSIVE, points=30) for i in range(10)]
    ball = Ball(bricks[0].rect.centerx, bricks[0].rect.bottom - 1)
    ball.vy = 5.0
    res = BreakoutPhysics.resolve_bricks(ball, bricks, speed=6.0)
    # The direct hit plus a bounded number of chained neighbours.
    assert res.chain_count <= BreakoutPhysics.MAX_CHAIN_DEPTH + 1
    assert bricks[0].alive is False


def test_neighbours_ignores_diagonal_and_distant_bricks() -> None:
    centre = _brick(100, 100)
    diagonal = _brick(164, 130)  # offset both axes -> not a neighbour
    distant = _brick(400, 100)   # same row but far away
    assert BreakoutPhysics.neighbours(centre, [centre, diagonal, distant]) == []


def test_neighbours_finds_side_and_bottom_touch() -> None:
    centre = _brick(100, 100)
    right = _brick(164, 100)         # touches the right face
    below = _brick(100, 130)         # touches the bottom face
    found = BreakoutPhysics.neighbours(centre, [centre, right, below])
    # Brick is a non-frozen dataclass (unhashable), so compare by identity.
    assert len(found) == 2
    assert any(b is right for b in found)
    assert any(b is below for b in found)


def test_resolve_bricks_bounces_off_brick() -> None:
    brick = _brick(100, 100)
    ball = Ball(brick.rect.centerx, brick.rect.bottom - 1)
    ball.vx, ball.vy = 0.0, 5.0
    BreakoutPhysics.resolve_bricks(ball, [brick], speed=6.0)
    assert ball.vy < 0  # reflected upward, away from the brick


# --------------------------------------------------------------------------
# Ball trail
# --------------------------------------------------------------------------
def test_trail_records_newest_first() -> None:
    trail = BallTrail(length=5)
    trail.record(1, 1)
    trail.record(2, 2)
    trail.record(3, 3)
    assert trail.points()[0] == (3, 3)  # newest at the front


def test_trail_is_capped_at_length() -> None:
    trail = BallTrail(length=3)
    for i in range(10):
        trail.record(i, i)
    assert len(trail) == 3
    assert trail.points() == [(9, 9), (8, 8), (7, 7)]


def test_trail_clear_empties_it() -> None:
    trail = BallTrail(length=4)
    trail.record(1, 1)
    trail.clear()
    assert len(trail) == 0
    assert trail.points() == []


# --------------------------------------------------------------------------
# Power-ups and lasers
# --------------------------------------------------------------------------
def test_falling_powerup_moves_down() -> None:
    token = FallingPowerUp(x=100, y=50, kind=PowerUpType.WIDE)
    token.update()
    assert token.y == pytest.approx(50 + config.POWERUP_FALL_SPEED)


def test_powerup_rect_is_centered() -> None:
    token = FallingPowerUp(x=100, y=100, kind=PowerUpType.LIFE)
    assert token.rect.center == (100, 100)


def test_roll_powerup_returns_valid_kind_or_none() -> None:
    rng = random.Random(0)
    for _ in range(50):
        rolled = roll_powerup(rng)
        assert rolled is None or isinstance(rolled, PowerUpType)


def test_roll_powerup_deterministic_seed_is_repeatable() -> None:
    first = [roll_powerup(random.Random(42)) for _ in range(10)]
    second = [roll_powerup(random.Random(42)) for _ in range(10)]
    assert first == second  # same seed -> same drops


def test_laser_bolt_rises_and_dies_off_screen() -> None:
    bolt = LaserBolt(x=100, y=config.SCREEN_HEIGHT // 2)
    bolt.update()
    assert bolt.y == pytest.approx(config.SCREEN_HEIGHT // 2 + LaserBolt.LASER_SPEED)
    assert bolt.alive is True
    # Drive it far above the screen.
    bolt.y = -5
    bolt.update()
    assert bolt.alive is False


# --------------------------------------------------------------------------
# Level generation
# --------------------------------------------------------------------------
def test_build_level_one_is_a_playable_wall() -> None:
    bricks = build_level(1, rng=random.Random(0))
    assert bricks  # non-empty
    # Level 1 has a HARD top row and normal bricks below (no steel/explosive).
    assert any(b.brick_type is BrickType.HARD for b in bricks)
    assert all(b.brick_type is not BrickType.INDESTRUCTIBLE for b in bricks)
    assert all(b.brick_type is not BrickType.EXPLOSIVE for b in bricks)


def test_higher_levels_introduce_steel_and_explosives() -> None:
    bricks = build_level(4, rng=random.Random(0))
    types = {b.brick_type for b in bricks}
    assert BrickType.INDESTRUCTIBLE in types
    assert BrickType.EXPLOSIVE in types


def test_build_level_more_rows_on_higher_levels() -> None:
    low = build_level(1, rng=random.Random(0))
    high = build_level(6, rng=random.Random(0))
    assert len(high) > len(low)


def test_brick_grid_does_not_overlap() -> None:
    bricks = build_level(3, rng=random.Random(0))
    for i, a in enumerate(bricks):
        for b in bricks[i + 1:]:
            assert not a.rect.colliderect(b.rect)


def test_destructible_left_ignores_steel() -> None:
    normal = _brick(0, 0, BrickType.NORMAL)
    steel = _brick(100, 0, BrickType.INDESTRUCTIBLE)
    assert destructible_left([normal, steel]) == 1
    normal.alive = False
    assert destructible_left([normal, steel]) == 0


def test_brick_resolution_hit_any_false_when_nothing_touched() -> None:
    res = BrickResolution()
    assert res.hit_any is False


def test_ball_speed_is_magnitude_and_rescale_keeps_direction() -> None:
    ball = Ball(0, 0)
    ball.vx, ball.vy = 3.0, 4.0
    assert ball.speed == pytest.approx(5.0)
    ball.rescale(10.0)
    assert ball.speed == pytest.approx(10.0)
    # Direction preserved (still the 3-4-5 slope).
    assert ball.vx / ball.vy == pytest.approx(3.0 / 4.0)


def test_split_angles_fans_balls_around_original_path() -> None:
    ball = Ball(100, 100)
    ball.vx, ball.vy = 0.0, -6.0  # straight up
    extras = ball.split_angles(count=2, angle=0.5)
    assert len(extras) == 2
    assert all(b.speed == pytest.approx(6.0) for b in extras)
    # The two extras head left and right of straight up.
    assert extras[0].vx < 0
    assert extras[1].vx > 0
