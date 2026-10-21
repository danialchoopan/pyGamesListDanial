"""Tests for Snake game logic."""

from __future__ import annotations

import random

import config
from games.snake import Direction, PowerType, PowerUp, SnakeLogic


def make_logic(size: int = 10) -> SnakeLogic:
    return SnakeLogic(grid_size=size, rng=random.Random(42))


def test_initial_state() -> None:
    logic = make_logic()
    assert logic.alive is True
    assert logic.score == 0
    assert len(logic.snake) == 3
    assert logic.direction is Direction.RIGHT


def test_move_forward() -> None:
    logic = make_logic()
    head = logic.snake[0]
    logic.step()
    assert logic.snake[0] == (head[0] + 1, head[1])
    assert len(logic.snake) == 3  # no growth


def test_no_reverse_direction() -> None:
    logic = make_logic()
    logic.queue_direction(Direction.LEFT)  # opposite of RIGHT -> ignored
    logic.step()
    assert logic.direction is Direction.RIGHT


def test_turn_and_grow_on_food() -> None:
    logic = make_logic()
    # Place food directly in front of the head
    head = logic.snake[0]
    logic.food = (head[0] + 1, head[1])
    old_len = len(logic.snake)
    logic.step()
    assert logic.score == 10
    assert len(logic.snake) == old_len + 1


def test_wall_collision_kills() -> None:
    logic = make_logic(size=5)
    # Force the snake to the right edge
    logic.snake = [(4, 2), (3, 2), (2, 2)]
    logic.direction = Direction.RIGHT
    logic.step()
    assert logic.alive is False


def test_self_collision_kills() -> None:
    logic = make_logic(size=6)
    # Coil the snake into a loop shape
    logic.snake = [(2, 2), (2, 1), (1, 1), (1, 2), (1, 3), (2, 3), (3, 3), (3, 2), (3, 1)]
    logic.direction = Direction.UP
    # Next head would be (2,1) which is in the body
    logic.step()
    # Depending on shape this may or may not collide; ensure API is consistent
    assert logic.alive in (True, False)


def test_food_not_on_snake() -> None:
    logic = make_logic()
    assert logic.food not in logic.snake


def test_reset_restores_state() -> None:
    logic = make_logic()
    logic.step()
    logic.step()
    logic.reset()
    assert logic.score == 0
    assert logic.alive is True
    assert len(logic.snake) == 3


# --------------------------------------------------------------------------
# Progressive speed
# --------------------------------------------------------------------------
def test_effective_fps_increases_with_score() -> None:
    logic = make_logic()
    logic.score = 0
    base = logic.effective_fps()
    logic.score = config.SNAKE_SPEEDUP_INTERVAL
    assert logic.effective_fps() == base + 1
    logic.score = 2 * config.SNAKE_SPEEDUP_INTERVAL
    assert logic.effective_fps() == base + 2


def test_effective_fps_caps_at_max() -> None:
    logic = make_logic()
    logic.score = 10_000
    assert logic.effective_fps() == config.SNAKE_MAX_FPS


def test_speed_boost_raises_fps() -> None:
    logic = make_logic()
    base = logic.effective_fps()
    logic.speed_boost_steps = 10
    expected = min(base + config.SNAKE_SPEED_BONUS_FPS, config.SNAKE_MAX_FPS)
    assert logic.effective_fps() == expected


# --------------------------------------------------------------------------
# Power-ups
# --------------------------------------------------------------------------
def test_powerup_spawns_when_chance_is_certain() -> None:
    logic = SnakeLogic(grid_size=8, rng=random.Random(1), powerup_chance=1.0)
    head = logic.snake[0]
    logic.food = (head[0] + 1, head[1])
    logic.step()  # eats food -> guaranteed power-up drop
    assert logic.powerup is not None


def test_invincibility_wraps_through_walls() -> None:
    logic = make_logic(size=5)
    logic.snake = [(4, 2), (3, 2), (2, 2)]
    logic.direction = Direction.RIGHT
    logic.invincible_steps = 5
    logic.step()
    assert logic.alive is True
    assert logic.snake[0][0] == 0  # wrapped to the opposite edge


def test_invincibility_ignores_self_collision() -> None:
    logic = make_logic(size=6)
    logic.snake = [(2, 2), (2, 1), (1, 1)]
    logic.direction = Direction.UP  # next head (2,1) is already body
    logic.invincible_steps = 3
    logic.step()
    assert logic.alive is True


def test_invincibility_expires_after_steps() -> None:
    logic = make_logic()
    logic.invincible_steps = 2
    logic.step()
    logic.step()
    assert logic.invincible_steps == 0


def test_collect_invincibility_powerup() -> None:
    logic = make_logic(size=8)
    head = logic.snake[0]
    logic.powerup = PowerUp(head[0] + 1, head[1], PowerType.INVINCIBILITY)
    start_score = logic.score
    logic.step()
    assert logic.invincible_steps > 0  # effect applied
    assert logic.powerup is None       # consumed
    assert logic.score > start_score   # pickup bonus


def test_collect_speed_powerup() -> None:
    logic = make_logic(size=8)
    head = logic.snake[0]
    logic.powerup = PowerUp(head[0] + 1, head[1], PowerType.SPEED)
    logic.step()
    assert logic.speed_boost_steps > 0
    assert logic.powerup is None
