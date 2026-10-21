"""Base game class that every game in the hub inherits from.

Each game implements:
    handle_events(events)  - react to pygame events, return False to quit to menu
    update(dt)             - advance game state by *dt* seconds
    draw(surface)          - render the current state
    reset()                - return to the initial state (new round)
    submit_score()         - record the final score when applicable

The shared ``run()`` method provides a ready-made game loop so
individual games only implement their own logic. It also provides three
cross-cutting features every game gets for free:

* **Pause/resume** - the P key freezes ``update()`` while still drawing the
  frame plus a pause overlay (see :meth:`BaseGame.toggle_pause`).
* **Audio** - ``self.audio`` plays SFX and background music honouring the
  user's volume settings, and stays silent when no audio device exists.
* **Score submission** - a small helper around the shared SQLite store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import pygame

import config
from assets import AudioService, get_assets
from ui import DialogAction, GameUI
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
    #: Optional background-music track (see :mod:`assets`); None = no music.
    music_track: str | None = None

    #: Dialog UI (pause / game-over with buttons), built in ``__init__``.
    #: Declared at class level so a subclass that skips ``__init__`` (the
    #: headless unit-test stub) still resolves to ``None`` and falls back to
    #: the plain-text overlays instead of raising AttributeError.
    _ui: GameUI | None = None

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
        self.paused: bool = False
        # Shared services: cached asset loads + volume-aware audio playback.
        self.assets = get_assets()
        self.audio = AudioService(self.assets, settings)
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
        self.paused = False
        self.audio.update_settings(self.settings)
        if self.music_track:
            self.audio.play_music(self.music_track)

    # ------------------------------------------------------------------
    # Pause / resume (shared by every game)
    # ------------------------------------------------------------------
    def toggle_pause(self) -> bool:
        """Toggle the paused state; returns the new value.

        Background music is paused/resumed in step with the game so a break
        in play is also a break in the soundtrack.
        """
        self.paused = not self.paused
        if self.paused:
            self.audio.pause_music()
        else:
            self.audio.resume_music()
        return self.paused

    def draw_pause_overlay(self, surface: pygame.Surface) -> None:
        """Draw the pause banner over the frozen frame.

        Uses the pygame-gui pause dialog (with working Resume / Restart /
        Menu buttons) when a display is available, and falls back to a
        plain-text banner for headless unit tests.
        """
        ui = self._ensure_ui()
        if ui is not None:
            ui.show_pause()
            ui.draw(surface)
            return

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((*config.BLACK, 150))
        surface.blit(overlay, (0, 0))
        center = (surface.get_width() // 2, surface.get_height() // 2)
        draw_text(surface, "PAUSED", config.FONT_SIZE_LARGE, config.YELLOW, center=center)
        draw_text(
            surface,
            "P to resume  |  ESC for menu",
            config.FONT_SIZE_SMALL,
            config.LIGHT_GREY,
            center=(center[0], center[1] + 50),
        )

    # ------------------------------------------------------------------
    # Shared loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Run the game loop until the player quits back to the menu.

        This is the canonical Pygame frame cycle that every game reuses:
        poll events -> update state -> draw -> flip the back buffer.
        Subclasses only fill in ``handle_events`` / ``update`` / ``draw``.

        The loop itself owns two cross-cutting jobs: the P-key pause (which
        skips ``update()`` entirely so *nothing* - physics, timers, spawners -
        advances while the player is away) and stopping the music on exit.
        """
        self._running = True
        self.start()
        try:
            while self._running:
                # clock.tick(fps) caps the frame rate AND returns the elapsed
                # milliseconds since the last frame; /1000.0 converts it to the
                # seconds we hand to update() so movement is frame-rate independent.
                dt = self.clock.tick(self.fps) / 1000.0
                events = pygame.event.get()

                # Give the dialog layer first refusal on every event so its
                # buttons (Resume / Restart / Retry / Menu) work, then apply
                # whatever action a click requested.
                ui = self._ensure_ui()
                if ui is not None:
                    ui.feed(events)
                    ui.update(dt)
                    action = ui.pop_action()
                    while action is not None:
                        if not self._apply_dialog_action(action):
                            return
                        action = ui.pop_action()

                for event in events:
                    # A window-close request is handled centrally here so no
                    # game has to remember to deal with it.
                    if event.type == pygame.QUIT:
                        self._running = False
                        return
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                        self.toggle_pause()

                if self.paused:
                    # While paused the game's own handlers are skipped so no
                    # input can nudge the simulation; only ESC (back to the
                    # hub menu) stays live.
                    if any(
                        ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE
                        for ev in events
                    ):
                        self._running = False
                        return
                    self.draw(self.screen)
                    self.draw_pause_overlay(self.screen)
                    pygame.display.flip()
                    continue

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
        finally:
            # Runs on every exit path (ESC, window close, or an exception) so
            # music never keeps playing after the player has left the game.
            self.audio.stop_music()

    def quit(self) -> None:
        """Signal the loop to stop and return to the menu."""
        self._running = False

    # ------------------------------------------------------------------
    # Dialog UI (pygame-gui)
    # ------------------------------------------------------------------
    def _ensure_ui(self) -> GameUI | None:
        """Build the pygame-gui dialog layer on first use.

        Returns ``None`` when no video device is initialised (headless unit
        tests), which makes every dialog call fall back to the plain-text
        overlays above so the suite never needs a real window.
        """
        if self._ui is None and pygame.display.get_init():
            try:
                self._ui = GameUI(self.screen.get_size())
            except pygame.error:
                # A display exists but the toolkit couldn't start; degrade
                # gracefully to the text overlays rather than crash the game.
                return None
        return self._ui

    def _apply_dialog_action(self, action: DialogAction) -> bool:
        """React to a pause/game-over button press.

        Returns ``False`` to tell :meth:`run` to leave the game (the "menu"
        button); every other action keeps the loop running.
        """
        if action is DialogAction.MENU:
            self._running = False
            return False
        if action is DialogAction.RESUME:
            if self.paused:
                self.toggle_pause()
            return True
        # RETRY / RESTART -> leave any pause, start a fresh run, and hide the
        # game-over dialog (draw() will re-show it only if still over).
        if self.paused:
            self.toggle_pause()
        self.reset()
        if self._ui is not None:
            self._ui.hide_game_over()
        return True

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
        hint = self.font_small.render("P: pause  ESC: menu", True, config.LIGHT_GREY)
        surface.blit(hint, (surface.get_width() - hint.get_width() - 10, 8))

    def draw_game_over(
        self,
        surface: pygame.Surface,
        message: str = "GAME OVER",
        subtitle: str | None = None,
    ) -> None:
        """Overlay a translucent game-over panel with the final score.

        Uses the pygame-gui game-over dialog (with working Retry / Menu
        buttons) when a display is available, and falls back to a plain-text
        panel for headless unit tests.
        """
        ui = self._ensure_ui()
        if ui is not None:
            ui.show_game_over(message, subtitle, self.score, self.best_score)
            ui.draw(surface)
            return

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
