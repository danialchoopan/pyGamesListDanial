"""Space Shooter (Galaga-style) with pooling, particles, bosses and a shop.

Testable pure-Python pieces:

* :class:`ObjectPool` - pre-allocates and recycles entities so a hail of
  bullets/explosions never triggers garbage-collection hitches.
* :class:`Particle` / :class:`Particle` explosions.
* :class:`WaveManager` - waves, enemy fleets, and a boss every 5th wave.
* :class:`Shop` - the between-wave upgrade store (rapid fire / multi-shot /
  shield).
* :class:`Achievement` / :class:`AchievementTracker` - unlock conditions.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

import pygame

import config
from base_game import BaseGame

T = TypeVar("T")


# --------------------------------------------------------------------------
# Object pool
# --------------------------------------------------------------------------
class ObjectPool(Generic[T]):
    """A fixed-size pool that reuses instances instead of allocating.

    Games create a pool once (pre-allocating *size* objects) and then
    ``acquire()`` / ``release()`` them every frame. When the pool is exhausted
    ``acquire()`` returns ``None`` and the caller falls back to allocating -
    so the pool is an optimisation, never a correctness risk.
    """

    def __init__(self, factory: Callable[[], T], size: int) -> None:
        self._factory = factory
        self._free: list[T] = [factory() for _ in range(size)]
        self._in_use: set[int] = set()  # ids of checked-out objects
        self.created = len(self._free)  # total objects ever allocated

    @property
    def available(self) -> int:
        """Objects currently free to be acquired."""
        return len(self._free)

    @property
    def in_use(self) -> int:
        """Objects currently checked out."""
        return len(self._in_use)

    def acquire(self) -> T | None:
        """Check out a recycled object, or None when the pool is empty."""
        if not self._free:
            return None
        obj = self._free.pop()
        self._in_use.add(id(obj))
        return obj

    def release(self, obj: T) -> None:
        """Return an object to the pool for reuse."""
        if id(obj) in self._in_use:
            self._in_use.discard(id(obj))
            self._free.append(obj)

    def release_all(self, objs: Sequence[T]) -> None:
        """Return several objects at once (e.g. on a wave reset)."""
        for obj in objs:
            self.release(obj)


# --------------------------------------------------------------------------
# Particles
# --------------------------------------------------------------------------
@dataclass
class Particle:
    """A single spark in an explosion."""

    x: float
    y: float
    vx: float
    vy: float
    life: float          # seconds remaining
    max_life: float      # original life, for colour fading
    color: tuple[int, int, int]

    @property
    def alive(self) -> bool:
        return self.life > 0.0

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    @property
    def t(self) -> float:
        """0 (fresh) -> 1 (about to die); used for fade-out."""
        return 1.0 - max(0.0, self.life / self.max_life) if self.max_life else 1.0


class ParticleSystem:
    """Spawns and updates particles, recycling them through an ObjectPool."""

    def __init__(self, pool_size: int = config.PARTICLE_POOL_SIZE) -> None:
        self._pool: ObjectPool[Particle] = ObjectPool(
            lambda: Particle(0, 0, 0, 0, 0, 1, config.WHITE), pool_size
        )
        self._particles: list[Particle] = []
        self.dropped = 0  # explosions we couldn't spawn (pool exhausted)

    @property
    def particles(self) -> list[Particle]:
        return self._particles

    @property
    def active_count(self) -> int:
        return len(self._particles)

    def emit_explosion(
        self, x: float, y: float, color: config.Color, count: int = 22,
        speed: float = 120.0, life: float = config.PARTICLE_MAX_AGE,
    ) -> int:
        """Burst *count* particles outward from (x, y). Returns spawned count."""
        spawned = 0
        for _ in range(count):
            particle = self._pool.acquire()
            if particle is None:
                self.dropped += 1
                continue
            angle = math.tau * random.random()
            velocity = speed * (0.4 + 0.6 * random.random())
            particle.x, particle.y = x, y
            particle.vx = math.cos(angle) * velocity
            particle.vy = math.sin(angle) * velocity
            particle.max_life = life
            particle.life = life
            particle.color = color
            self._particles.append(particle)
            spawned += 1
        return spawned

    def update(self, dt: float) -> None:
        """Advance every particle and recycle the dead ones."""
        for particle in self._particles:
            particle.update(dt)
        dead = [p for p in self._particles if not p.alive]
        if dead:
            self._pool.release_all(dead)
            self._particles = [p for p in self._particles if p.alive]

    def clear(self) -> None:
        """Recycle every live particle (e.g. on reset)."""
        self._pool.release_all(self._particles)
        self._particles.clear()


# --------------------------------------------------------------------------
# Bullets and enemies
# --------------------------------------------------------------------------
class Bullet:
    """A bullet projectile (player or enemy)."""

    def __init__(self, x: float = 0.0, y: float = 0.0, vy: float = 0.0,
                 from_player: bool = True) -> None:
        self.x = x
        self.y = y
        self.vy = vy
        self.from_player = from_player
        self.alive = True
        self.radius = 4

    def spawn(self, x: float, y: float, vy: float, from_player: bool) -> None:
        """(Re)configure a pooled bullet for a new shot."""
        self.x, self.y, self.vy, self.from_player, self.alive = x, y, vy, from_player, True

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self) -> None:
        """Move and cull off-screen bullets."""
        self.y += self.vy
        if self.y < -20 or self.y > config.SCREEN_HEIGHT + 20:
            self.alive = False


class EnemyType(Enum):
    """Movement archetypes. Each needs a different response from the player."""

    GRUNT = "grunt"    # marches with the fleet, turns at screen edges
    DIVER = "diver"    # periodically dives toward the player, then climbs back
    SINE = "sine"      # marches but weaves horizontally in a sine wave


class EnemyShip:
    """A single enemy ship.

    Movement lives here (not in the WaveManager) so a ship fully owns its own
    behaviour and stays trivially testable in isolation.
    """

    def __init__(self, x: float = 0.0, y: float = 0.0, hp: int = 1,
                 speed: float = config.ENEMY_BASE_SPEED,
                 kind: EnemyType = EnemyType.GRUNT) -> None:
        self.x = x
        self.y = y
        self.hp = hp
        self.speed = speed
        self.kind = kind
        self.alive = True
        self.w = 34
        self.h = 26
        # Diver state machine: "march" -> "dive" -> "climb" -> "march".
        self._dive_state = "march"
        self._dive_timer = 2.0
        self._target_x = x
        # Sine weaver phase (radians), advanced every update.
        self._phase = 0.0

    def spawn(self, x: float, y: float, hp: int, speed: float,
              kind: EnemyType = EnemyType.GRUNT) -> None:
        """(Re)configure a pooled hull for a new enemy."""
        self.x, self.y, self.hp, self.speed, self.kind = x, y, hp, speed, kind
        self.alive = True
        self._dive_state = "march"
        self._dive_timer = 2.0
        self._target_x = x
        self._phase = 0.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.w // 2), int(self.y - self.h // 2), self.w, self.h)

    @property
    def diving(self) -> bool:
        """True while a diver has left the formation to attack."""
        return self._dive_state != "march"

    def update(self, direction: int, bounds: tuple[int, int],
               player_x: float | None = None) -> None:
        """Advance one frame. Behaviour depends on :attr:`kind`.

        ``direction`` and ``bounds`` drive the shared fleet march; ``player_x``
        is only needed by divers to aim their attack.
        """
        if self.kind is EnemyType.DIVER:
            self._update_diver(direction, bounds, player_x)
        elif self.kind is EnemyType.SINE:
            self._update_sine(direction, bounds)
        else:
            self._update_grunt(direction, bounds)

    def _clamp_x(self, bounds: tuple[int, int]) -> None:
        lo, hi = bounds
        self.x = max(lo + self.w // 2, min(hi - self.w // 2, self.x))

    def _update_grunt(self, direction: int, bounds: tuple[int, int]) -> None:
        """Plain horizontal march; the WaveManager handles the bounce."""
        self.x += direction * self.speed
        self._clamp_x(bounds)

    def _update_sine(self, direction: int, bounds: tuple[int, int]) -> None:
        """March, plus a horizontal sine sway that makes it hard to lead."""
        self.x += direction * self.speed
        self._phase += config.ENEMY_SINE_FREQ
        self.x += math.cos(self._phase) * (config.ENEMY_SINE_AMPLITUDE * 0.1)
        self._clamp_x(bounds)

    def _update_diver(self, direction: int, bounds: tuple[int, int],
                      player_x: float | None) -> None:
        """Three-phase attack: pick a lane, dive at the player, then climb."""
        if self._dive_state == "march":
            self.x += direction * self.speed
            self._clamp_x(bounds)
            self._dive_timer -= 1.0 / 60.0
            if self._dive_timer <= 0 and player_x is not None:
                # Commit to the player's current lane and begin the dive.
                self._dive_state = "dive"
                self._target_x = player_x
        elif self._dive_state == "dive":
            # Home horizontally toward the lane while accelerating downward.
            self.x += (self._target_x - self.x) * 0.08
            self.y += self.speed * config.ENEMY_DIVE_SPEED_MULT
            if self.y >= config.ENEMY_DIVE_DEPTH:
                self._dive_state = "climb"
        else:  # "climb": retreat back up to rejoin the fleet formation.
            self.y -= self.speed * config.ENEMY_CLIMB_SPEED_MULT
            if self.y <= 90.0:
                self._dive_state = "march"
                self._dive_timer = 2.5


# --------------------------------------------------------------------------
# Achievements
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Achievement:
    """A named milestone with an English description."""

    key: str
    title: str
    description: str


#: All achievements, checked via :meth:`AchievementTracker.check`.
ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement("first_blood", "First Blood", "Destroy your first enemy"),
    Achievement("wave_5", "Getting Warmed Up", "Reach wave 5"),
    Achievement("boss_slayer", "Boss Slayer", "Defeat a boss"),
    Achievement("sharpshooter", "Sharpshooter", "Destroy 25 enemies in one run"),
    Achievement("survivor", "Survivor", "Clear 5 waves without losing a life"),
    Achievement("shopper", "Well Equipped", "Buy 3 upgrades in one run"),
)


class AchievementTracker:
    """Tracks which achievements have been unlocked this run.

    Keys are matched against :data:`ACHIEVEMENTS`; unknown keys are ignored so
    a typo can never crash the game.
    """

    def __init__(self, unlocked: set[str] | None = None) -> None:
        self.unlocked: set[str] = set(unlocked or ())

    def unlock(self, key: str) -> bool:
        """Mark *key* unlocked; returns True only the first time."""
        if key not in {a.key for a in ACHIEVEMENTS}:
            return False
        if key in self.unlocked:
            return False
        self.unlocked.add(key)
        return True

    def is_unlocked(self, key: str) -> bool:
        return key in self.unlocked

    def all_keys(self) -> set[str]:
        return set(self.unlocked)

    def reset(self) -> None:
        self.unlocked.clear()


# --------------------------------------------------------------------------
# Upgrade shop
# --------------------------------------------------------------------------
@dataclass
class Shop:
    """Between-wave upgrade store. Pure logic (no pygame)."""

    credits: int = 0
    rapid_level: int = 0       # 0..UPGRADE_RAPID_MAX
    multi_level: int = 0       # 0..UPGRADE_MULTI_MAX
    shield_level: int = 0      # 0..UPGRADE_SHIELD_MAX
    _purchases: int = field(default=0, repr=False)

    # -- pricing / effects --------------------------------------------
    def cost(self, kind: str) -> int:
        """Price of the next level of *kind*, or -1 if maxed out / unknown."""
        if kind == "rapid":
            if self.rapid_level >= config.UPGRADE_RAPID_MAX:
                return -1
            return config.UPGRADE_RAPID_BASE_COST + self.rapid_level * config.UPGRADE_RAPID_COST_STEP
        if kind == "multi":
            if self.multi_level >= config.UPGRADE_MULTI_MAX:
                return -1
            return config.UPGRADE_MULTI_BASE_COST + self.multi_level * config.UPGRADE_RAPID_COST_STEP
        if kind == "shield":
            if self.shield_level >= config.UPGRADE_SHIELD_MAX:
                return -1
            return config.UPGRADE_SHIELD_BASE_COST + self.shield_level * config.UPGRADE_SHIELD_COST_STEP
        return -1

    def can_buy(self, kind: str) -> bool:
        cost = self.cost(kind)
        return cost >= 0 and self.credits >= cost

    def buy(self, kind: str) -> bool:
        """Purchase the next level of *kind*; False when unaffordable."""
        if not self.can_buy(kind):
            return False
        cost = self.cost(kind)
        self.credits -= cost
        if kind == "rapid":
            self.rapid_level += 1
        elif kind == "multi":
            self.multi_level += 1
        elif kind == "shield":
            self.shield_level += 1
        else:
            return False
        self._purchases += 1
        return True

    @property
    def purchases(self) -> int:
        return self._purchases

    @property
    def fire_cooldown_ms(self) -> int:
        """Player fire delay, shrinking with rapid-fire upgrades."""
        scale = config.UPGRADE_RAPID_COOLDOWN_SCALE ** self.rapid_level
        return max(60, int(config.BULLET_COOLDOWN_MS * scale))

    @property
    def shot_count(self) -> int:
        """Number of bullets fired per trigger pull (multi-shot adds more)."""
        return 1 + self.multi_level

    @property
    def max_shield(self) -> int:
        return self.shield_level

    def grant_wave_clear(self, wave: int) -> None:
        """Award credits for clearing *wave*."""
        self.credits += config.WAVE_BONUS_BASE * wave


# --------------------------------------------------------------------------
# Wave manager
# --------------------------------------------------------------------------
class WaveManager:
    """Spawns, marches and (on boss waves) bosses. Pools enemy hulls."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self._pool: ObjectPool[EnemyShip] = ObjectPool(
            EnemyShip, config.ENEMY_POOL_SIZE
        )
        self.enemies: list[EnemyShip] = []
        self.reset()

    def reset(self) -> None:
        """Reset to wave 1."""
        self.wave = 1
        self.release_fleet()
        self.direction = 1
        self._spawn_wave()

    def release_fleet(self) -> None:
        """Return every enemy hull to the pool."""
        self._pool.release_all(self.enemies)
        self.enemies = []

    def _spawn_enemy(self, x: float, y: float, hp: int, speed: float,
                     kind: EnemyType = EnemyType.GRUNT) -> EnemyShip:
        """Acquire a pooled hull, falling back to a fresh one if exhausted."""
        ship = self._pool.acquire()
        if ship is None:
            ship = EnemyShip()
        ship.spawn(x, y, hp, speed, kind)
        self.enemies.append(ship)
        return ship

    def _pick_kind(self, row: int) -> EnemyType:
        """Assign a movement archetype based on the row the ship sits in.

        Top rows stay predictable (Grunt), the middle weaves (Sine), and the
        bottom row - closest to the player - dives. This makes the fleet read
        as a gradient of threat from top to bottom.
        """
        if row <= 0:
            return EnemyType.GRUNT
        if row % 2 == 1:
            return EnemyType.SINE
        return EnemyType.DIVER

    def is_boss_wave(self, wave: int | None = None) -> bool:
        """True every :data:`config.BOSS_WAVE_INTERVAL`-th wave."""
        check = self.wave if wave is None else wave
        return check % config.BOSS_WAVE_INTERVAL == 0

    @property
    def boss(self) -> EnemyShip | None:
        """The live boss on a boss wave, else None."""
        if not self.is_boss_wave():
            return None
        for enemy in self.enemies:
            if enemy.w > 100:  # boss hull is much wider than a normal ship
                return enemy
        return None

    def _spawn_wave(self) -> None:
        """Create the fleet for the current wave, scaling difficulty."""
        self.release_fleet()
        if self.is_boss_wave():
            self._spawn_boss()
            return
        # Difficulty ramps with the wave number: an extra row every 2 waves
        # (capped at 6), +1 HP every 3 waves, and speed climbs each wave.
        rows = min(config.ENEMY_ROWS + (self.wave - 1) // 2, 6)
        cols = config.ENEMY_COLS
        spacing_x, spacing_y = 90, 60
        grid_w = cols * spacing_x
        ox = (config.SCREEN_WIDTH - grid_w) // 2 + spacing_x // 2
        oy = 90
        hp = 1 + (self.wave - 1) // 3
        speed = config.ENEMY_BASE_SPEED + (self.wave - 1) * 0.4
        for r in range(rows):
            for c in range(cols):
                kind = self._pick_kind(r)
                self._spawn_enemy(ox + c * spacing_x, oy + r * spacing_y, hp, speed, kind)

    def _spawn_boss(self) -> None:
        """Big, high-HP ship that drifts side to side, plus a small escort."""
        boss_wave = self.wave // config.BOSS_WAVE_INTERVAL
        hp = config.BOSS_BASE_HP + (boss_wave - 1) * config.BOSS_HP_PER_WAVE
        boss = self._spawn_enemy(config.SCREEN_WIDTH / 2, 110, hp, speed=1.4)
        boss.w, boss.h = 170, 80
        # A light escort so the wave isn't a pure bullet-sponge.
        escort_speed = config.ENEMY_BASE_SPEED + self.wave * 0.3
        for c in range(3):
            self._spawn_enemy(260 + c * 180, 240, hp=1 + self.wave // 6, speed=escort_speed)

    @property
    def alive_enemies(self) -> list[EnemyShip]:
        return [e for e in self.enemies if e.alive]

    @property
    def is_wave_cleared(self) -> bool:
        """True when every ship (and boss) in the wave is destroyed."""
        return not self.alive_enemies

    def update(self, player_x: float | None = None) -> None:
        """March the fleet side to side; does NOT auto-advance the wave.

        The game decides when to advance (so it can show the upgrade shop
        between waves) by calling :meth:`start_next_wave`. ``player_x`` is the
        live player position, needed only by diving enemies to aim.
        """
        if self.is_wave_cleared:
            return
        alive = self.alive_enemies
        # Find the fleet's horizontal extent; when it hits a screen edge the
        # whole formation reverses and drops - the classic Galaga march.
        left = min(e.rect.left for e in alive)
        right = max(e.rect.right for e in alive)
        if (left <= 0 and self.direction < 0) or (right >= config.SCREEN_WIDTH and self.direction > 0):
            self.direction *= -1
            for e in alive:
                e.y += 24
        for e in alive:
            e.update(self.direction, (0, config.SCREEN_WIDTH), player_x)

    def start_next_wave(self) -> None:
        """Advance to (and spawn) the next wave."""
        self.wave += 1
        self._spawn_wave()

    def kill(self, enemy: EnemyShip) -> None:
        """Mark an enemy dead and return its hull to the pool."""
        enemy.alive = False
        self._pool.release(enemy)

    def random_shooter(self) -> EnemyShip | None:
        """Pick a random alive enemy to fire a bullet."""
        alive = self.alive_enemies
        return self.rng.choice(alive) if alive else None

    @property
    def pooled_in_use(self) -> int:
        return self._pool.in_use


# --------------------------------------------------------------------------
# The game
# --------------------------------------------------------------------------
class SpaceShooterGame(BaseGame):
    """Playable space shooter: waves, a boss every 5th wave, and a shop."""

    name = "Space Shooter"
    description = "Blast alien waves, beat bosses, and buy upgrades"
    score_key = "space_shooter"
    fps = config.SPACE_SHOOTER_FPS
    music_track = "space"

    PLAYER_W = 44
    PLAYER_H = 30

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.wave_mgr = WaveManager()
        self._setup()

    def _setup(self) -> None:
        self.wave_mgr.reset()
        self.player_x = config.SCREEN_WIDTH / 2
        self.player_y = config.SCREEN_HEIGHT - 60
        # Bullets are pooled so firing + explosions never allocate mid-frame.
        self._bullet_pool: ObjectPool[Bullet] = ObjectPool(Bullet, config.BULLET_POOL_SIZE)
        self.bullets: list[Bullet] = []
        self.particles = ParticleSystem()
        self.shop = Shop()
        self.achievements = AchievementTracker()
        self.kills = 0
        self.waves_cleared = 0
        self.lives = 3
        self.shield = 0            # shield hits remaining this wave
        self._shield_timer = 0.0   # invuln grace after a shield absorbs a hit
        self.game_over = False
        self.score = 0
        self.phase = "playing"     # "playing" | "shop"
        self._last_shot = 0
        self._last_enemy_shot = 0

    def reset(self) -> None:
        super().reset()
        self._setup()

    @property
    def player_rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.player_x - self.PLAYER_W // 2),
                           int(self.player_y - self.PLAYER_H // 2),
                           self.PLAYER_W, self.PLAYER_H)

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
                elif self.phase == "shop":
                    self._handle_shop_key(event.key)
        return True

    def _handle_shop_key(self, key: int) -> None:
        """1/2/3 buy an upgrade; SPACE/ENTER starts the next wave."""
        mapping = {pygame.K_1: "rapid", pygame.K_2: "multi", pygame.K_3: "shield"}
        if key in mapping:
            if self.shop.buy(mapping[key]):
                self.audio.play("buy")
                if self.shop.purchases >= 3:
                    self._unlock("shopper")
        elif key in (pygame.K_SPACE, pygame.K_RETURN):
            self._start_next_wave()

    def _start_next_wave(self) -> None:
        self.wave_mgr.start_next_wave()
        self.shield = self.shop.max_shield
        self.phase = "playing"
        if self.achievements.is_unlocked("wave_5") is False and self.wave_mgr.wave >= 5:
            self._unlock("wave_5")

    # ------------------------------------------------------------------
    # Shooting / spawning
    # ------------------------------------------------------------------
    def _spawn_bullet(self, x: float, y: float, vy: float, from_player: bool) -> None:
        """Acquire a pooled bullet, falling back to a fresh one if exhausted."""
        bullet = self._bullet_pool.acquire()
        if bullet is None:
            bullet = Bullet()
        bullet.spawn(x, y, vy, from_player)
        self.bullets.append(bullet)

    def _shoot(self) -> None:
        # Rate-limit player fire using a millisecond cooldown so holding SPACE
        # doesn't unleash a continuous stream of bullets.
        now = pygame.time.get_ticks()
        if now - self._last_shot < self.shop.fire_cooldown_ms:
            return
        self._last_shot = now
        # Multi-shot fans the bullets out around straight-up.
        shots = self.shop.shot_count
        for i in range(shots):
            offset = (i - (shots - 1) / 2) * 10  # -10, 0, +10 for 3 shots
            self._spawn_bullet(self.player_x + offset, self.player_y - self.PLAYER_H // 2,
                               config.PLAYER_BULLET_SPEED, from_player=True)
        self.audio.play("shoot")

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        self.particles.update(dt)
        if self._shield_timer > 0:
            self._shield_timer -= dt
        if self.phase == "shop":
            return  # freeze the field while the player shops
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player_x -= config.PLAYER_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player_x += config.PLAYER_SPEED
        self.player_x = max(self.PLAYER_W // 2,
                            min(config.SCREEN_WIDTH - self.PLAYER_W // 2, self.player_x))
        if keys[pygame.K_SPACE]:
            self._shoot()

        self.wave_mgr.update(self.player_x)

        # Enemy fire: the interval shrinks as waves rise (harder = faster fire)
        # but is floored at 400ms so it never becomes unfair.
        now = pygame.time.get_ticks()
        interval = max(400, 1200 - self.wave_mgr.wave * 100)
        if now - self._last_enemy_shot >= interval:
            shooter = self.wave_mgr.random_shooter()
            if shooter is not None:
                # Divers fire from wherever they've dived to, so the shots
                # track the player instead of the home row.
                self._spawn_bullet(shooter.x, shooter.y + shooter.h // 2,
                                   config.ENEMY_BULLET_SPEED, from_player=False)
            self._last_enemy_shot = now

        for bullet in self.bullets:
            bullet.update()
        self._resolve_collisions()
        self._prune_bullets()

        # Wave cleared -> award credits and open the upgrade shop.
        if self.wave_mgr.is_wave_cleared:
            self._on_wave_cleared()
            return
        # Enemies reached the player line
        for enemy in self.wave_mgr.alive_enemies:
            if enemy.rect.bottom >= self.player_rect.top:
                self._game_over()
                return

    def _prune_bullets(self) -> None:
        """Drop dead bullets from the live list, recycling them to the pool."""
        dead = [b for b in self.bullets if not b.alive]
        if dead:
            self._bullet_pool.release_all(dead)
            self.bullets = [b for b in self.bullets if b.alive]

    def _resolve_collisions(self) -> None:
        p_rect = self.player_rect
        for bullet in self.bullets:
            if not bullet.alive:
                continue
            if bullet.from_player:
                for enemy in self.wave_mgr.alive_enemies:
                    if bullet.rect.colliderect(enemy.rect):
                        bullet.alive = False
                        enemy.hp -= 1
                        if enemy.hp <= 0:
                            self._kill_enemy(enemy)
                        else:
                            self.score += 2
                            self.audio.play("boss_hit" if enemy.w > 100 else "hit")
                        break
            elif bullet.rect.colliderect(p_rect):
                bullet.alive = False
                self._hit_player()

    def _kill_enemy(self, enemy: EnemyShip) -> None:
        is_boss = enemy.w > 100
        self.score += (50 if is_boss else 10) * self.wave_mgr.wave
        self.particles.emit_explosion(enemy.x, enemy.y, config.ENEMY_SHIP,
                                      count=40 if is_boss else 22,
                                      speed=200 if is_boss else 120)
        self.audio.play("explode")
        self.wave_mgr.kill(enemy)
        self.kills += 1
        if self.kills == 1:
            self._unlock("first_blood")
        if self.kills >= 25:
            self._unlock("sharpshooter")
        if is_boss:
            self._unlock("boss_slayer")

    def _on_wave_cleared(self) -> None:
        """Move to the shop phase, or end the run if it was the final wave."""
        self.waves_cleared += 1
        self.shop.grant_wave_clear(self.wave_mgr.wave)
        if self.wave_mgr.wave >= 5:
            self._unlock("wave_5")
        if self.waves_cleared >= 5 and self.lives == 3:
            self._unlock("survivor")
        self.shop.credits = max(self.shop.credits, 0)
        self.phase = "shop"
        self.audio.play("wave_clear")

    def _hit_player(self) -> None:
        if self._shield_timer > 0:
            return  # still in the post-shield invulnerability window
        if self.shield > 0:
            self.shield -= 1
            self._shield_timer = config.SHIELD_INVULN_SECONDS
            self.particles.emit_explosion(self.player_x, self.player_y, config.CYAN,
                                          count=14, speed=90)
            self.audio.play("hit")
            return
        self.lives -= 1
        self.audio.play("player_hit")
        if self.lives <= 0:
            self._game_over()
        else:
            self.player_x = config.SCREEN_WIDTH / 2

    def _unlock(self, key: str) -> None:
        if self.achievements.unlock(key):
            self.audio.play("achievement")

    def _game_over(self) -> None:
        self.game_over = True
        self.particles.emit_explosion(self.player_x, self.player_y, config.PLAYER_SHIP,
                                      count=30, speed=150)
        if self.highscores.is_top_n(self.score_key, self.score):
            self.submit_score()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.SPACE_BG)
        # Sparse starfield backdrop (deterministic so it doesn't shimmer).
        rng = random.Random(0)
        for _ in range(80):
            x = rng.randrange(0, config.SCREEN_WIDTH)
            y = rng.randrange(0, config.SCREEN_HEIGHT)
            surface.set_at((x, y), config.LIGHT_GREY)

        # Player ship (triangle)
        p = self.player_rect
        pygame.draw.polygon(surface, config.PLAYER_SHIP,
                            [(p.centerx, p.top), (p.left, p.bottom), (p.right, p.bottom)])
        if self.shield > 0 and self._shield_timer > 0:
            pygame.draw.circle(surface, config.CYAN, p.center, 30, 2)

        # Enemies - colour signals their movement behaviour to the player.
        for enemy in self.wave_mgr.alive_enemies:
            if enemy.w > 100:
                color = config.ORANGE  # boss
            else:
                color = config.ENEMY_SHIPS.get(enemy.kind.value, config.ENEMY_SHIP)
            pygame.draw.rect(surface, color, enemy.rect, border_radius=6)
            pygame.draw.rect(surface, config.WHITE, enemy.rect.inflate(-14, -12), border_radius=4)

        # Bullets
        for bullet in self.bullets:
            color = config.BULLET_COLOR if bullet.from_player else config.ENEMY_BULLET_COLOR
            pygame.draw.circle(surface, color, (int(bullet.x), int(bullet.y)), bullet.radius)

        self._draw_particles(surface)
        self._draw_hud(surface)
        if self.phase == "shop":
            self._draw_shop(surface)
        if self.game_over:
            self.draw_game_over(surface)

    def _draw_particles(self, surface: pygame.Surface) -> None:
        for particle in self.particles.particles:
            # Fade + shrink each spark over its lifetime for a soft burst.
            radius = max(1, int(3 * (1.0 - particle.t)))
            pygame.draw.circle(surface, particle.color,
                               (int(particle.x), int(particle.y)), radius)

    def _draw_hud(self, surface: pygame.Surface) -> None:
        items = [
            f"Score: {self.score}",
            f"Lives: {self.lives}",
            f"Wave: {self.wave_mgr.wave}",
            f"Credits: {self.shop.credits}",
            f"Shield: {self.shield}",
            f"Best: {self.best_score}",
        ]
        self.draw_hud(surface, *items)

    def _draw_shop(self, surface: pygame.Surface) -> None:
        """Modal upgrade shop shown between waves."""
        from utils import draw_text  # local import keeps the module top clean

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((*config.BLACK, 190))
        surface.blit(overlay, (0, 0))
        cx = config.SCREEN_WIDTH // 2
        draw_text(surface, "UPGRADE SHOP", config.FONT_SIZE_LARGE, config.ACCENT,
                  center=(cx, 130))
        draw_text(surface, f"Credits: {self.shop.credits}", config.FONT_SIZE_MEDIUM,
                  config.WHITE, center=(cx, 180))
        options = [
            ("1", "Rapid Fire", f"Level {self.shop.rapid_level}/{config.UPGRADE_RAPID_MAX}",
             self.shop.cost("rapid")),
            ("2", "Multi-Shot", f"Level {self.shop.multi_level}/{config.UPGRADE_MULTI_MAX}",
             self.shop.cost("multi")),
            ("3", "Shield", f"Level {self.shop.shield_level}/{config.UPGRADE_SHIELD_MAX}",
             self.shop.cost("shield")),
        ]
        y = 250
        for key, title, level, cost in options:
            price = "MAXED" if cost < 0 else f"{cost} cr"
            draw_text(surface, f"[{key}] {title}  {level}  ({price})",
                      config.FONT_SIZE_MEDIUM, config.WHITE, center=(cx, y))
            y += 50
        draw_text(surface, "SPACE to launch next wave", config.FONT_SIZE_SMALL,
                  config.LIGHT_GREY, center=(cx, y + 30))
