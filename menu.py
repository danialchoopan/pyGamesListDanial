"""Pygame-gui main menu for the Game Hub.

A themed, widget-driven front end built on ``pygame_gui``. It shows a game
list, a details pane (description + best score for the highlighted game), and
a live settings panel (music/SFX volume sliders + an FPS toggle) that writes
straight through to the shared :class:`~utils.Settings` object so changes
survive the session.

The public surface is unchanged from the original hand-drawn menu::

    MainMenu(screen, clock, game_classes, settings, highscores).run()

so ``main.py`` and ``run.py`` boot it exactly as before. Keyboard navigation
(Up/Down, Enter, 1-9, Esc) is kept alongside the mouse-driven widgets, and
both stay in sync through :meth:`MainMenu._select`.
"""

from __future__ import annotations

from collections.abc import Sequence

import pygame
import pygame_gui
from pygame_gui.elements import (
    UICheckBox,
    UIHorizontalSlider,
    UILabel,
    UISelectionList,
    UITextBox,
)

import config
from assets import AudioService, get_assets
from base_game import BaseGame
from ui import make_manager
from utils import Settings, draw_text


class MainMenu:
    """Widget-based menu listing every registered game."""

    # Layout constants (kept as class attrs so a future theme can retune them
    # without hunting through the drawing code).
    _LEFT = pygame.Rect(40, 150, 440, 430)       # game list panel
    _RIGHT = pygame.Rect(500, 150, 484, 250)     # details panel
    _SETTINGS = pygame.Rect(500, 420, 484, 160)  # settings panel
    _PAD = 20                                    # inner padding for widgets

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        game_classes: Sequence[type[BaseGame]],
        settings: Settings,
        highscores: object,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.game_classes = list(game_classes)
        self.settings = settings
        self.highscores = highscores  # HighScoreStore (typed loosely to avoid cycle)
        self.selected = 0

        # Audio feedback for hover/click plus live volume application.
        self.assets = get_assets()
        self.audio = AudioService(self.assets, settings)

        # One themed UIManager drives every widget below.
        self.manager = make_manager(screen.get_size())
        self._build_widgets()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        """Create the list, details pane, settings controls and buttons."""
        w, _h = self.screen.get_size()

        # -- game list ---------------------------------------------------
        self._game_list = UISelectionList(
            relative_rect=self._inner(self._LEFT),
            item_list=self._list_items(),
            manager=self.manager,
            allow_double_clicks=True,
        )

        # -- details pane ------------------------------------------------
        self._name_label = UILabel(
            relative_rect=pygame.Rect(self._RIGHT.x + self._PAD, self._RIGHT.y + 14,
                                      self._RIGHT.w - 2 * self._PAD, 34),
            text="",
            manager=self.manager,
        )
        self._desc_box = UITextBox(
            relative_rect=pygame.Rect(self._RIGHT.x + self._PAD, self._RIGHT.y + 54,
                                      self._RIGHT.w - 2 * self._PAD, 120),
            html_text="",
            manager=self.manager,
        )
        self._score_label = UILabel(
            relative_rect=pygame.Rect(self._RIGHT.x + self._PAD, self._RIGHT.y + 186,
                                      self._RIGHT.w - 2 * self._PAD, 30),
            text="",
            manager=self.manager,
        )

        # -- settings: two volume sliders + an FPS checkbox ---------------
        sx = self._SETTINGS.x + self._PAD
        sw = self._SETTINGS.w - 2 * self._PAD
        self._music_label = UILabel(
            relative_rect=pygame.Rect(sx, self._SETTINGS.y + 14, sw, 24),
            text="Music volume",
            manager=self.manager,
        )
        self._music_slider = UIHorizontalSlider(
            relative_rect=pygame.Rect(sx, self._SETTINGS.y + 40, sw - 70, 22),
            value_range=(config.MIN_VOLUME, config.MAX_VOLUME),
            start_value=self.settings.music_volume,
            manager=self.manager,
        )
        self._music_value = UILabel(
            relative_rect=pygame.Rect(sx + sw - 64, self._SETTINGS.y + 38, 64, 24),
            text=self._pct(self.settings.music_volume),
            manager=self.manager,
        )
        self._sfx_label = UILabel(
            relative_rect=pygame.Rect(sx, self._SETTINGS.y + 70, sw, 24),
            text="Sound effects volume",
            manager=self.manager,
        )
        self._sfx_slider = UIHorizontalSlider(
            relative_rect=pygame.Rect(sx, self._SETTINGS.y + 96, sw - 70, 22),
            value_range=(config.MIN_VOLUME, config.MAX_VOLUME),
            start_value=self.settings.sfx_volume,
            manager=self.manager,
        )
        self._sfx_value = UILabel(
            relative_rect=pygame.Rect(sx + sw - 64, self._SETTINGS.y + 94, 64, 24),
            text=self._pct(self.settings.sfx_volume),
            manager=self.manager,
        )
        self._fps_check = UICheckBox(
            relative_rect=pygame.Rect(sx, self._SETTINGS.y + 124, sw, 28),
            text="Show FPS counter in games",
            manager=self.manager,
            initial_state=bool(self.settings.show_fps),
        )

        # -- action buttons ----------------------------------------------
        btn_y, btn_h, btn_w = 610, 56, 240
        self._play_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(w // 2 - btn_w - 12, btn_y, btn_w, btn_h),
            text="Play selected game",
            manager=self.manager,
        )
        self._quit_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(w // 2 + 12, btn_y, btn_w, btn_h),
            text="Quit",
            manager=self.manager,
        )

        # Populate the details pane for the initially selected game.
        self._sync_details()

    # ------------------------------------------------------------------
    # Layout / formatting helpers
    # ------------------------------------------------------------------
    def _inner(self, rect: pygame.Rect) -> pygame.Rect:
        """Shrink *rect* by the panel padding so widgets don't touch the frame."""
        return pygame.Rect(
            rect.x + self._PAD, rect.y + self._PAD,
            rect.w - 2 * self._PAD, rect.h - 2 * self._PAD,
        )

    @staticmethod
    def _pct(value: float) -> str:
        """Render a 0..1 volume as a whole-number percentage."""
        return f"{round(value * 100):3d}%"

    def _list_items(self) -> list[str | tuple[str, str]]:
        """Build the display labels, marking the selected row."""
        return [
            ("▶  " if i == self.selected else "    ") + f"{i + 1}. {cls.name}"
            for i, cls in enumerate(self.game_classes)
        ]

    def _sync_details(self) -> None:
        """Refresh the name, description and best-score widgets."""
        cls = self.game_classes[self.selected]
        self._name_label.set_text(cls.name)
        # UITextBox takes HTML; descriptions are plain text authored in the
        # game modules, so wrap them in a single grey font tag.
        self._desc_box.set_text(f"<font color=#d0d0e0>{cls.description or 'No description.'}</font>")
        best = self.highscores.best_score(cls.score_key)  # type: ignore[attr-defined]
        self._score_label.set_text(f"Best score: {best:,}")

    def _select(self, index: int) -> None:
        """Move the selection to *index* (wrapping) and refresh the UI."""
        n = len(self.game_classes)
        self.selected = index % n
        self._game_list.set_item_list(self._list_items())
        self._sync_details()
        self.audio.play("select")

    # ------------------------------------------------------------------
    # Launching
    # ------------------------------------------------------------------
    def _launch_selected(self) -> None:
        # Instantiate the chosen game with the shared screen/clock/settings and
        # hand control to its run(). That call blocks this thread until the
        # player presses ESC in-game; once it returns we resume the menu loop.
        cls = self.game_classes[self.selected]
        game = cls(
            screen=self.screen,
            clock=self.clock,
            settings=self.settings,  # type: ignore[arg-type]
            highscores=self.highscores,  # type: ignore[arg-type]
        )
        self.audio.play("confirm")
        game.run()
        # The game may have swapped music; make sure the menu is quiet again
        # and any volume edits made in-game are reflected here.
        self.audio.stop_music()
        self.audio.update_settings(self.settings)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def _handle_ui_event(self, event: pygame.event.Event) -> bool:
        """Route a pygame-gui event; return False to quit the menu."""
        if event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            for i, cls in enumerate(self.game_classes):
                if cls.name in event.text:
                    if i != self.selected:
                        self.selected = i
                        self._sync_details()
                        self.audio.play("select")
                    break

        elif event.type == pygame_gui.UI_SELECTION_LIST_DOUBLE_CLICKED_SELECTION:
            self._launch_selected()

        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self._play_btn:
                self._launch_selected()
            elif event.ui_element == self._quit_btn:
                return False

        elif event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
            if event.ui_element == self._music_slider:
                self.settings.music_volume = float(event.value)
                self._music_value.set_text(self._pct(self.settings.music_volume))
            elif event.ui_element == self._sfx_slider:
                self.settings.sfx_volume = float(event.value)
                self._sfx_value.set_text(self._pct(self.settings.sfx_volume))
            # Push the new volume to the mixer immediately for live feedback.
            self.audio.update_settings(self.settings)

        elif event.type == pygame_gui.UI_CHECK_BOX_CHECKED:
            if event.ui_element == self._fps_check:
                self.settings.show_fps = True

        elif event.type == pygame_gui.UI_CHECK_BOX_UNCHECKED:
            if event.ui_element == self._fps_check:
                self.settings.show_fps = False

        return True

    def _handle_key(self, key: int) -> bool:
        """Handle a raw KEYDOWN; return False to quit the menu."""
        if key == pygame.K_ESCAPE:
            return False
        if key in (pygame.K_UP, pygame.K_w):
            self._select(self.selected - 1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._select(self.selected + 1)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._launch_selected()
        elif pygame.K_1 <= key <= pygame.K_9:
            index = key - pygame.K_1
            if index < len(self.game_classes):
                self._select(index)
                self._launch_selected()
        return True

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _draw_chrome(self) -> None:
        """Draw the backdrop, title and panel frames under the widgets."""
        surface = self.screen
        surface.fill(config.BACKGROUND)

        # Title block.
        draw_text(surface, config.SCREEN_TITLE, config.FONT_SIZE_TITLE,
                  config.ACCENT, center=(config.SCREEN_WIDTH // 2, 70))
        draw_text(surface, "Choose your game", config.FONT_SIZE_MEDIUM,
                  config.LIGHT_GREY, center=(config.SCREEN_WIDTH // 2, 122))

        # Panel frames with section headings.
        for rect, heading in (
            (self._LEFT, "GAMES"),
            (self._RIGHT, "DETAILS"),
            (self._SETTINGS, "SETTINGS"),
        ):
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=12)
            pygame.draw.rect(surface, config.HOVER, rect, 2, border_radius=12)
            draw_text(surface, heading, config.FONT_SIZE_SMALL, config.ACCENT,
                      topleft=(rect.x + self._PAD, rect.y - 12))

        # Footer hint.
        draw_text(
            surface,
            "Up/Down to select  |  Enter to play  |  Esc to quit",
            config.FONT_SIZE_SMALL, config.GREY,
            center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 26),
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Run the menu loop until the user quits the application."""
        running = True
        while running:
            # Cap the frame rate; dt drives the widget animations.
            dt = self.clock.tick(config.FPS) / 1000.0

            for event in pygame.event.get():
                # Every event goes to the widget layer first (hover, clicks,
                # slider drags, checkbox toggles)...
                self.manager.process_events(event)

                # ...then we interpret it for menu behaviour.
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if not self._handle_key(event.key):
                        running = False
                elif not self._handle_ui_event(event):
                    running = False

            self.manager.update(dt)

            self._draw_chrome()
            self.manager.draw_ui(self.screen)
            pygame.display.flip()
