"""Tic-Tac-Toe with an unbeatable Minimax AI.

The board and AI are pure Python (:class:`Board`, :class:`MinimaxAI`)
so they can be unit-tested without pygame.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

import pygame

import config
from base_game import BaseGame
from utils import draw_text


class Mark(Enum):
    """Player marks."""

    EMPTY = " "
    X = "X"
    O = "O"  # noqa: E741 - 'O' is the conventional noughts-and-crosses mark

    @property
    def opponent(self) -> Mark:
        """Return the opposing mark."""
        return Mark.O if self is Mark.X else Mark.X


#: All winning lines as index triples into the 9-cell board.
WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
    (0, 4, 8), (2, 4, 6),              # diagonals
)


class Board:
    """3x3 tic-tac-toe board represented as 9 cells."""

    def __init__(self, cells: Sequence[Mark] | None = None) -> None:
        if cells is None:
            self.cells: list[Mark] = [Mark.EMPTY] * 9
        else:
            if len(cells) != 9:
                raise ValueError("Board requires exactly 9 cells")
            self.cells = list(cells)

    def available_moves(self) -> list[int]:
        """Indices of empty cells."""
        return [i for i, m in enumerate(self.cells) if m is Mark.EMPTY]

    def make_move(self, index: int, mark: Mark) -> None:
        """Place *mark* at *index*; raises on invalid moves."""
        if self.cells[index] is not Mark.EMPTY:
            raise ValueError(f"Cell {index} is occupied")
        self.cells[index] = mark

    def undo_move(self, index: int) -> None:
        """Clear cell *index*."""
        self.cells[index] = Mark.EMPTY

    def winner(self) -> Mark | None:
        """Return the winning mark, or None."""
        for a, b, c in WIN_LINES:
            if self.cells[a] is not Mark.EMPTY and self.cells[a] is self.cells[b] is self.cells[c]:
                return self.cells[a]
        return None

    def is_full(self) -> bool:
        """True when no empty cells remain."""
        return all(m is not Mark.EMPTY for m in self.cells)

    def is_over(self) -> bool:
        """True when there is a winner or the board is full."""
        return self.winner() is not None or self.is_full()

    def copy(self) -> Board:
        """Return an independent copy."""
        return Board(self.cells)

    def reset(self) -> None:
        """Clear every cell."""
        self.cells = [Mark.EMPTY] * 9


class MinimaxAI:
    """Unbeatable tic-tac-toe AI using the minimax algorithm."""

    def __init__(self, mark: Mark, opponent: Mark | None = None) -> None:
        self.mark = mark
        self.opponent = opponent or mark.opponent

    def choose_move(self, board: Board) -> int:
        """Return the index of the best move for :attr:`mark`."""
        best_score = float("-inf")
        best_move = -1
        for move in board.available_moves():
            board.make_move(move, self.mark)
            score = self._minimax(board, 0, False)
            board.undo_move(move)
            if score > best_score:
                best_score = score
                best_move = move
        return best_move

    def _minimax(self, board: Board, depth: int, maximizing: bool) -> float:
        """Minimax scoring: +1 win, -1 loss, 0 draw (faster wins preferred)."""
        winner = board.winner()
        if winner is self.mark:
            return 10.0 - depth
        if winner is self.opponent:
            return depth - 10.0
        if board.is_full():
            return 0.0

        if maximizing:
            best = -2.0
            for move in board.available_moves():
                board.make_move(move, self.mark)
                best = max(best, self._minimax(board, depth + 1, False))
                board.undo_move(move)
            return best
        best = 2.0
        for move in board.available_moves():
            board.make_move(move, self.opponent)
            best = min(best, self._minimax(board, depth + 1, True))
            board.undo_move(move)
        return best


class TicTacToeGame(BaseGame):
    """Playable Tic-Tac-Toe: human X vs AI O (minimax)."""

    name = "Tic-Tac-Toe"
    description = "Classic Xs and Os vs an unbeatable minimax AI"
    score_key = "tictactoe"
    fps = config.TICTACTOE_FPS

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.board = Board()
        self.ai = MinimaxAI(mark=Mark.O)
        self.human = Mark.X
        self.game_over = False
        self.status = "Your turn (X)"
        self._layout_cells: list[pygame.Rect] = []

    def reset(self) -> None:
        super().reset()
        self.board.reset()
        self.game_over = False
        self.status = "Your turn (X)"
        # Score: win +100, draw +25 — displayed in HUD
        self.score = 0

    def _cell_rects(self) -> list[pygame.Rect]:
        size = config.TTT_CELL_SIZE
        total = size * 3
        ox = (config.SCREEN_WIDTH - total) // 2
        oy = (config.SCREEN_HEIGHT - total) // 2 + 20
        return [
            pygame.Rect(ox + (i % 3) * size, oy + (i // 3) * size, size, size)
            for i in range(9)
        ]

    def _handle_result(self) -> None:
        winner = self.board.winner()
        if winner is self.human:
            self.score = 100
            self.status = "You win!"
            self.game_over = True
            self.submit_score()
        elif winner is not None:
            self.status = "AI wins!"
            self.game_over = True
        elif self.board.is_full():
            self.score = 25
            self.status = "Draw!"
            self.game_over = True
            self.submit_score()

    def handle_events(self, events: Sequence[pygame.event.Event]) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_r:
                    self.reset()
            elif event.type == pygame.MOUSEBUTTONDOWN and not self.game_over:
                if self.board.winner() is not None:
                    return True
                pos = event.pos
                for i, rect in enumerate(self._cell_rects()):
                    if rect.collidepoint(pos) and self.board.cells[i] is Mark.EMPTY:
                        self.board.make_move(i, self.human)
                        self._handle_result()
                        if not self.game_over and self.board.winner() is None and not self.board.is_full():
                            ai_move = self.ai.choose_move(self.board)
                            self.board.make_move(ai_move, self.ai.mark)
                            self._handle_result()
                        break
        return True

    def update(self, dt: float) -> None:
        return

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND)
        draw_text(surface, self.name, config.FONT_SIZE_LARGE, config.ACCENT,
                  center=(config.SCREEN_WIDTH // 2, 70))
        draw_text(surface, self.status, config.FONT_SIZE_MEDIUM, config.WHITE,
                  center=(config.SCREEN_WIDTH // 2, 120))

        rects = self._cell_rects()
        mark_colors = {Mark.X: config.CYAN, Mark.O: config.RED}
        for i, rect in enumerate(rects):
            pygame.draw.rect(surface, config.PANEL_BG, rect)
            pygame.draw.rect(surface, config.LIGHT_GREY, rect, 2)
            mark = self.board.cells[i]
            if mark is not Mark.EMPTY:
                draw_text(surface, mark.value, config.TTT_CELL_SIZE - 40,
                          mark_colors[mark], center=rect.center)

        winner = self.board.winner()
        if winner is not None:
            for a, _b, c in (line for line in WIN_LINES if self.board.cells[line[0]] is winner):
                pygame.draw.line(surface, config.YELLOW, rects[a].center, rects[c].center, 6)

        self.draw_hud(surface, f"Score: {self.score}", f"Best: {self.best_score}")
        if self.game_over:
            draw_text(surface, "Press R to play again  |  ESC for menu",
                      config.FONT_SIZE_SMALL, config.LIGHT_GREY,
                      center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 40))
