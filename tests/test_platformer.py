"""Tests for the Platformer's headless logic.

Covers the level format, AABB physics resolution, the sprite animator, timed
power-up effects, the level manager (progression + custom JSON) and the
in-game level editor. Rendering and pygame input are deliberately excluded so
the suite stays fast and display-free.
"""

from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from games.platformer import (
    BUILTIN_LEVELS,
    EDITABLE_TILES,
    KNOWN_TILES,
    TILE,
    ActiveEffect,
    Enemy,
    LevelEditor,
    LevelManager,
    PhysicsBody,
    PlatformerLevel,
    SpriteAnimator,
    _move_axis,
    level_from_json,
    level_from_rows,
)


def _flat_level(width: int = 20, floor_row: int = 5) -> PlatformerLevel:
    """Open-topped box: solid floor plus walls down the left/right edges."""
    rows = ["#" + "." * (width - 2) + "#" for _ in range(floor_row)]
    rows.append("#" * width)  # solid floor
    return PlatformerLevel(rows=rows)


# --------------------------------------------------------------------------
# Level format
# --------------------------------------------------------------------------
def test_level_pads_ragged_rows_to_uniform_width() -> None:
    level = PlatformerLevel(rows=["###", "#", "#####"])
    assert level.width == 5
    assert all(len(r) == 5 for r in level.rows)
    assert level.tile_at(4, 1) == "."  # padded with empty space


def test_tile_out_of_bounds_is_empty() -> None:
    level = _flat_level()
    assert level.tile_at(-1, 0) == "."
    assert level.tile_at(0, 999) == "."
    assert level.tile_at(999, 999) == "."


def test_find_tiles_locates_every_occurrence() -> None:
    level = PlatformerLevel(rows=["...", ".#.", "..#"])
    assert level.find_tiles("#") == [(1, 1), (2, 2)]
    assert level.find_tiles("o") == []


def test_solid_at_detects_overlap_and_respects_edges() -> None:
    level = PlatformerLevel(rows=["....", "....", "####"])
    floor = pygame.Rect(0, 2 * TILE, 4 * TILE, TILE)
    assert level.solid_at(pygame.Rect(0, 2 * TILE, TILE, TILE)) is True
    # A rect that only abuts the floor (bottom edge == floor top) is NOT solid.
    assert level.solid_at(pygame.Rect(0, 2 * TILE - TILE, TILE, TILE)) is False
    assert floor.collidepoint(5, 2 * TILE + 5)


def test_problems_flags_bad_levels() -> None:
    assert "level has no rows" in PlatformerLevel(rows=[]).problems()
    empty = PlatformerLevel(rows=["....", "...."])
    assert any("player start" in p for p in empty.problems())
    assert any("goal flag" in p for p in empty.problems())
    assert any("no ground" in p for p in empty.problems())
    unknown = PlatformerLevel(rows=["P.F", "###", "??"])
    assert any("unknown tiles" in p for p in unknown.problems())


def test_valid_level_has_no_problems() -> None:
    assert PlatformerLevel(rows=["P..F", "####"]).problems() == []


def test_level_from_rows_raises_on_bad_input() -> None:
    with pytest.raises(ValueError):
        level_from_rows(["....", "...."])
    assert level_from_rows(["P.F", "###"]).problems() == []


def test_every_builtin_level_is_playable() -> None:
    for rows in BUILTIN_LEVELS:
        level = level_from_rows(rows)  # raises if unplayable
        assert level.problems() == []
        assert len(level.find_tiles("P")) == 1
        assert level.find_tiles("F")
        assert any(c in KNOWN_TILES for row in level.rows for c in row)


def test_level_from_json_round_trips() -> None:
    spec = level_from_json('{"title": "My Level", "rows": ["P.F", "###"]}')
    assert spec.title == "My Level"
    assert spec.rows == ("P.F", "###")
    with pytest.raises(ValueError):
        level_from_json("not json")
    with pytest.raises(ValueError):
        level_from_json('{"title": "x", "rows": []}')


# --------------------------------------------------------------------------
# Physics
# --------------------------------------------------------------------------
def test_falling_body_lands_on_floor_and_flags_ground() -> None:
    level = _flat_level()
    # 32x34 body: bottom 194 is 6px above the floor at row 5 (y=200).
    body = PhysicsBody(x=2 * TILE, y=160, vy=10.0)
    _move_axis(body, level, axis="y")
    assert body.on_ground is True
    assert body.vy == 0.0
    assert body.rect.bottom == 5 * TILE  # resting exactly on the floor


def test_rising_body_stops_at_ceiling() -> None:
    # 3-tile-tall shaft with a solid tile capping col 2 at row 0.
    level = PlatformerLevel(rows=["..#" + "." * 17, "." * 20, "." * 20])
    body = PhysicsBody(x=2 * TILE, y=TILE, vy=-20.0)
    _move_axis(body, level, axis="y")
    assert body.on_ground is False
    assert body.vy == 0.0
    assert body.rect.top == TILE  # snapped just below the ceiling tile


def test_walking_into_wall_is_blocked_and_speed_zeroed() -> None:
    level = _flat_level()
    # 32px body just left of the right wall (col 19 = x 760..800). A 30px
    # step carries its right edge (782) into the wall, which the resolver
    # must push back out and zero the velocity.
    body = PhysicsBody(x=720, y=160, vx=30.0)
    _move_axis(body, level, axis="x")
    assert body.vx == 0.0
    assert level.solid_at(body.rect) is False  # resolved out of the wall
    assert body.rect.right <= 19 * TILE  # never past the wall's left edge


def test_free_fall_keeps_velocity_when_open() -> None:
    level = _flat_level()
    body = PhysicsBody(x=TILE, y=TILE, vy=3.0)
    _move_axis(body, level, axis="y")
    assert body.on_ground is False
    assert body.vy == 3.0  # untouched: no collision to resolve


def test_enemy_patrol_turns_around_at_wall() -> None:
    # Corridor wide enough for the enemy to actually reach the right wall:
    # 20 tiles (800px) with walls at both ends and floor under the whole span.
    width = 20
    rows = ["#" + "." * (width - 2) + "#"] * 4 + ["#" * width]
    level = PlatformerLevel(rows=rows)
    enemy = Enemy(x=2 * TILE, y=126, direction=1, speed=3.0)
    for _ in range(300):  # march right until the wall forces a reversal
        enemy.update(level)
    # It must have backed away from the right-hand wall.
    assert enemy.direction == -1
    assert level.solid_at(enemy.rect) is False
    assert enemy.rect.right <= (width - 1) * TILE


def test_enemy_does_not_walk_off_a_ledge() -> None:
    # Floor under cols 0-11 only; cols 12-19 are an open pit.
    width = 20
    rows = ["." * width] * 4 + ["#" * 12 + "." * (width - 12)]
    level = PlatformerLevel(rows=rows)
    enemy = Enemy(x=2 * TILE, y=126, direction=1, speed=2.0)
    for _ in range(250):
        enemy.update(level)
        if enemy.direction == -1:
            break
    # It stopped at the ledge and reversed instead of marching into thin air.
    assert enemy.direction == -1
    assert enemy.rect.right <= 12 * TILE + enemy.speed


def test_dead_enemy_does_not_move() -> None:
    level = _flat_level()
    enemy = Enemy(x=3 * TILE, y=126, direction=1, alive=False)
    enemy.update(level)
    assert enemy.vx == 0.0 and enemy.direction == 1


# --------------------------------------------------------------------------
# Sprite animator
# --------------------------------------------------------------------------
def test_animator_cycles_through_frames() -> None:
    anim = SpriteAnimator(frame_count=4, fps=10.0)
    assert anim.frame == 0
    assert anim.tick(0.1) == 1
    assert anim.tick(0.1) == 2
    assert anim.tick(0.1) == 3
    assert anim.tick(0.1) == 0  # wraps back to the start


def test_animator_reset_returns_to_first_frame() -> None:
    anim = SpriteAnimator(frame_count=3, fps=10.0)
    anim.tick(0.5)
    assert anim.frame != 0
    anim.reset()
    assert anim.frame == 0


def test_animator_rejects_zero_frames() -> None:
    with pytest.raises(ValueError):
        SpriteAnimator(frame_count=0)


# --------------------------------------------------------------------------
# Power-up effects
# --------------------------------------------------------------------------
def test_effect_counts_down_and_expires() -> None:
    fx = ActiveEffect(kind="star", remaining=1.0, duration=1.0)
    assert fx.active is True
    fx.tick(0.4)
    assert fx.remaining == pytest.approx(0.6)
    fx.tick(1.0)
    assert fx.remaining == 0.0
    assert fx.active is False


def test_effect_extend_refreshes_but_caps_at_duration() -> None:
    fx = ActiveEffect(kind="speed", remaining=0.2, duration=2.0)
    fx.extend(1.0)
    assert fx.remaining == pytest.approx(1.2)
    fx.extend(99.0)
    assert fx.remaining == pytest.approx(2.0)  # capped at the original duration


# --------------------------------------------------------------------------
# Level manager
# --------------------------------------------------------------------------
def test_level_manager_counts_builtin_levels() -> None:
    mgr = LevelManager()
    assert mgr.count == len(BUILTIN_LEVELS)
    assert mgr.current.title.startswith("Level")


def test_advance_walks_levels_then_reports_last() -> None:
    mgr = LevelManager()
    for _ in range(len(BUILTIN_LEVELS) - 1):
        assert mgr.advance() is True
    assert mgr.advance() is False  # already on the final level


def test_save_custom_persists_and_appears_after_reload(tmp_path: Path) -> None:
    mgr = LevelManager(extra_dir=tmp_path)
    base_count = mgr.count
    rows = ["P..F", "####"]
    index = mgr.save_custom("my-level", rows)
    assert (tmp_path / "my-level.json").is_file()
    assert mgr.count == base_count + 1
    assert mgr.levels[index].title == "my-level"

    # A fresh manager over the same directory must pick the file up.
    again = LevelManager(extra_dir=tmp_path)
    assert again.count == base_count + 1


def test_save_custom_rejects_unplayable_rows(tmp_path: Path) -> None:
    mgr = LevelManager(extra_dir=tmp_path)
    with pytest.raises(ValueError):
        mgr.save_custom("broken", ["....", "...."])


def test_save_custom_without_directory_raises() -> None:
    mgr = LevelManager(extra_dir=None)
    with pytest.raises(ValueError):
        mgr.save_custom("x", ["P.F", "###"])


def test_reload_skips_broken_custom_files(tmp_path: Path) -> None:
    (tmp_path / "good.json").write_text('{"title": "g", "rows": ["P.F", "###"]}')
    (tmp_path / "bad.json").write_text("this is not json")
    mgr = LevelManager(extra_dir=tmp_path)
    titles = [s.title for s in mgr.levels]
    assert "g" in titles
    assert mgr.count == len(BUILTIN_LEVELS) + 1


# --------------------------------------------------------------------------
# Level editor
# --------------------------------------------------------------------------
def test_editor_starts_blank_and_rejects_bad_brush() -> None:
    ed = LevelEditor(width=6, height=3)
    assert ed.brush == "#"
    assert ed.set_brush("Z") is False
    assert ed.set_brush("E") is True
    assert ed.brush == "E"


def test_editor_paint_stamps_brush_and_reports_tile() -> None:
    ed = LevelEditor(width=6, height=3)
    assert ed.paint(2, 1) == "#"
    assert ed.rows[1][2] == "#"


def test_editor_paint_out_of_bounds_is_ignored() -> None:
    ed = LevelEditor(width=6, height=3)
    assert ed.paint(99, 1) is None
    assert ed.paint(1, 99) is None
    assert ed.paint(-1, 0) is None


def test_editor_erase_clears_a_cell() -> None:
    ed = LevelEditor(width=6, height=3)
    ed.paint(2, 1)
    assert ed.paint(2, 1, erase=True) == "."
    assert ed.rows[1][2] == "."


def test_editor_keeps_only_one_player_start() -> None:
    ed = LevelEditor(width=6, height=3)
    ed.set_brush("P")
    ed.paint(0, 0)
    ed.paint(5, 2)
    total_p = sum(row.count("P") for row in ed.rows)
    assert total_p == 1
    assert ed.rows[2][5] == "P"  # the newest start won
    assert ed.rows[0][0] == "."  # the old one was cleared


def test_editor_clear_blanks_everything() -> None:
    ed = LevelEditor(width=6, height=3)
    ed.paint(0, 0)
    ed.paint(3, 2)
    ed.clear()
    assert all(set(row) == {"."} for row in ed.rows)


def test_editor_problems_reports_missing_start_and_goal() -> None:
    ed = LevelEditor(width=6, height=3)
    assert ed.problems()  # blank grid is not playable
    ed.set_brush("P")
    ed.paint(0, 2)
    ed.set_brush("F")
    ed.paint(5, 2)
    ed.set_brush("#")
    ed.paint(1, 2)  # add ground beside the start, not over it
    assert ed.problems() == []


def test_editor_dict_round_trip_preserves_grid() -> None:
    ed = LevelEditor(width=6, height=3)
    ed.set_brush("E")
    ed.paint(1, 1)
    clone = LevelEditor.from_dict(ed.to_dict())
    assert clone.to_rows() == ed.to_rows()
    with pytest.raises(ValueError):
        LevelEditor.from_dict({"rows": "not-a-list"})


def test_editor_save_and_load_round_trip(tmp_path: Path) -> None:
    ed = LevelEditor(width=8, height=2)
    ed.set_brush("C")
    ed.paint(3, 0)
    path = tmp_path / "sub" / "level.json"
    ed.save(path)
    loaded = LevelEditor.load(path)
    assert loaded.to_rows() == ed.to_rows()


def test_editor_load_rejects_malformed_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    with pytest.raises(ValueError):
        LevelEditor.load(bad)


def test_editable_tiles_are_all_known() -> None:
    assert set(EDITABLE_TILES) <= KNOWN_TILES
