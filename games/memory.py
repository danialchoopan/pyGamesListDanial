"""Memory Card Game (pairs matching).

Flip two cards per turn; match them to clear the board. Score rewards fast,
accurate matching and rewards combo streaks. Card logic is in
:class:`MemoryBoard` for display-free unit testing.

Features
- Card-flipping animation
- Timer and move counter
- Three themes (numbers, symbols, animals)
- Combo system for consecutive matches
- Leaderboard via the shared SQLite high-score store
"""

from __future__ import annotations

import random
import time
from collections.abc import Sequence
from dataclasses import dataclass

import pygame

import config
from base_game import BaseGame
from utils import draw_text

#: Fallback symbols used for card faces (kept for back-compatibility).
CARD_SYMBOLS: tuple[str, ...] = ("A", "K", "Q", "J", "10", "9", "8", "7")


@dataclass(frozen=True)
class Theme:
    """A card-face theme: its tokens and the font size used to draw them."""

    key: str
    label: str
    tokens: tuple[str, ...]
    font_size: int


#: Available themes, shown on the in-game picker.
THEMES: tuple[Theme, ...] = (
    Theme("numbers", "Numbers", ("1", "2", "3", "4", "5", "6", "7", "8"), 48),
    Theme("symbols", "Symbols", ("★", "●", "▲", "■", "♥", "◆", "♣", "▶"), 40),
    Theme("animals", "Animals", ("CAT", "DOG", "FOX", "OWL", "BAT", "COW", "HEN", "PIG"), 22),
)


class MemoryBoard:
    """Pure state for a grid of matched/hidden cards."""

    def __init__(
        self,
        cols: int = config.MEMORY_COLS,
        rows: int = config.MEMORY_ROWS,
        tokens: Sequence[str] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if (cols * rows) % 2 != 0:
            raise ValueError("Card grid must contain an even number of cells")
        self.cols = cols
        self.rows = rows
        self.tokens: tuple[str, ...] = tuple(tokens) if tokens else CARD_SYMBOLS
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        """Shuffle a fresh pair-matching layout."""
        pairs = (self.cols * self.rows) // 2
        # Build one token per pair (cycling through the theme's tokens if there
        # are more pairs than unique tokens), then *2 so each appears exactly
        # twice, then shuffle so the layout is random.
        deck = [self.tokens[i % len(self.tokens)] for i in range(pairs)] * 2
        self.rng.shuffle(deck)
        self.symbols: list[str] = deck
        self.matched: list[bool] = [False] * len(deck)
        self.flipped: list[int] = []  # indices currently face-up (max 2)
        self.moves: int = 0
        self.matches_found: int = 0
        self._lock_until: float = 0.0  # monotonic deadline for the mismatch reveal
        # Combo tracking: consecutive matches without a miss.
        self.combo: int = 0
        self.best_combo: int = 0
        self.earned: int = 0  # running total of combo-scaled match points

    @property
    def total_pairs(self) -> int:
        """Number of pairs to find."""
        return (self.cols * self.rows) // 2

    @property
    def is_complete(self) -> bool:
        """True when every pair has been matched."""
        return self.matches_found == self.total_pairs

    @property
    def is_busy(self) -> bool:
        """True while a mismatched pair is briefly shown face-up."""
        return time.monotonic() < self._lock_until

    def combo_multiplier(self) -> float:
        """Score multiplier for the *next* match given the current combo."""
        return 1.0 + config.MEMORY_COMBO_STEP * max(0, self.combo - 1)

    def flip(self, index: int) -> str:
        """Flip card *index*.

        Tiny state machine returning what happened so the caller can react:
        ``"flipped"`` (first card of a pair), ``"match"``, ``"mismatch"``,
        or ``"ignored"`` (busy, already face-up, or already matched).
        """
        if self.is_busy or index in self.flipped or self.matched[index]:
            return "ignored"
        self.flipped.append(index)
        if len(self.flipped) < 2:
            return "flipped"  # wait for the second card of this pair
        # Two cards are now face-up: decide match vs mismatch.
        self.moves += 1
        a, b = self.flipped
        if self.symbols[a] == self.symbols[b]:
            self.matched[a] = self.matched[b] = True
            self.matches_found += 1
            # Combo grows on a match; award points scaled by the streak.
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
            points = round(config.MEMORY_MATCH_SCORE * self.combo_multiplier())
            self.earned += points
            self.flipped.clear()
            return "match"
        # Mismatch: reset the combo and lock input briefly so the player can
        # see both cards before resolve_mismatch() flips them back face-down.
        self.combo = 0
        self._lock_until = time.monotonic() + 0.8
        return "mismatch"

    def resolve_mismatch(self) -> None:
        """Hide a mismatched pair once its display delay has passed."""
        if not self.is_busy and len(self.flipped) == 2:
            self.flipped.clear()

    def score(self, elapsed: float) -> int:
        """Compute the final score from combo points, misses and elapsed time."""
        # ``earned`` already includes the per-match combo multiplier.
        # Only "wasted" flips (moves beyond the ideal one-per-pair) are
        # penalised, so perfect play takes no hit.
        penalty = max(0, self.moves - self.matches_found) * config.MEMORY_MISMATCH_PENALTY
        # Reward finishing quickly; the bonus shrinks as time grows and is only
        # granted when the board is fully cleared.
        bonus = max(0, int((60.0 - elapsed) * config.MEMORY_TIME_BONUS_FACTOR))
        return max(0, self.earned - penalty + (bonus if self.is_complete else 0))


class MemoryGame(BaseGame):
    """Playable memory pairs game with themes, combo scoring and animation."""

    name = "Memory Cards"
    description = "Flip cards, chain combos, and find every pair"
    score_key = "memory"
    fps = config.MEMORY_FPS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.theme: Theme = THEMES[0]
        self.board = MemoryBoard(tokens=self.theme.tokens)
        self.elapsed = 0.0
        self.game_over = False
        self.phase = "select"  # "select" -> "playing" -> "over"
        self.hovered = -1
        # Per-card flip animation progress: 0 = face-down, 1 = face-up.
        self.anim: list[float] = [0.0] * len(self.board.symbols)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Return to the theme picker with a clean slate."""
        super().reset()
        self.board = MemoryBoard(tokens=self.theme.tokens)
        self.phase = "select"
        self.hovered = -1
        self.elapsed = 0.0
        self.game_over = False
        self.score = 0
        self.anim = [0.0] * len(self.board.symbols)

    def _start_round(self, theme: Theme) -> None:
        """Begin a fresh round with the chosen theme."""
        self.theme = theme
        self.board = MemoryBoard(tokens=theme.tokens)
        self.phase = "playing"
        self.hovered = -1
        self.elapsed = 0.0
        self.game_over = False
        self.score = 0
        self.anim = [0.0] * len(self.board.symbols)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _compute_rects(self) -> list[pygame.Rect]:
        b = self.board
        margin = 20
        top = 70
        avail_w = config.SCREEN_WIDTH - margin * 2
        avail_h = config.SCREEN_HEIGHT - top - margin
        card_w = min(140, avail_w // b.cols - margin)
        card_h = min(160, avail_h // b.rows - margin)
        grid_w = b.cols * (card_w + margin) - margin
        grid_h = b.rows * (card_h + margin) - margin
        ox = (config.SCREEN_WIDTH - grid_w) // 2
        oy = top + (avail_h - grid_h) // 2
        return [
            pygame.Rect(ox + (i % b.cols) * (card_w + margin),
                        oy + (i // b.cols) * (card_h + margin),
                        card_w, card_h)
            for i in range(b.cols * b.rows)
        ]

    def _option_rects(self) -> list[pygame.Rect]:
        """One picker card per theme, centred horizontally."""
        card_w, card_h, gap = 240, 150, 40
        total = len(THEMES) * card_w + (len(THEMES) - 1) * gap
        ox = (config.SCREEN_WIDTH - total) // 2
        oy = (config.SCREEN_HEIGHT - card_h) // 2
        return [
            pygame.Rect(ox + i * (card_w + gap), oy, card_w, card_h)
            for i in range(len(THEMES))
        ]

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
                elif self.phase == "select" and pygame.K_1 <= event.key <= pygame.K_3:
                    idx = event.key - pygame.K_1
                    if idx < len(THEMES):
                        self._start_round(THEMES[idx])
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.phase == "select":
                    for i, rect in enumerate(self._option_rects()):
                        if rect.collidepoint(event.pos):
                            self._start_round(THEMES[i])
                            break
                elif self.phase == "playing" and not self.game_over:
                    for i, rect in enumerate(self._compute_rects()):
                        if rect.collidepoint(event.pos):
                            result = self.board.flip(i)
                            if result == "match" and self.board.is_complete:
                                self._finish()
                            break
        return True

    def _finish(self) -> None:
        self.phase = "over"
        self.game_over = True
        self.score = self.board.score(self.elapsed)
        if self.highscores.is_top_n(self.score_key, self.score):
            self.submit_score()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.phase == "select":
            mx, my = pygame.mouse.get_pos()
            self.hovered = -1
            for i, rect in enumerate(self._option_rects()):
                if rect.collidepoint((mx, my)):
                    self.hovered = i
                    break
            return
        if self.game_over:
            return
        self.elapsed += dt
        self.board.resolve_mismatch()
        self._advance_animation(dt)

    def _advance_animation(self, dt: float) -> None:
        """Ease each card's flip progress toward its logical up/down state."""
        step = config.MEMORY_ANIM_SPEED * dt
        for i in range(len(self.anim)):
            target = 1.0 if (self.board.matched[i] or i in self.board.flipped) else 0.0
            if self.anim[i] < target:
                self.anim[i] = min(target, self.anim[i] + step)
            elif self.anim[i] > target:
                self.anim[i] = max(target, self.anim[i] - step)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND)
        draw_text(surface, self.name, config.FONT_SIZE_LARGE, config.ACCENT,
                  center=(config.SCREEN_WIDTH // 2, 42))
        if self.phase == "select":
            self._draw_picker(surface)
        else:
            self._draw_board(surface)

    def _draw_picker(self, surface: pygame.Surface) -> None:
        draw_text(surface, "Choose a theme", config.FONT_SIZE_MEDIUM, config.WHITE,
                  center=(config.SCREEN_WIDTH // 2, 100))
        for i, rect in enumerate(self._option_rects()):
            hover = self.hovered == i
            bg = config.HOVER if hover else config.PANEL_BG
            border = config.ACCENT if hover else config.LIGHT_GREY
            pygame.draw.rect(surface, bg, rect, border_radius=12)
            pygame.draw.rect(surface, border, rect, 3 if hover else 2, border_radius=12)
            theme = THEMES[i]
            draw_text(surface, f"{i + 1}. {theme.label}", config.FONT_SIZE_MEDIUM,
                      config.ACCENT if hover else config.WHITE, center=(rect.centerx, rect.centery - 25))
            # Preview a few tokens from the theme.
            preview = "  ".join(theme.tokens[:4])
            draw_text(surface, preview, theme.font_size // 2 + 4, config.LIGHT_GREY,
                      center=(rect.centerx, rect.centery + 20))
        draw_text(surface, f"Best: {self.best_score}", config.FONT_SIZE_SMALL,
                  config.YELLOW, center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 50))

    def _draw_board(self, surface: pygame.Surface) -> None:
        b = self.board
        rects = self._compute_rects()
        for i, rect in enumerate(rects):
            p = self.anim[i]
            # Fake a horizontal flip: the card squeezes to a sliver at the
            # midpoint (p=0.5) then widens again showing the other face.
            width_factor = max(abs(1.0 - 2.0 * p), 0.08)
            w = max(2, int(rect.width * width_factor))
            draw_rect = pygame.Rect(rect.centerx - w // 2, rect.top, w, rect.height)
            show_face = p > 0.5
            if b.matched[i]:
                color, face, text_color = config.MEMORY_MATCHED, b.symbols[i], config.GREEN
            elif show_face:
                color, face, text_color = config.MEMORY_CARD_FRONT, b.symbols[i], config.BLUE
            else:
                color, face, text_color = config.MEMORY_CARD_BACK, "?", config.WHITE
            pygame.draw.rect(surface, color, draw_rect, border_radius=10)
            pygame.draw.rect(surface, config.DARK_GREY, draw_rect, 2, border_radius=10)
            if w > 24:  # only draw the face once the card is wide enough
                draw_text(surface, face, self.theme.font_size, text_color, center=rect.center)

        # Header: moves, pairs, time and live combo.
        combo_txt = f"    Combo x{b.combo_multiplier():.1f}" if b.combo > 1 else ""
        draw_text(
            surface,
            f"Moves: {b.moves}    Pairs: {b.matches_found}/{b.total_pairs}    "
            f"Time: {self.elapsed:.0f}s{combo_txt}",
            config.FONT_SIZE_MEDIUM,
            config.WHITE,
            center=(config.SCREEN_WIDTH // 2, 78),
        )
        self.draw_hud(surface, f"Score: {self.score}", f"Best: {self.best_score}",
                      f"Theme: {self.theme.label}")
        if self.game_over:
            self.draw_game_over(
                surface,
                message="YOU WIN!",
                subtitle=f"{b.moves} moves  |  best combo x{b.best_combo}",
            )
