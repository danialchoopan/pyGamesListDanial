"""Pygame main menu for the Game Hub.

Draws a navigable list of games, shows each game's description and best
score, and hands control to the selected game's ``run()`` loop.
"""

from __future__ import annotations

from collections.abc import Sequence

import pygame

import config
from base_game import BaseGame
from utils import Settings, draw_text


class MainMenu:
    """Arrow-key / mouse navigable menu listing every registered game."""

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
        self._item_rects: list[pygame.Rect] = []

    # ------------------------------------------------------------------
    def _draw(self) -> None:
        surface = self.screen
        surface.fill(config.BACKGROUND)

        # Title
        draw_text(surface, config.SCREEN_TITLE, config.FONT_SIZE_TITLE,
                  config.ACCENT, center=(config.SCREEN_WIDTH // 2, 100))
        draw_text(surface, "Choose your game", config.FONT_SIZE_MEDIUM,
                  config.LIGHT_GREY, center=(config.SCREEN_WIDTH // 2, 160))

        # Menu items
        self._item_rects = []
        y = config.MENU_START_Y
        for i, game_cls in enumerate(self.game_classes):
            rect = pygame.Rect(0, y - 8, config.SCREEN_WIDTH, config.MENU_ITEM_SPACING - 10)
            self._item_rects.append(rect)
            is_selected = i == self.selected
            if is_selected:
                pygame.draw.rect(surface, config.HOVER, rect, border_radius=10)
                pygame.draw.rect(surface, config.ACCENT, rect, 2, border_radius=10)
            color = config.ACCENT if is_selected else config.WHITE
            marker = "> " if is_selected else "  "
            draw_text(surface, f"{marker}{i + 1}. {game_cls.name}", config.FONT_SIZE_MEDIUM,
                      color, topleft=(config.SCREEN_WIDTH // 2 - 220, y))
            if is_selected:
                draw_text(surface, game_cls.description, config.FONT_SIZE_SMALL,
                          config.LIGHT_GREY, topleft=(config.SCREEN_WIDTH // 2 - 220, y + 34))
            y += config.MENU_ITEM_SPACING

        # Selected game best score
        selected_cls = self.game_classes[self.selected]
        best = self.highscores.best_score(selected_cls.score_key)  # type: ignore[attr-defined]
        draw_text(surface, f"Best score: {best:,}", config.FONT_SIZE_SMALL,
                  config.YELLOW, center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 90))
        draw_text(surface,
                  "Up/Down or mouse to select  |  Enter/Click to play  |  Esc to quit",
                  config.FONT_SIZE_SMALL, config.GREY,
                  center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 50))

    # ------------------------------------------------------------------
    def _launch_selected(self) -> None:
        game_cls = self.game_classes[self.selected]
        game = game_cls(
            screen=self.screen,
            clock=self.clock,
            settings=self.settings,  # type: ignore[arg-type]
            highscores=self.highscores,  # type: ignore[arg-type]
        )
        game.run()

    def run(self) -> None:
        """Run the menu loop until the user quits the application."""
        running = True
        while running:
            self.clock.tick(config.FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self.selected = (self.selected - 1) % len(self.game_classes)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected = (self.selected + 1) % len(self.game_classes)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._launch_selected()
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        index = event.key - pygame.K_1
                        if index < len(self.game_classes):
                            self.selected = index
                            self._launch_selected()
                elif event.type == pygame.MOUSEMOTION:
                    for i, rect in enumerate(self._item_rects):
                        if rect.collidepoint(event.pos):
                            self.selected = i
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for i, rect in enumerate(self._item_rects):
                        if rect.collidepoint(event.pos):
                            self.selected = i
                            self._launch_selected()

            self._draw()
            pygame.display.flip()
