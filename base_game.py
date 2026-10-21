"""Base game class that every game in the hub inherits from.

Each game implements:
    handle_events(events)  - react to pygame events, return False to quit to menu
    update(dt)             - advance game state by *dt* seconds
    draw(surface)          - render the current state
    reset()                - return to the initial state (new round)
    submit_score()         - record the final score when applicable

The shared ``run()`` method provides a ready-made game loop so
individual games only implement their own logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import pygame

import config
from utils import HighScoreStore, Settings, draw_text


class BaseGame(ABC):
    """Abstract base class for all hub games."""

    #: Human-readable name shown in the menu.
    name: str = "Base Game"
    #: One-line description shown under the menu selection.
    description: str = ""
    #: Stable key used for high score storage.
    score_key: str = "base"
    #: Default target frame rate for this game.
    fps: int = config.DEFAULT_FPS

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        settings: Settings,
        highscores: HighScoreStore,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.settings = settings
        self.highscores = highscores
        self._running: bool = False
        self.score: int = 0
        # Fonts shared by subclasses
        self.font_small = pygame.font.SysFont(config.FONT_NAME, config.FONT_SIZE_SMALL)
        self.font_medium = pygame.font.SysFont(config.FONT_NAME, config.FONT_SIZE_MEDIUM)
        self.font_large = pygame.font.SysFont(config.FONT_NAME, config.FONT_SIZE_LARGE)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    @abstractmethod
    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        """Process *events*; return False to quit back to the hub menu."""

    @abstractmethod
    def update(self, dt: float) -> None:
        """Advance the simulation by *dt* seconds."""

    @abstractmethod
    def draw(self, surface: pygame.Surface) -> None:
        """Render the current state onto *surface*."""

    def reset(self) -> None:
        """Reset the game to its initial state. Games override as needed."""
        self.score = 0

    def start(self) -> None:
        """Called once when the game is launched from the menu."""
        self.reset()

    # ------------------------------------------------------------------
    # Shared loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Run the game loop until the player quits back to the menu.

        This is the canonical Pygame frame cycle that every game reuses:
        poll events -> update state -> draw -> flip the back buffer.
        Subclasses only fill in ``handle_events`` / ``update`` / ``draw``.
        """
        self._running = True
        self.start()
        while self._running:
            # clock.tick(fps) caps the frame rate AND returns the elapsed
            # milliseconds since the last frame; /1000.0 converts it to the
            # seconds we hand to update() so movement is frame-rate independent.
            dt = self.clock.tick(self.fps) / 1000.0
            events = pygame.event.get()
            # A window-close request is handled centrally here so no game has
            # to remember to deal with it.
            for event in events:
                if event.type == pygame.QUIT:
                    self._running = False
                    return
            # handle_events() returning False is the "back to menu" signal.
            if not self.handle_events(events):
                self._running = False
                return
            self.update(dt)
            self.draw(self.screen)
            if self.settings.show_fps:
                fps = self.clock.get_fps()
                draw_text(
                    self.screen,
                    f"{fps:5.1f} FPS",
                    config.FONT_SIZE_SMALL,
                    config.LIGHT_GREY,
                    topleft=(8, 8),
                )
            pygame.display.flip()  # reveal everything drawn this frame

    def quit(self) -> None:
        """Signal the loop to stop and return to the menu."""
        self._running = False

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def submit_score(self, name: str = "AAA") -> None:
        """Persist ``self.score`` under this game's ``score_key``."""
        self.highscores.add_score(self.score_key, name, self.score)

    @property
    def best_score(self) -> int:
        """Best score previously recorded for this game."""
        return self.highscores.best_score(self.score_key)

    # ------------------------------------------------------------------
    # HUD helpers
    # ------------------------------------------------------------------
    def draw_hud(self, surface: pygame.Surface, *items: str) -> None:
        """Draw a simple top bar with the given text items plus ESC hint."""
        pygame.draw.rect(surface, config.PANEL_BG, (0, 0, surface.get_width(), 34))
        x = 10
        for item in items:
            text_surf = self.font_small.render(item, True, config.WHITE)
            surface.blit(text_surf, (x, 8))
            x += text_surf.get_width() + 24
        hint = self.font_small.render("ESC: menu", True, config.LIGHT_GREY)
        surface.blit(hint, (surface.get_width() - hint.get_width() - 10, 8))

    def draw_game_over(
        self,
        surface: pygame.Surface,
        message: str = "GAME OVER",
        subtitle: str | None = None,
    ) -> None:
        """Overlay a translucent game-over panel with the final score."""
        # SRCALPHA makes a see-through surface; filling with alpha=160 darkens
        # the whole screen so the panel text reads clearly over the gameplay.
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((*config.BLACK, 160))
        surface.blit(overlay, (0, 0))
        center = (surface.get_width() // 2, surface.get_height() // 2)
        draw_text(surface, message, config.FONT_SIZE_LARGE, config.RED, center=center)
        if subtitle:
            draw_text(
                surface,
                subtitle,
                config.FONT_SIZE_MEDIUM,
                config.WHITE,
                center=(center[0], center[1] + 50),
            )
        draw_text(
            surface,
            f"Score: {self.score}   Best: {self.best_score}",
            config.FONT_SIZE_MEDIUM,
            config.YELLOW,
            center=(center[0], center[1] + 90),
        )
        draw_text(
            surface,
            "Press R to retry  |  ESC for menu",
            config.FONT_SIZE_SMALL,
            config.LIGHT_GREY,
            center=(center[0], center[1] + 130),
        )
