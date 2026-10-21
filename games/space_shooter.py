"""Space Shooter (Galaga-style).

Player ship at the bottom, waves of enemies overhead, bullets both ways.
Wave logic lives in :class:`WaveManager` for testability.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

import pygame

import config
from base_game import BaseGame


class Bullet:
    """A bullet projectile."""

    def __init__(self, x: float, y: float, vy: float, from_player: bool) -> None:
        self.x = x
        self.y = y
        self.vy = vy
        self.from_player = from_player
        self.alive = True
        self.radius = 4

    @property
    def rect(self) -> pygame.Rect:
        """Bounding rect of the bullet."""
        return pygame.Rect(int(self.x - self.radius), int(self.y - self.radius),
                           self.radius * 2, self.radius * 2)

    def update(self) -> None:
        """Move and cull off-screen bullets."""
        self.y += self.vy
        if self.y < -20 or self.y > config.SCREEN_HEIGHT + 20:
            self.alive = False


class EnemyShip:
    """A single enemy ship."""

    def __init__(self, x: float, y: float, hp: int = 1, speed: float = config.ENEMY_BASE_SPEED) -> None:
        self.x = x
        self.y = y
        self.hp = hp
        self.speed = speed
        self.alive = True
        self.w = 34
        self.h = 26

    @property
    def rect(self) -> pygame.Rect:
        """Bounding rect of the ship."""
        return pygame.Rect(int(self.x - self.w // 2), int(self.y - self.h // 2), self.w, self.h)

    def update(self, direction: int, bounds: tuple[int, int]) -> None:
        """Move horizontally by *direction*, bouncing at *bounds*."""
        self.x += direction * self.speed
        lo, hi = bounds
        self.x = max(lo + self.w // 2, min(hi - self.w // 2, self.x))


class WaveManager:
    """Spawns and tracks enemy waves."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        """Reset to wave 1."""
        self.wave = 1
        self.enemies: list[EnemyShip] = []
        self.direction = 1
        self._spawn_wave()

    def _spawn_wave(self) -> None:
        """Create the fleet for the current wave, scaling difficulty."""
        self.enemies = []
        # Difficulty ramps with the wave number: an extra row every 2 waves
        # (capped at 6), +1 HP every 3 waves, and speed climbs each wave.
        rows = min(config.ENEMY_ROWS + (self.wave - 1) // 2, 6)
        cols = config.ENEMY_COLS
        spacing_x = 90
        spacing_y = 60
        grid_w = cols * spacing_x
        ox = (config.SCREEN_WIDTH - grid_w) // 2 + spacing_x // 2  # centre the grid
        oy = 90  # start below the HUD bar
        hp = 1 + (self.wave - 1) // 3
        speed = config.ENEMY_BASE_SPEED + (self.wave - 1) * 0.4
        for r in range(rows):
            for c in range(cols):
                self.enemies.append(EnemyShip(ox + c * spacing_x, oy + r * spacing_y, hp=hp, speed=speed))

    @property
    def alive_enemies(self) -> list[EnemyShip]:
        """Ships still on screen."""
        return [e for e in self.enemies if e.alive]

    @property
    def is_wave_cleared(self) -> bool:
        """True when every ship in the wave is destroyed."""
        return not self.alive_enemies

    def update(self) -> None:
        """March the fleet side to side; advance to the next wave when clear."""
        if self.is_wave_cleared:
            self.wave += 1
            self._spawn_wave()
            return
        alive = self.alive_enemies
        # Find the fleet's horizontal extent; when it hits a screen edge the
        # whole formation reverses and drops - the classic Galaga march.
        left = min(e.rect.left for e in alive)
        right = max(e.rect.right for e in alive)
        if (left <= 0 and self.direction < 0) or (right >= config.SCREEN_WIDTH and self.direction > 0):
            self.direction *= -1
            for e in alive:
                e.y += 24  # descend one step on each direction change
        for e in alive:
            e.update(self.direction, (0, config.SCREEN_WIDTH))

    def random_shooter(self) -> EnemyShip | None:
        """Pick a random alive enemy to fire a bullet."""
        alive = self.alive_enemies
        return self.rng.choice(alive) if alive else None


class SpaceShooterGame(BaseGame):
    """Playable space shooter."""

    name = "Space Shooter"
    description = "Blast descending alien waves before they reach you"
    score_key = "space_shooter"
    fps = config.SPACE_SHOOTER_FPS

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
        self.bullets: list[Bullet] = []
        self.lives = 3
        self.game_over = False
        self.score = 0
        self._last_shot = 0
        self._last_enemy_shot = 0

    def reset(self) -> None:
        super().reset()
        self._setup()

    @property
    def player_rect(self) -> pygame.Rect:
        """Bounding rect of the player ship."""
        return pygame.Rect(int(self.player_x - self.PLAYER_W // 2),
                           int(self.player_y - self.PLAYER_H // 2),
                           self.PLAYER_W, self.PLAYER_H)

    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
        return True

    def _shoot(self) -> None:
        # Rate-limit player fire using a millisecond cooldown so holding SPACE
        # doesn't unleash a continuous stream of bullets.
        now = pygame.time.get_ticks()
        if now - self._last_shot >= config.BULLET_COOLDOWN_MS:
            self.bullets.append(Bullet(self.player_x, self.player_y - self.PLAYER_H // 2,
                                       config.PLAYER_BULLET_SPEED, from_player=True))
            self._last_shot = now

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player_x -= config.PLAYER_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player_x += config.PLAYER_SPEED
        self.player_x = max(self.PLAYER_W // 2, min(config.SCREEN_WIDTH - self.PLAYER_W // 2, self.player_x))
        if keys[pygame.K_SPACE]:
            self._shoot()

        self.wave_mgr.update()

        # Enemy fire: the interval shrinks as waves rise (harder = faster fire)
        # but is floored at 400ms so it never becomes unfair.
        now = pygame.time.get_ticks()
        if now - self._last_enemy_shot >= max(400, 1200 - self.wave_mgr.wave * 100):
            shooter = self.wave_mgr.random_shooter()
            if shooter is not None:
                self.bullets.append(Bullet(shooter.x, shooter.y + shooter.h // 2,
                                           config.ENEMY_BULLET_SPEED, from_player=False))
            self._last_enemy_shot = now

        # Bullets
        for bullet in self.bullets:
            bullet.update()
        self._resolve_collisions()
        self.bullets = [b for b in self.bullets if b.alive]

        # Enemies reached the player line
        for enemy in self.wave_mgr.alive_enemies:
            if enemy.rect.bottom >= self.player_rect.top:
                self._game_over()
                return

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
                            enemy.alive = False
                            self.score += 10 * self.wave_mgr.wave
                        else:
                            self.score += 2
                        break
            elif bullet.rect.colliderect(p_rect):
                bullet.alive = False
                self._hit_player()

    def _hit_player(self) -> None:
        self.lives -= 1
        if self.lives <= 0:
            self._game_over()
        else:
            self.player_x = config.SCREEN_WIDTH / 2

    def _game_over(self) -> None:
        self.game_over = True
        if self.highscores.is_top_n(self.score_key, self.score):
            self.submit_score()

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.SPACE_BG)
        # Sparse starfield backdrop
        rng = random.Random(0)
        for _ in range(80):
            x = rng.randrange(0, config.SCREEN_WIDTH)
            y = rng.randrange(0, config.SCREEN_HEIGHT)
            surface.set_at((x, y), config.LIGHT_GREY)

        # Player ship (triangle)
        p = self.player_rect
        pygame.draw.polygon(
            surface,
            config.PLAYER_SHIP,
            [(p.centerx, p.top), (p.left, p.bottom), (p.right, p.bottom)],
        )

        # Enemies
        for enemy in self.wave_mgr.alive_enemies:
            pygame.draw.rect(surface, config.ENEMY_SHIP, enemy.rect, border_radius=6)
            pygame.draw.rect(surface, config.WHITE, enemy.rect.inflate(-14, -12), border_radius=4)

        # Bullets
        for bullet in self.bullets:
            color = config.BULLET_COLOR if bullet.from_player else config.ENEMY_BULLET_COLOR
            pygame.draw.circle(surface, color, (int(bullet.x), int(bullet.y)), bullet.radius)

        self.draw_hud(
            surface,
            f"Score: {self.score}",
            f"Lives: {self.lives}",
            f"Wave: {self.wave_mgr.wave}",
            f"Best: {self.best_score}",
        )
        if self.game_over:
            self.draw_game_over(surface)
