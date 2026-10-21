"""Tests for Tic-Tac-Toe board and minimax AI."""

from __future__ import annotations

from games.tictactoe import Board, Mark, MinimaxAI


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
