"""Tests for Memory board logic."""

from __future__ import annotations

import random

import config
from games.memory import MemoryBoard


def make_board(cols: int = 4, rows: int = 4) -> MemoryBoard:
    return MemoryBoard(cols=cols, rows=rows, rng=random.Random(7))


def match_any_pair(b: MemoryBoard) -> None:
    """Flip one currently-matched pair on the board and clear the lock."""
    for i, s in enumerate(b.symbols):
        if b.matched[i]:
            continue
        mate = next(
            j for j, t in enumerate(b.symbols) if t == s and j != i and not b.matched[j]
        )
        b.flip(i)
        b.flip(mate)
        b._lock_until = 0.0
        return


def test_pairs_created() -> None:
    b = make_board()
    assert b.total_pairs == 8
    assert len(b.symbols) == 16
    # Every symbol appears exactly twice
    for sym in set(b.symbols):
        assert b.symbols.count(sym) == 2


def test_matching_pair_scores() -> None:
    b = make_board()
    # Find two indices with the same symbol
    target = b.symbols[0]
    mate = b.symbols.index(target, 1)
    assert b.flip(0) == "flipped"
    assert b.flip(mate) == "match"
    assert b.matched[0] and b.matched[mate]
    assert b.moves == 1
    assert b.matches_found == 1


def test_mismatch_penalises_moves() -> None:
    b = make_board()
    target = b.symbols[0]
    other = next(i for i, s in enumerate(b.symbols) if s != target and i != 0)
    b.flip(0)
    assert b.flip(other) == "mismatch"
    assert b.moves == 1
    assert b.matches_found == 0
    assert b.flipped == [0, other]


def test_cannot_flip_matched_or_active() -> None:
    b = make_board()
    target = b.symbols[0]
    mate = b.symbols.index(target, 1)
    b.flip(0)
    b.flip(mate)  # matched now
    assert b.flip(0) == "ignored"  # already matched


def test_resolve_mismatch_clears() -> None:
    b = make_board()
    target = b.symbols[0]
    other = next(i for i, s in enumerate(b.symbols) if s != target and i != 0)
    b.flip(0)
    b.flip(other)
    # Simulate the lockout expiring by clearing the timer directly
    b._lock_until = 0.0
    b.resolve_mismatch()
    assert b.flipped == []


def test_completion_and_score() -> None:
    b = make_board()
    # Match every pair to complete the board
    seen: set[str] = set()
    for i, sym in enumerate(b.symbols):
        if sym in seen:
            continue
        mate = b.symbols.index(sym, i + 1)
        b.flip(i)
        b.flip(mate)
        b._lock_until = 0.0
        seen.add(sym)
    assert b.is_complete is True
    assert b.score(elapsed=10.0) > 0


def test_invalid_grid_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        MemoryBoard(cols=3, rows=3)  # odd number of cells


# --------------------------------------------------------------------------
# Combo system
# --------------------------------------------------------------------------
def test_combo_increments_on_consecutive_matches() -> None:
    b = make_board()
    match_any_pair(b)
    assert b.combo == 1
    match_any_pair(b)
    assert b.combo == 2
    assert b.best_combo == 2


def test_combo_resets_on_mismatch() -> None:
    b = make_board()
    match_any_pair(b)  # combo = 1
    # Force a mismatch between two unmatched cards of different symbols.
    i = next(i for i, m in enumerate(b.matched) if not m)
    other = next(
        j for j, s in enumerate(b.symbols)
        if not b.matched[j] and j != i and s != b.symbols[i]
    )
    b.flip(i)
    b.flip(other)
    assert b.combo == 0
    b._lock_until = 0.0


def test_combo_multiplier_grows_with_streak() -> None:
    b = make_board()
    b.combo = 1
    m1 = b.combo_multiplier()
    b.combo = 3
    m3 = b.combo_multiplier()
    assert m3 > m1
    assert m1 == 1.0


def test_earned_scales_with_combo() -> None:
    b = make_board()
    match_any_pair(b)  # combo 1 -> 1.0x
    match_any_pair(b)  # combo 2 -> 1.5x
    expected = round(config.MEMORY_MATCH_SCORE * 1.0) + round(config.MEMORY_MATCH_SCORE * 1.5)
    assert b.earned == expected


# --------------------------------------------------------------------------
# Themes
# --------------------------------------------------------------------------
def test_custom_tokens_are_used() -> None:
    b = MemoryBoard(cols=2, rows=2, tokens=("A", "B"), rng=random.Random(0))
    assert set(b.symbols) <= {"A", "B"}
    assert len(b.symbols) == 4
