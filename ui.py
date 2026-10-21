"""Shared pygame-gui layer: hub theme + dialog UIs used by every game.

This module owns everything that talks to ``pygame_gui`` so the rest of the
codebase never has to. Two things live here:

1. :data:`HUB_THEME` - a dict-based theme giving every widget the hub's look
   (dark navy panels, gold accents) without shipping a separate JSON file.

2. :class:`GameUI` - per-game UI manager that provides the pause and
   game-over dialogs *with working buttons* (Resume / Restart / Retry /
   Menu). It is deliberately built lazily by :class:`base_game.BaseGame` so a
   game only pays for it once a dialog is actually shown.

The class returns actions as strings (``"resume"``, ``"restart"``,
``"retry"``, ``"menu"``) rather than invoking callbacks, which keeps the
event flow in one place (:meth:`base_game.BaseGame.run`) and makes the whole
thing trivially testable.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

import pygame
import pygame_gui
from pygame_gui.elements import UIButton, UILabel, UIWindow

import config


#: Actions a dialog button can request. The run loop translates these into
#: calls on the game (toggle_pause / reset / quit).
class DialogAction(Enum):
    RESUME = "resume"
    RETRY = "retry"
    RESTART = "restart"
    MENU = "menu"


def make_manager(resolution: tuple[int, int]) -> pygame_gui.UIManager:
    """Create a themed UIManager for *resolution*."""
    return pygame_gui.UIManager(resolution, theme_path=dict(HUB_THEME))


#: Hub-wide widget theme. Keys follow pygame-gui's schema; every colour is a
#: hex string so the file stays readable and matches the palette in config.
HUB_THEME: dict[str, object] = {
    "defaults": {
        "colours": {
            "normal_bg": "#1e1e30",
            "normal_text": "#f2f2f7",
            "hovered_bg": "#3d3d64",
            "hovered_text": "#ffffff",
            "selected_bg": "#4a4a78",
            "selected_text": "#ffffff",
            "active_bg": "#ffd700",
            "active_text": "#12121e",
            "disabled_bg": "#16162a",
            "disabled_text": "#6a6a8a",
            "border": "#3a3a5c",
        },
        "font": {
            "name": "noto_sans",
            "size": config.FONT_SIZE_SMALL,
        },
    },
    "button": {
        "colours": {
            "normal_bg": "#2d2d48",
            "normal_text": "#f2f2f7",
            "hovered_bg": "#ffd700",
            "hovered_text": "#12121e",
            "active_bg": "#e6c000",
            "active_text": "#12121e",
            "border": "#3a3a5c",
        },
        "font": {"name": "noto_sans", "size": config.FONT_SIZE_SMALL + 2},
        "misc": {"border_width": "2", "shadow_width": "3", "text_shadow": "0,1"},
    },
    "label": {
        "colours": {
            "normal_bg": "#1e1e30",
            "normal_text": "#f2f2f7",
            "selected_bg": "#2d2d48",
            "selected_text": "#ffd700",
        },
        "font": {"name": "noto_sans", "size": config.FONT_SIZE_SMALL},
        "misc": {"text_horiz_alignment": "left"},
    },
    "window": {
        "colours": {
            "bg": "#1e1e30",
            "border": "#ffd700",
            "title_bar": "#2d2d48",
            "title_bar_text": "#ffd700",
            "close_button": "#c0392b",
            "close_button_hover": "#e74c3c",
        },
        "font": {"name": "noto_sans", "size": config.FONT_SIZE_MEDIUM},
        "misc": {"border_width": "2", "shadow_width": "10", "round_corner": "8"},
    },
    "horizontal_slider": {
        "colours": {
            "bg": "#1e1e30",
            "slider_line": "#3a3a5c",
            "slider_piece": "#ffd700",
            "slider_piece_hover": "#ffe666",
            "border": "#3a3a5c",
        },
        "misc": {"border_width": "0", "shadow_width": "0"},
    },
    "selection_list": {
        "colours": {
            "bg": "#16162a",
            "border": "#3a3a5c",
            "selected_bg": "#4a4a78",
            "selected_text": "#ffd700",
            "normal_bg": "#16162a",
            "normal_text": "#f2f2f7",
            "hover_bg": "#2d2d48",
            "hover_text": "#ffffff",
        },
        "font": {"name": "noto_sans", "size": config.FONT_SIZE_SMALL + 2},
        "misc": {"border_width": "2"},
    },
    "text_box": {
        "colours": {
            "bg": "#1e1e30",
            "normal_bg": "#1e1e30",
            "normal_text": "#d0d0e0",
            "selected_bg": "#4a4a78",
            "selected_text": "#ffffff",
            "border": "#3a3a5c",
        },
        "font": {"name": "noto_sans", "size": config.FONT_SIZE_SMALL},
    },
    "check_box": {
        "colours": {
            "bg": "#1e1e30",
            "normal_bg": "#2d2d48",
            "normal_text": "#f2f2f7",
            "hovered_bg": "#3d3d64",
            "border": "#ffd700",
            "selected_bg": "#ffd700",
        },
        "misc": {"border_width": "2"},
    },
}


class GameUI:
    """Per-game dialog UI (pause + game-over) built on one UIManager.

    Windows are created up front but kept hidden; :meth:`draw` renders only
    what is currently shown. Button presses are collected into an action queue
    that the caller drains with :meth:`pop_action`.
    """

    def __init__(self, resolution: tuple[int, int]) -> None:
        self.manager = make_manager(resolution)
        self._actions: list[DialogAction] = []
        self._w, self._h = resolution

        # -- pause dialog ------------------------------------------------
        self._pause_win = UIWindow(
            rect=pygame.Rect(0, 0, 440, 300),
            window_display_title="Paused",
            manager=self.manager,
            resizable=False,
            draggable=False,
        )
        UILabel(
            relative_rect=pygame.Rect(20, 16, 380, 40),
            text="Game paused",
            manager=self.manager,
            container=self._pause_win,
        )
        self._pause_resume = self._make_button(
            self._pause_win, "Resume", DialogAction.RESUME, y=70
        )
        self._pause_restart = self._make_button(
            self._pause_win, "Restart", DialogAction.RESTART, y=124
        )
        self._pause_menu = self._make_button(
            self._pause_win, "Quit to menu", DialogAction.MENU, y=178
        )
        UILabel(
            relative_rect=pygame.Rect(20, 236, 380, 30),
            text="or press P to resume, ESC to leave",
            manager=self.manager,
            container=self._pause_win,
        )
        self._pause_win.hide()

        # -- game-over dialog -------------------------------------------
        self._over_win = UIWindow(
            rect=pygame.Rect(0, 0, 460, 340),
            window_display_title="Game Over",
            manager=self.manager,
            resizable=False,
            draggable=False,
        )
        self._over_title = UILabel(
            relative_rect=pygame.Rect(20, 16, 400, 44),
            text="GAME OVER",
            manager=self.manager,
            container=self._over_win,
        )
        self._over_subtitle = UILabel(
            relative_rect=pygame.Rect(20, 60, 400, 32),
            text="",
            manager=self.manager,
            container=self._over_win,
        )
        self._over_score = UILabel(
            relative_rect=pygame.Rect(20, 100, 400, 34),
            text="",
            manager=self.manager,
            container=self._over_win,
        )
        self._over_retry = self._make_button(
            self._over_win, "Retry (R)", DialogAction.RETRY, y=150
        )
        self._over_menu = self._make_button(
            self._over_win, "Back to menu (ESC)", DialogAction.MENU, y=204
        )
        self._over_win.hide()

        self._centre(self._pause_win)
        self._centre(self._over_win)

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    def _make_button(self, container: UIWindow, text: str, action: DialogAction,
                     y: int) -> UIButton:
        """Create a full-width button in *container* tagged with *action*."""
        button = UIButton(
            relative_rect=pygame.Rect(30, y, container.rect.width - 60, 44),
            text=text,
            manager=self.manager,
            container=container,
        )
        # Stash the action on the element itself so event handling is a
        # simple attribute lookup instead of an id->action mapping.
        button.dialog_action = action  # type: ignore[attr-defined]
        return button

    def _centre(self, window: UIWindow) -> None:
        """Place *window* in the middle of the screen."""
        window.set_relative_position(
            ((self._w - window.rect.width) // 2, (self._h - window.rect.height) // 2)
        )

    # ------------------------------------------------------------------
    # show / hide
    # ------------------------------------------------------------------
    def show_pause(self) -> None:
        """Show the pause dialog (and hide game-over, which it supersedes)."""
        self._over_win.hide()
        self._pause_win.show()

    def hide_pause(self) -> None:
        self._pause_win.hide()

    def show_game_over(self, title: str, subtitle: str | None, score: int,
                       best: int) -> None:
        """Show the game-over dialog with the final numbers filled in."""
        self._pause_win.hide()
        self._over_title.set_text(title)
        self._over_subtitle.set_text(subtitle or "")
        self._over_score.set_text(f"Score: {score:,}     Best: {best:,}")
        self._over_win.show()

    def hide_game_over(self) -> None:
        self._over_win.hide()

    @property
    def any_visible(self) -> bool:
        """True when at least one dialog is on screen."""
        return bool(self._pause_win.visible or self._over_win.visible)

    # ------------------------------------------------------------------
    # event / frame plumbing
    # ------------------------------------------------------------------
    def feed(self, events: Sequence[pygame.event.Event]) -> None:
        """Pass *events* to the manager and collect any button actions."""
        for event in events:
            self.manager.process_events(event)
            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                action = getattr(event.ui_element, "dialog_action", None)
                if isinstance(action, DialogAction):
                    self._actions.append(action)

    def pop_action(self) -> DialogAction | None:
        """Drain the oldest queued button action, if any."""
        return self._actions.pop(0) if self._actions else None

    def update(self, dt: float) -> None:
        """Advance widget animations by *dt* seconds."""
        self.manager.update(dt)

    def draw(self, surface: pygame.Surface, dim: bool = True) -> None:
        """Render the visible dialogs (optionally over a dimmed backdrop)."""
        if dim:
            # A translucent full-screen wash so the dialog reads clearly over
            # whatever gameplay is frozen behind it.
            wash = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            wash.fill((*config.BLACK, 160))
            surface.blit(wash, (0, 0))
        self.manager.draw_ui(surface)
