"""Tests for the Space Shooter's headless logic.

Covers the object pool (recycling + exhaustion fallback), particle system,
bullet movement, the three enemy movement archetypes (Grunt / Sine / Diver),
the achievement tracker, the upgrade shop and the wave manager (including
boss waves and fleet recycling). Rendering and pygame input are excluded so
the suite stays fast and display-free.
"""

from __future__ import annotations

import random

import pytest

import config
from games.space_shooter import (
    ACHIEVEMENTS,
    AchievementTracker,
    Bullet,
    EnemyShip,
    EnemyType,
    ObjectPool,
    Particle,
    ParticleSystem,
    Shop,
    WaveManager,
)


# --------------------------------------------------------------------------
# Object pool
# --------------------------------------------------------------------------
def test_pool_starts_with_full_capacity() -> None:
    pool: ObjectPool[dict[str, str]] = ObjectPool(dict, size=5)
    assert pool.available == 5
    assert pool.in_use == 0
    assert pool.created == 5


def test_acquire_checks_out_and_release_recycles_same_object() -> None:
    pool: ObjectPool[dict[str, str]] = ObjectPool(dict, size=2)
    first = pool.acquire()
    assert first is not None
    assert pool.in_use == 1
    assert pool.available == 1
    pool.release(first)
    assert pool.in_use == 0
    assert pool.acquire() is first  # the very same instance came back


def test_acquire_returns_none_when_exhausted() -> None:
    pool: ObjectPool[dict[str, str]] = ObjectPool(dict, size=1)
    assert pool.acquire() is not None
    assert pool.acquire() is None  # pool empty -> caller allocates a fallback


def test_release_ignores_object_not_from_this_pool() -> None:
    pool: ObjectPool[dict[str, str]] = ObjectPool(dict, size=1)
    outsider: dict[str, str] = dict()
    pool.release(outsider)  # must not inflate the free list
    assert pool.available == 1


def test_release_all_returns_every_object() -> None:
    pool: ObjectPool[dict[str, str]] = ObjectPool(dict, size=3)
    got = [pool.acquire() for _ in range(3)]
    assert pool.available == 0
    pool.release_all([obj for obj in got if obj is not None])
    assert pool.available == 3
    assert pool.in_use == 0


# --------------------------------------------------------------------------
# Particles
# --------------------------------------------------------------------------
def test_particle_moves_and_decays() -> None:
    p = Particle(x=0.0, y=0.0, vx=10.0, vy=-5.0, life=1.0, max_life=1.0, color=(255, 255, 255))
    p.update(0.5)
    assert p.x == pytest.approx(5.0)
    assert p.y == pytest.approx(-2.5)
    assert p.life == pytest.approx(0.5)
    assert p.alive is True


def test_particle_dies_at_zero_life() -> None:
    p = Particle(x=0.0, y=0.0, vx=0.0, vy=0.0, life=0.1, max_life=0.1, color=(1, 1, 1))
    p.update(0.2)
    assert p.alive is False


def test_particle_t_goes_from_fresh_to_dying() -> None:
    p = Particle(x=0, y=0, vx=0, vy=0, life=1.0, max_life=1.0, color=(0, 0, 0))
    assert p.t == pytest.approx(0.0)
    p.update(0.5)
    assert p.t == pytest.approx(0.5, abs=1e-6)


def test_emit_explosion_spawns_requested_count() -> None:
    ps = ParticleSystem(pool_size=50)
    spawned = ps.emit_explosion(100, 200, (255, 0, 0), count=10)
    assert spawned == 10
    assert ps.active_count == 10
    # Every particle starts at the burst origin.
    assert all(p.x == 100 and p.y == 200 for p in ps.particles)


def test_emit_explosion_drops_when_pool_exhausted() -> None:
    ps = ParticleSystem(pool_size=4)
    spawned = ps.emit_explosion(0, 0, (0, 255, 0), count=10)
    assert spawned == 4
    assert ps.dropped == 6  # the rest were counted as dropped, not lost silently


def test_particle_system_update_recycles_dead_particles() -> None:
    ps = ParticleSystem(pool_size=10)
    ps.emit_explosion(0, 0, (255, 255, 0), count=5, life=0.1)
    assert ps.active_count == 5
    ps.update(1.0)  # outlive every particle
    assert ps.active_count == 0
    # Recycled: a second burst can still spawn the full count.
    assert ps.emit_explosion(0, 0, (1, 2, 3), count=5) == 5


def test_particle_system_clear_returns_everything() -> None:
    ps = ParticleSystem(pool_size=10)
    ps.emit_explosion(5, 5, (9, 9, 9), count=6)
    ps.clear()
    assert ps.active_count == 0
    assert ps.emit_explosion(0, 0, (0, 0, 0), count=10) == 10


# --------------------------------------------------------------------------
# Bullets
# --------------------------------------------------------------------------
def test_bullet_moves_by_velocity() -> None:
    b = Bullet(x=100, y=100, vy=-8, from_player=True)
    b.update()
    assert b.y == 92  # player bullets travel up


def test_bullet_dies_when_leaving_screen() -> None:
    b = Bullet(x=0, y=config.SCREEN_HEIGHT + 30, vy=5, from_player=False)
    b.update()
    assert b.alive is False


def test_bullet_stays_alive_on_screen() -> None:
    b = Bullet(x=0, y=200, vy=-5, from_player=True)
    b.update()
    assert b.alive is True


def test_bullet_spawn_resets_all_fields() -> None:
    b = Bullet(x=0, y=0, vy=1, from_player=False)
    b.alive = False
    b.spawn(50, 60, -4, from_player=True)
    assert (b.x, b.y, b.vy, b.from_player, b.alive) == (50, 60, -4, True, True)


# --------------------------------------------------------------------------
# Enemy movement archetypes
# --------------------------------------------------------------------------
def test_grunt_marches_with_the_fleet() -> None:
    e = EnemyShip(x=100, y=100, speed=2.0, kind=EnemyType.GRUNT)
    e.update(direction=1, bounds=(0, config.SCREEN_WIDTH))
    assert e.x == pytest.approx(102.0)
    assert e.diving is False


def test_sine_weaves_horizontally() -> None:
    e = EnemyShip(x=200, y=100, speed=0.0, kind=EnemyType.SINE)
    # With zero march speed, the only horizontal change is the sine sway.
    e.update(direction=0, bounds=(0, config.SCREEN_WIDTH))
    sway = e.x - 200.0
    assert sway != 0.0  # it wobbled
    assert e.diving is False


def test_diver_stays_in_formation_until_timer_fires() -> None:
    e = EnemyShip(x=300, y=100, speed=2.0, kind=EnemyType.DIVER)
    # A single update: the 2s dive timer barely ticks down, no dive yet.
    e.update(direction=1, bounds=(0, config.SCREEN_WIDTH), player_x=150)
    assert e.diving is False


def test_diver_begins_diving_after_timer_and_homes_on_player() -> None:
    e = EnemyShip(x=300, y=100, speed=2.0, kind=EnemyType.DIVER)
    e._dive_timer = 0.0  # force the dive to start immediately
    # Call 1 flips the state machine from "march" to "dive" (diving is True);
    # the actual dive movement happens on the next update.
    e.update(direction=1, bounds=(0, config.SCREEN_WIDTH), player_x=150)
    assert e.diving is True
    e.update(direction=1, bounds=(0, config.SCREEN_WIDTH), player_x=150)
    assert e.y > 100  # it accelerated downward
    assert e.x < 302  # it homed horizontally toward the player's lane (150)


def test_diver_climbs_back_after_reaching_depth() -> None:
    e = EnemyShip(x=200, y=config.ENEMY_DIVE_DEPTH - 1, speed=2.0, kind=EnemyType.DIVER)
    e._dive_state = "dive"
    e.update(direction=1, bounds=(0, config.SCREEN_WIDTH), player_x=200)
    # At (or past) the depth it flips to climbing, so the next update rises.
    y_after_dive = e.y
    e.update(direction=1, bounds=(0, config.SCREEN_WIDTH), player_x=200)
    assert e.y < y_after_dive  # moving back up
    assert e.diving is True  # still diving (climb counts as off-formation)


def test_enemy_spawn_resets_behaviour_state() -> None:
    e = EnemyShip(x=0, y=0, kind=EnemyType.DIVER)
    e._dive_state = "dive"
    e._dive_timer = 0.0
    e.spawn(50, 60, hp=3, speed=1.5, kind=EnemyType.GRUNT)
    assert (e.x, e.y, e.hp, e.speed, e.kind) == (50, 60, 3, 1.5, EnemyType.GRUNT)
    assert e.diving is False
    assert e.alive is True


def test_enemy_rect_is_centered_on_position() -> None:
    e = EnemyShip(x=100, y=100)
    assert e.rect.center == (100, 100)


# --------------------------------------------------------------------------
# Achievements
# --------------------------------------------------------------------------
def test_achievement_definitions_are_well_formed() -> None:
    keys = [a.key for a in ACHIEVEMENTS]
    assert len(keys) == len(set(keys))  # no duplicate keys
    assert all(a.title and a.description for a in ACHIEVEMENTS)


def test_unlock_marks_achievement_once() -> None:
    tracker = AchievementTracker()
    assert tracker.is_unlocked("first_blood") is False
    assert tracker.unlock("first_blood") is True
    assert tracker.is_unlocked("first_blood") is True
    assert tracker.unlock("first_blood") is False  # already unlocked


def test_unknown_achievement_key_is_ignored() -> None:
    tracker = AchievementTracker()
    assert tracker.unlock("no-such-achievement") is False
    assert tracker.all_keys() == set()


def test_preseeded_unlocks_are_preserved() -> None:
    tracker = AchievementTracker(unlocked={"wave_5"})
    assert tracker.is_unlocked("wave_5") is True
    assert tracker.unlock("wave_5") is False


def test_reset_clears_everything() -> None:
    tracker = AchievementTracker()
    tracker.unlock("first_blood")
    tracker.reset()
    assert tracker.all_keys() == set()


# --------------------------------------------------------------------------
# Upgrade shop
# --------------------------------------------------------------------------
def test_shop_starts_with_no_upgrades() -> None:
    shop = Shop()
    assert shop.fire_cooldown_ms == config.BULLET_COOLDOWN_MS
    assert shop.shot_count == 1
    assert shop.max_shield == 0


def test_rapid_upgrade_shortens_fire_cooldown() -> None:
    shop = Shop(credits=1000)
    base = shop.fire_cooldown_ms
    assert shop.buy("rapid") is True
    assert shop.fire_cooldown_ms < base


def test_multi_upgrade_adds_a_shot() -> None:
    shop = Shop(credits=1000)
    assert shop.shot_count == 1
    shop.buy("multi")
    assert shop.shot_count == 2


def test_shield_upgrade_raises_max_shield() -> None:
    shop = Shop(credits=1000)
    shop.buy("shield")
    assert shop.max_shield == 1


def test_buy_fails_when_unaffordable() -> None:
    shop = Shop(credits=0)
    assert shop.buy("rapid") is False
    assert shop.rapid_level == 0


def test_buy_fails_when_maxed_out() -> None:
    shop = Shop(credits=10_000)
    for _ in range(config.UPGRADE_RAPID_MAX):
        assert shop.buy("rapid") is True
    assert shop.cost("rapid") == -1
    assert shop.buy("rapid") is False


def test_unknown_upgrade_kind_is_rejected() -> None:
    shop = Shop(credits=10_000)
    assert shop.buy("hyperspeed") is False
    assert shop.cost("hyperspeed") == -1


def test_grant_wave_clear_scales_with_wave() -> None:
    shop = Shop()
    shop.grant_wave_clear(1)
    first = shop.credits
    shop.grant_wave_clear(3)
    assert shop.credits == first + config.WAVE_BONUS_BASE * 3


# --------------------------------------------------------------------------
# Wave manager
# --------------------------------------------------------------------------
def test_wave_manager_starts_on_wave_one() -> None:
    mgr = WaveManager(rng=random.Random(0))
    assert mgr.wave == 1
    assert mgr.alive_enemies  # a fleet exists
    assert mgr.is_wave_cleared is False


def test_wave_one_fleet_has_all_three_behaviour_types() -> None:
    mgr = WaveManager(rng=random.Random(0))
    kinds = {e.kind for e in mgr.alive_enemies}
    # Row 0 is Grunt, odd rows are Sine, even (non-zero) rows are Diver.
    assert EnemyType.GRUNT in kinds
    assert EnemyType.SINE in kinds
    assert EnemyType.DIVER in kinds


def test_fleet_marches_side_to_side() -> None:
    mgr = WaveManager(rng=random.Random(0))
    before = [e.x for e in mgr.alive_enemies]
    mgr.update(player_x=400)
    after = [e.x for e in mgr.alive_enemies]
    assert after != before


def test_fleet_reverses_and_drops_at_screen_edge() -> None:
    mgr = WaveManager(rng=random.Random(0))
    # Push the whole fleet against the right edge moving right.
    for e in mgr.enemies:
        e.x = config.SCREEN_WIDTH - 5
    mgr.direction = 1
    mgr.update(player_x=400)
    assert mgr.direction == -1  # bounced
    # And every ship dropped a row (the Galaga descent).
    assert all(e.y >= 90 for e in mgr.alive_enemies)


def test_start_next_wave_increments_and_respawns() -> None:
    mgr = WaveManager(rng=random.Random(0))
    first_ids = {id(e) for e in mgr.alive_enemies}
    mgr.start_next_wave()
    assert mgr.wave == 2
    second_ids = {id(e) for e in mgr.alive_enemies}
    # The previous fleet was recycled (hulls reused), so ids may overlap,
    # but the fleet is definitely non-empty and freshly spawned.
    assert mgr.alive_enemies
    assert mgr.is_wave_cleared is False
    assert first_ids != set() and second_ids != set()


def test_kill_marks_dead_and_recycles_hull() -> None:
    mgr = WaveManager(rng=random.Random(0))
    victim = mgr.alive_enemies[0]
    mgr.kill(victim)
    assert victim.alive is False
    assert victim not in mgr.alive_enemies
    assert mgr.pooled_in_use == len(mgr.alive_enemies)  # victim returned


def test_wave_cleared_when_every_enemy_dead() -> None:
    mgr = WaveManager(rng=random.Random(0))
    for enemy in list(mgr.alive_enemies):
        mgr.kill(enemy)
    assert mgr.is_wave_cleared is True


def test_random_shooter_picks_an_alive_enemy() -> None:
    mgr = WaveManager(rng=random.Random(0))
    shooter = mgr.random_shooter()
    assert shooter is not None
    assert shooter.alive is True


def test_random_shooter_returns_none_when_empty() -> None:
    mgr = WaveManager(rng=random.Random(0))
    for enemy in list(mgr.alive_enemies):
        mgr.kill(enemy)
    assert mgr.random_shooter() is None


# --------------------------------------------------------------------------
# Boss waves
# --------------------------------------------------------------------------
def test_boss_wave_every_fifth_wave() -> None:
    mgr = WaveManager(rng=random.Random(0))
    assert mgr.is_boss_wave() is False  # wave 1
    for _ in range(4):
        mgr.start_next_wave()
    assert mgr.wave == 5
    assert mgr.is_boss_wave() is True


def test_boss_spawned_on_boss_wave_with_escort() -> None:
    mgr = WaveManager(rng=random.Random(0))
    for _ in range(4):
        mgr.start_next_wave()
    assert mgr.wave == 5
    boss = mgr.boss
    assert boss is not None
    assert boss.hp == config.BOSS_BASE_HP
    assert boss.w == 170 and boss.h == 80
    # Boss + 3 escorts.
    assert len(mgr.alive_enemies) == 4


def test_boss_absent_on_normal_wave() -> None:
    mgr = WaveManager(rng=random.Random(0))
    assert mgr.boss is None  # wave 1 is not a boss wave


def test_boss_hp_scales_on_later_boss_waves() -> None:
    mgr = WaveManager(rng=random.Random(0))
    for _ in range(9):
        mgr.start_next_wave()
    assert mgr.wave == 10
    assert mgr.is_boss_wave() is True
    assert mgr.boss is not None
    assert mgr.boss.hp == config.BOSS_BASE_HP + config.BOSS_HP_PER_WAVE


def test_fleet_difficulty_scales_with_wave() -> None:
    mgr = WaveManager(rng=random.Random(0))
    wave1_speed = mgr.alive_enemies[0].speed
    mgr.start_next_wave()
    wave2_speed = mgr.alive_enemies[0].speed
    assert wave2_speed > wave1_speed


def test_reset_returns_to_wave_one_with_fresh_fleet() -> None:
    mgr = WaveManager(rng=random.Random(0))
    for _ in range(7):
        mgr.start_next_wave()
    assert mgr.wave == 8
    mgr.reset()
    assert mgr.wave == 1
    assert mgr.alive_enemies
    assert mgr.is_boss_wave() is False
