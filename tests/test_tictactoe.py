"""Tests for Tic-Tac-Toe board and minimax AI."""

from __future__ import annotations

import random

from games.tictactoe import (
    Board,
    Difficulty,
    Mark,
    MinimaxAI,
    MoveLog,
    TicTacToeAI,
)


def board_from(marks: str) -> Board:
    """Build a board from a 9-char string like 'XOXO' padded with spaces."""
    cells = [Mark(c) if c in "XO" else Mark.EMPTY for c in marks.ljust(9)]
    return Board(cells)


def test_winner_rows() -> None:
    b = board_from("XXXOO....")
    assert b.winner() is Mark.X


def test_winner_columns() -> None:
    b = board_from("X..X..X..")
    assert b.winner() is Mark.X


def test_winner_diagonal() -> None:
    b = board_from("X...X...X")
    assert b.winner() is Mark.X


def test_no_winner() -> None:
    b = board_from("OOXXXOOXX")  # full board, no three-in-a-row anywhere
    assert b.winner() is None
    assert b.is_full() is True
    assert b.is_over() is True


def test_available_moves() -> None:
    b = board_from("X.O......")
    assert b.available_moves() == [1, 3, 4, 5, 6, 7, 8]


def test_make_and_undo_move() -> None:
    b = Board()
    b.make_move(4, Mark.X)
    assert b.cells[4] is Mark.X
    b.undo_move(4)
    assert b.cells[4] is Mark.EMPTY


def test_ai_takes_winning_move() -> None:
    # AI (O) can win with the top-right corner
    b = board_from("OO.X.X...")
    ai = MinimaxAI(mark=Mark.O)
    move = ai.choose_move(b)
    b.make_move(move, Mark.O)
    assert b.winner() is Mark.O


def test_ai_blocks_opponent_win() -> None:
    # Human (X) threatens to win at index 2
    b = board_from("XX.......")
    ai = MinimaxAI(mark=Mark.O)
    assert ai.choose_move(b) == 2


def test_ai_never_loses_full_selfplay() -> None:
    """The AI (O) must never lose, even against a perfect X opponent."""
    ai = MinimaxAI(mark=Mark.O)

    for first in Board().available_moves():
        b = Board()
        b.make_move(first, Mark.X)
        turn = Mark.O  # after X opens, it is O's turn
        while not b.is_over():
            if turn is Mark.O:
                move = ai.choose_move(b)
            else:
                move = b.available_moves()[0]  # X plays first legal (worst case for O)
            b.make_move(move, turn)
            turn = turn.opponent
        assert b.winner() is not Mark.X, f"AI lost when X opened at {first}"


# --------------------------------------------------------------------------
# Difficulty levels
# --------------------------------------------------------------------------
def test_easy_returns_legal_move() -> None:
    b = Board()
    ai = TicTacToeAI(Mark.O, Difficulty.EASY, rng=random.Random(3))
    assert ai.choose_move(b) in b.available_moves()


def test_easy_no_move_on_full_board() -> None:
    b = board_from("XOXOXOOXX")
    ai = TicTacToeAI(Mark.O, Difficulty.EASY, rng=random.Random(3))
    assert ai.choose_move(b) == -1


def test_medium_takes_immediate_win() -> None:
    b = board_from("OO.......")  # O wins at index 2
    ai = TicTacToeAI(Mark.O, Difficulty.MEDIUM, rng=random.Random(1))
    assert ai.choose_move(b) == 2


def test_medium_blocks_opponent_win() -> None:
    b = board_from("XX.......")  # X threatens index 2
    ai = TicTacToeAI(Mark.O, Difficulty.MEDIUM, rng=random.Random(1))
    assert ai.choose_move(b) == 2


def test_medium_prefers_center() -> None:
    b = Board()
    ai = TicTacToeAI(Mark.O, Difficulty.MEDIUM, rng=random.Random(1))
    assert ai.choose_move(b) == 4


def test_medium_corner_fallback_when_center_taken() -> None:
    b = board_from("....O....")  # centre occupied, no win/block available
    ai = TicTacToeAI(Mark.O, Difficulty.MEDIUM, rng=random.Random(1))
    assert ai.choose_move(b) in (0, 2, 6, 8)


def test_hard_delegates_to_minimax() -> None:
    b = board_from("XX.......")  # must block at 2, like minimax
    ai = TicTacToeAI(Mark.O, Difficulty.HARD, rng=random.Random(1))
    assert ai.choose_move(b) == 2


# --------------------------------------------------------------------------
# Move history
# --------------------------------------------------------------------------
def test_movelog_records_in_order() -> None:
    log = MoveLog()
    log.record(4, Mark.X)
    log.record(0, Mark.O)
    assert log.cells() == [4, 0]
    assert len(log) == 2
    assert log.last == (0, Mark.O)


def test_movelog_undo() -> None:
    log = MoveLog()
    log.record(4, Mark.X)
    assert log.undo() == (4, Mark.X)
    assert log.undo() is None
    assert len(log) == 0
    assert log.last is None
