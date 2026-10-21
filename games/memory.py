"""Memory Card Game (pairs matching).

Flip two cards per turn; match them to clear the board. Score rewards
fast matches and penalises misses. Card logic is in :class:`MemoryBoard`
for display-free unit testing.
"""

from __future__ import annotations

import random
import time
from collections.abc import Sequence

import pygame

import config
from base_game import BaseGame
from utils import draw_text

#: Symbols used for the card faces (emoji-free for font compatibility).
CARD_SYMBOLS: tuple[str, ...] = ("A", "K", "Q", "J", "10", "9", "8", "7")


class MemoryBoard:
    """Pure state for a grid of matched/hidden cards."""

    def __init__(
        self,
        cols: int = config.MEMORY_COLS,
        rows: int = config.MEMORY_ROWS,
        rng: random.Random | None = None,
    ) -> None:
        if (cols * rows) % 2 != 0:
            raise ValueError("Card grid must contain an even number of cells")
        self.cols = cols
        self.rows = rows
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        """Shuffle a fresh pair-matching layout."""
        pairs = (self.cols * self.rows) // 2
        # Build one symbol per pair (cycling through CARD_SYMBOLS if there are
        # more pairs than unique symbols), then *2 so each appears exactly
        # twice, then shuffle so the layout is random.
        deck = [CARD_SYMBOLS[i % len(CARD_SYMBOLS)] for i in range(pairs)] * 2
        self.rng.shuffle(deck)
        self.symbols: list[str] = deck
        self.matched: list[bool] = [False] * len(deck)
        self.flipped: list[int] = []  # indices currently face-up (max 2)
        self.moves: int = 0
        self.matches_found: int = 0
        self._lock_until: float = 0.0  # monotonic deadline for the mismatch reveal

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
            self.flipped.clear()
            return "match"
        # Mismatch: lock input briefly so the player can see both cards before
        # resolve_mismatch() flips them back face-down.
        self._lock_until = time.monotonic() + 0.8
        return "mismatch"

    def resolve_mismatch(self) -> None:
        """Hide a mismatched pair once its display delay has passed."""
        if not self.is_busy and len(self.flipped) == 2:
            self.flipped.clear()

    def score(self, elapsed: float) -> int:
        """Compute the final score from moves and elapsed *seconds*."""
        base = self.matches_found * config.MEMORY_MATCH_SCORE  # points per pair
        # Only "wasted" flips (moves beyond the ideal one-per-pair) are
        # penalised, so perfect play takes no hit.
        penalty = max(0, self.moves - self.matches_found) * config.MEMORY_MISMATCH_PENALTY
        # Reward finishing quickly; the bonus shrinks as time grows and is only
        # granted when the board is fully cleared.
        bonus = max(0, int((60.0 - elapsed) * config.MEMORY_TIME_BONUS_FACTOR))
        return max(0, base - penalty + (bonus if self.is_complete else 0))


class MemoryGame(BaseGame):
    """Playable memory pairs game."""

    name = "Memory Cards"
    description = "Flip cards and find all the matching pairs"
    score_key = "memory"
    fps = config.MEMORY_FPS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.board = MemoryBoard()
        self.elapsed = 0.0
        self.game_over = False
        self._card_rects: list[pygame.Rect] = []

    def reset(self) -> None:
        super().reset()
        self.board.reset()
        self.elapsed = 0.0
        self.game_over = False
        self.score = 0

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

    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
            elif event.type == pygame.MOUSEBUTTONDOWN and not self.game_over:
                pos = event.pos
                for i, rect in enumerate(self._compute_rects()):
                    if rect.collidepoint(pos):
                        result = self.board.flip(i)
                        if result == "match" and self.board.is_complete:
                            self._finish()
                        break
        return True

    def _finish(self) -> None:
        self.game_over = True
        self.score = self.board.score(self.elapsed)
        if self.highscores.is_top_n(self.score_key, self.score):
            self.submit_score()

    def update(self, dt: float) -> None:
        if not self.game_over:
            self.elapsed += dt
            self.board.resolve_mismatch()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND)
        b = self.board
        rects = self._compute_rects()
        for i, rect in enumerate(rects):
            if b.matched[i]:
                color = config.MEMORY_MATCHED
                face = b.symbols[i]
                text_color = config.GREEN
            elif i in b.flipped:
                color = config.MEMORY_CARD_FRONT
                face = b.symbols[i]
                text_color = config.BLUE
            else:
                color = config.MEMORY_CARD_BACK
                face = "?"
                text_color = config.WHITE
            pygame.draw.rect(surface, color, rect, border_radius=10)
            pygame.draw.rect(surface, config.DARK_GREY, rect, 2, border_radius=10)
            draw_text(surface, face, 40, text_color, center=rect.center)

        draw_text(
            surface,
            f"Moves: {b.moves}    Pairs: {b.matches_found}/{b.total_pairs}    "
            f"Time: {self.elapsed:.0f}s",
            config.FONT_SIZE_MEDIUM,
            config.WHITE,
            center=(config.SCREEN_WIDTH // 2, 36),
        )
        self.draw_hud(surface, f"Score: {self.score}", f"Best: {self.best_score}")
        if self.game_over:
            self.draw_game_over(surface, message="YOU WIN!", subtitle=f"{b.moves} moves")
