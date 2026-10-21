"""Tic-Tac-Toe with three AI difficulties.

The board, AI and move log are pure Python (:class:`Board`,
:class:`TicTacToeAI`, :class:`MoveLog`) so they can be unit-tested without
pygame.

Features
- Minimax AI (Hard) plus Medium (win/block) and Easy (random) difficulties
- Win/draw detection
- Move history tracking
- In-game difficulty picker and hover highlighting
"""

from __future__ import annotations

import random
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


class Difficulty(Enum):
    """AI difficulty levels, ordered easiest to hardest."""

    EASY = "easy"      # random legal moves
    MEDIUM = "medium"  # take a win, block a loss, else centre/corner
    HARD = "hard"      # full minimax - unbeatable


#: All winning lines as index triples into the 9-cell board.
WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
    (0, 4, 8), (2, 4, 6),              # diagonals
)

#: Corner cells, used by the Medium AI's positional fallback.
_CORNERS: tuple[int, int, int, int] = (0, 2, 6, 8)


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
            # The chained `is` checks that all three cells hold the same mark.
            # The first guard rules out three EMPTY cells, which would
            # otherwise "match" on any unfilled line.
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
        # Seed with -inf so that even a move scoring below -2 (i.e. a forced
        # loss) still gets recorded. Starting at a finite number like -2 would
        # skip such moves and leave best_move as the sentinel -1.
        best_score = float("-inf")
        best_move = -1
        # For every legal move: play it, score the resulting position under the
        # assumption both sides play perfectly afterwards, then undo it. Using
        # make/undo avoids deep-copying the board at each branch.
        for move in board.available_moves():
            board.make_move(move, self.mark)
            score = self._minimax(board, 0, False)  # False -> opponent to move
            board.undo_move(move)
            if score > best_score:
                best_score = score
                best_move = move
        return best_move

    def _minimax(self, board: Board, depth: int, maximizing: bool) -> float:
        """Minimax scoring: +1 win, -1 loss, 0 draw (faster wins preferred).

        Scores are adjusted by ``depth`` so the AI prefers to win as quickly as
        possible and to delay losing as long as possible. ``maximizing`` is
        True when it is this AI's turn (pick the highest score) and False for
        the opponent's turn (they pick the lowest).
        """
        winner = board.winner()
        if winner is self.mark:
            return 10.0 - depth  # shallower (quicker) win scores higher
        if winner is self.opponent:
            return depth - 10.0  # deeper (later) loss is less bad
        if board.is_full():
            return 0.0  # draw

        if maximizing:
            # Our turn: choose the move with the best (highest) outcome.
            best = -2.0
            for move in board.available_moves():
                board.make_move(move, self.mark)
                best = max(best, self._minimax(board, depth + 1, False))
                board.undo_move(move)
            return best
        # Opponent's turn: assume they play their best (lowest for us) move.
        best = 2.0
        for move in board.available_moves():
            board.make_move(move, self.opponent)
            best = min(best, self._minimax(board, depth + 1, True))
            board.undo_move(move)
        return best


class TicTacToeAI:
    """Difficulty-aware AI that dispatches to the right strategy.

    - EASY:   pick a random legal move.
    - MEDIUM: take an immediate win, else block the opponent's win, else play
              centre -> corner -> random.
    - HARD:   delegate to the unbeatable :class:`MinimaxAI`.
    """

    def __init__(
        self,
        mark: Mark,
        difficulty: Difficulty = Difficulty.HARD,
        rng: random.Random | None = None,
    ) -> None:
        self.mark = mark
        self.opponent = mark.opponent
        self.difficulty = difficulty
        self.rng = rng or random.Random()
        self._minimax = MinimaxAI(mark=mark)  # reused for HARD

    def choose_move(self, board: Board) -> int:
        """Return the chosen cell index for the configured difficulty."""
        moves = board.available_moves()
        if not moves:
            return -1  # no move possible on a full board
        if self.difficulty is Difficulty.EASY:
            return self.rng.choice(moves)
        if self.difficulty is Difficulty.MEDIUM:
            return self._medium_move(board, moves)
        return self._minimax.choose_move(board)  # HARD

    def _medium_move(self, board: Board, moves: list[int]) -> int:
        """One-ply 'smart' strategy: win, block, then positional play."""
        # 1) Take an immediate win if available.
        for m in moves:
            board.make_move(m, self.mark)
            wins = board.winner() is self.mark
            board.undo_move(m)
            if wins:
                return m
        # 2) Block the opponent's immediate win.
        for m in moves:
            board.make_move(m, self.opponent)
            threatens = board.winner() is self.opponent
            board.undo_move(m)
            if threatens:
                return m
        # 3) Positional fallback: centre, then a corner, then anywhere.
        if board.cells[4] is Mark.EMPTY:
            return 4
        corners = [c for c in _CORNERS if board.cells[c] is Mark.EMPTY]
        if corners:
            return self.rng.choice(corners)
        return self.rng.choice(moves)


class MoveLog:
    """Ordered record of the moves played this round (cell index + mark)."""

    def __init__(self) -> None:
        self._entries: list[tuple[int, Mark]] = []

    def record(self, index: int, mark: Mark) -> None:
        """Append a move."""
        self._entries.append((index, mark))

    def undo(self) -> tuple[int, Mark] | None:
        """Remove and return the last move, or None when empty."""
        return self._entries.pop() if self._entries else None

    def cells(self) -> list[int]:
        """Cell indices in the order they were played."""
        return [i for i, _ in self._entries]

    @property
    def entries(self) -> list[tuple[int, Mark]]:
        """A copy of all recorded moves."""
        return list(self._entries)

    @property
    def last(self) -> tuple[int, Mark] | None:
        """The most recent move, or None."""
        return self._entries[-1] if self._entries else None

    def __len__(self) -> int:
        return len(self._entries)


class TicTacToeGame(BaseGame):
    """Playable Tic-Tac-Toe: human X vs a difficulty-selected AI."""

    name = "Tic-Tac-Toe"
    description = "Xs and Os vs three AI difficulties (Easy to unbeatable)"
    score_key = "tictactoe"
    fps = config.TICTACTOE_FPS

    #: Labels + blurbs shown on the difficulty picker, indexed like Difficulty.
    _OPTIONS: tuple[tuple[str, str], ...] = (
        ("Easy", "Random moves"),
        ("Medium", "Win / block logic"),
        ("Hard", "Unbeatable minimax"),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.board = Board()
        self.human = Mark.X
        self.ai: TicTacToeAI | None = None
        self.difficulty: Difficulty | None = None
        self.movelog = MoveLog()
        self.phase = "select"  # "select" -> "playing" -> "over"
        self.hovered = -1      # hovered option (select) or cell (playing)
        self.status = ""
        self.game_over = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Return to the difficulty picker with a clean slate."""
        super().reset()
        self.board.reset()
        self.movelog = MoveLog()
        self.difficulty = None
        self.ai = None
        self.phase = "select"
        self.hovered = -1
        self.status = ""
        self.game_over = False
        self.score = 0

    def _start_round(self, difficulty: Difficulty) -> None:
        """Begin a fresh round against the chosen difficulty."""
        self.difficulty = difficulty
        self.ai = TicTacToeAI(mark=Mark.O, difficulty=difficulty)
        self.board.reset()
        self.movelog = MoveLog()
        self.phase = "playing"
        self.hovered = -1
        self.status = "Your turn (X)"
        self.game_over = False
        self.score = 0

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _cell_rects(self) -> list[pygame.Rect]:
        """Screen rectangles for the 9 cells, laid out as a centred 3x3 grid."""
        size = config.TTT_CELL_SIZE
        total = size * 3
        ox = (config.SCREEN_WIDTH - total) // 2  # centre the grid horizontally
        oy = (config.SCREEN_HEIGHT - total) // 2 + 20  # nudged down past the title
        # Map flat index 0..8 to a grid position: i%3 -> column, i//3 -> row.
        return [
            pygame.Rect(ox + (i % 3) * size, oy + (i // 3) * size, size, size)
            for i in range(9)
        ]

    def _option_rects(self) -> list[pygame.Rect]:
        """Three difficulty cards centred horizontally."""
        card_w, card_h, gap = 240, 150, 40
        total = 3 * card_w + 2 * gap
        ox = (config.SCREEN_WIDTH - total) // 2
        oy = (config.SCREEN_HEIGHT - card_h) // 2
        return [
            pygame.Rect(ox + i * (card_w + gap), oy, card_w, card_h)
            for i in range(3)
        ]

    # ------------------------------------------------------------------
    # Result handling
    # ------------------------------------------------------------------
    def _handle_result(self) -> None:
        winner = self.board.winner()
        if winner is self.human:
            self.score = config.TTT_WIN_SCORE
            self.status = "You win!"
            self.phase = "over"
            self.game_over = True
            self.submit_score()
        elif winner is not None:
            self.status = "AI wins!"
            self.phase = "over"
            self.game_over = True
        elif self.board.is_full():
            self.score = config.TTT_DRAW_SCORE
            self.status = "Draw!"
            self.phase = "over"
            self.game_over = True
            self.submit_score()

    def _human_move(self, index: int) -> None:
        """Play the human move at *index*, then let the AI reply."""
        if self.board.cells[index] is not Mark.EMPTY or self.ai is None:
            return
        self.board.make_move(index, self.human)
        self.movelog.record(index, self.human)
        self._handle_result()
        # Only reply if the round is still live.
        if self.phase == "playing" and self.board.winner() is None and not self.board.is_full():
            ai_move = self.ai.choose_move(self.board)
            if ai_move != -1:
                self.board.make_move(ai_move, self.ai.mark)
                self.movelog.record(ai_move, self.ai.mark)
                self._handle_result()

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
                    self._start_round(list(Difficulty)[event.key - pygame.K_1])
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.phase == "select":
                    for i, rect in enumerate(self._option_rects()):
                        if rect.collidepoint(event.pos):
                            self._start_round(list(Difficulty)[i])
                            break
                elif self.phase == "playing":
                    for i, rect in enumerate(self._cell_rects()):
                        if rect.collidepoint(event.pos):
                            self._human_move(i)
                            break
        return True

    def update(self, dt: float) -> None:
        """Recompute the hovered option/cell from the current mouse position."""
        mx, my = pygame.mouse.get_pos()
        self.hovered = -1
        if self.phase == "select":
            for i, rect in enumerate(self._option_rects()):
                if rect.collidepoint((mx, my)):
                    self.hovered = i
                    break
        elif self.phase == "playing" and not self.game_over:
            for i, rect in enumerate(self._cell_rects()):
                if rect.collidepoint((mx, my)) and self.board.cells[i] is Mark.EMPTY:
                    self.hovered = i
                    break

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BACKGROUND)
        draw_text(surface, self.name, config.FONT_SIZE_LARGE, config.ACCENT,
                  center=(config.SCREEN_WIDTH // 2, 70))
        if self.phase == "select":
            self._draw_picker(surface)
        else:
            self._draw_board(surface)

    def _draw_picker(self, surface: pygame.Surface) -> None:
        draw_text(surface, "Choose difficulty", config.FONT_SIZE_MEDIUM, config.WHITE,
                  center=(config.SCREEN_WIDTH // 2, 130))
        for i, rect in enumerate(self._option_rects()):
            hover = self.hovered == i
            bg = config.HOVER if hover else config.PANEL_BG
            border = config.ACCENT if hover else config.LIGHT_GREY
            pygame.draw.rect(surface, bg, rect, border_radius=12)
            pygame.draw.rect(surface, border, rect, 3 if hover else 2, border_radius=12)
            label, blurb = self._OPTIONS[i]
            draw_text(surface, f"{i + 1}. {label}", config.FONT_SIZE_MEDIUM,
                      config.ACCENT if hover else config.WHITE, center=(rect.centerx, rect.centery - 15))
            draw_text(surface, blurb, config.FONT_SIZE_SMALL, config.LIGHT_GREY,
                      center=(rect.centerx, rect.centery + 22))
        draw_text(surface, f"Best: {self.best_score}", config.FONT_SIZE_SMALL,
                  config.YELLOW, center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 60))

    def _draw_board(self, surface: pygame.Surface) -> None:
        draw_text(surface, self.status, config.FONT_SIZE_MEDIUM, config.WHITE,
                  center=(config.SCREEN_WIDTH // 2, 120))

        rects = self._cell_rects()
        mark_colors = {Mark.X: config.CYAN, Mark.O: config.RED}
        for i, rect in enumerate(rects):
            pygame.draw.rect(surface, config.PANEL_BG, rect)
            # Hover highlight + faint ghost mark on the hovered empty cell.
            if i == self.hovered and self.phase == "playing":
                overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
                overlay.fill((*config.CYAN, 45))
                surface.blit(overlay, rect.topleft)
                draw_text(surface, self.human.value, config.TTT_CELL_SIZE - 40,
                          config.CYAN, center=rect.center)  # ghost preview
            pygame.draw.rect(surface, config.LIGHT_GREY, rect, 2)
            mark = self.board.cells[i]
            if mark is not Mark.EMPTY:
                draw_text(surface, mark.value, config.TTT_CELL_SIZE - 40,
                          mark_colors[mark], center=rect.center)

        winner = self.board.winner()
        if winner is not None:
            for a, _b, c in (line for line in WIN_LINES if self.board.cells[line[0]] is winner):
                pygame.draw.line(surface, config.YELLOW, rects[a].center, rects[c].center, 6)

        self._draw_history(surface)
        self.draw_hud(surface, f"Score: {self.score}", f"Best: {self.best_score}",
                      f"Difficulty: {self.difficulty.value.title() if self.difficulty else '-'}")
        if self.game_over:
            draw_text(surface, "Press R to change difficulty  |  ESC for menu",
                      config.FONT_SIZE_SMALL, config.LIGHT_GREY,
                      center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT - 30))

    def _draw_history(self, surface: pygame.Surface) -> None:
        """Render the move log down the right-hand side."""
        x = config.SCREEN_WIDTH - 230
        y = 90
        draw_text(surface, "Move history", config.FONT_SIZE_SMALL, config.LIGHT_GREY, topleft=(x, y))
        y += 24
        mark_colors = {Mark.X: config.CYAN, Mark.O: config.RED}
        for n, (cell, mark) in enumerate(self.movelog.entries, start=1):
            draw_text(surface, f"{n}. {mark.value} -> cell {cell}", config.FONT_SIZE_SMALL,
                      mark_colors[mark], topleft=(x, y))
            y += 20
