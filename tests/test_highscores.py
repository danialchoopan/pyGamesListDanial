"""Tests for the SQLite high score store."""

from __future__ import annotations

from utils import HighScoreStore


def test_add_and_top_scores(store: HighScoreStore) -> None:
    store.add_score("snake", "dan", 100)
    store.add_score("snake", "mia", 300)
    store.add_score("snake", "leo", 200)
    top = store.top_scores("snake", limit=2)
    assert [s.name for s in top] == ["MIA", "LEO"]
    assert top[0].score == 300


def test_scores_isolated_per_game(store: HighScoreStore) -> None:
    store.add_score("snake", "dan", 100)
    store.add_score("breakout", "mia", 50)
    assert store.top_scores("breakout")[0].score == 50
    assert len(store.top_scores("snake")) == 1


def test_best_score(store: HighScoreStore) -> None:
    assert store.best_score("snake") == 0  # empty
    store.add_score("snake", "dan", 100)
    store.add_score("snake", "mia", 250)
    assert store.best_score("snake") == 250


def test_empty_name_normalized(store: HighScoreStore) -> None:
    store.add_score("snake", "   ", 10)
    assert store.top_scores("snake")[0].name == "AAA"


def test_is_top_n(store: HighScoreStore) -> None:
    for i in range(5):
        store.add_score("snake", f"p{i}", (5 - i) * 10)  # 50,40,30,20,10
    assert store.is_top_n("snake", 99) is True
    assert store.is_top_n("snake", 11) is True   # beats worst (10)
    assert store.is_top_n("snake", 5) is False   # below all top 5
    assert store.is_top_n("snake", 0) is False   # zero never counts


def test_clear_specific_game(store: HighScoreStore) -> None:
    store.add_score("snake", "dan", 100)
    store.add_score("breakout", "mia", 50)
    store.clear("snake")
    assert store.top_scores("snake") == []
    assert len(store.top_scores("breakout")) == 1


def test_persistence_across_instances(tmp_path) -> None:
    path = tmp_path / "hs.db"
    with HighScoreStore(path) as s:
        s.add_score("snake", "dan", 420)
    with HighScoreStore(path) as s2:
        assert s2.best_score("snake") == 420
