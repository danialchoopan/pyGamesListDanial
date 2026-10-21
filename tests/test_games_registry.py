"""Smoke tests: every game class is registered and subclasses BaseGame."""

from __future__ import annotations

import config
from base_game import BaseGame
from games import GAME_CLASSES


def test_six_games_registered() -> None:
    assert len(GAME_CLASSES) == 6


def test_all_are_base_game_subclasses() -> None:
    for cls in GAME_CLASSES:
        assert issubclass(cls, BaseGame), f"{cls} is not a BaseGame"


def test_unique_score_keys() -> None:
    keys = [cls.score_key for cls in GAME_CLASSES]
    assert len(set(keys)) == len(keys)


def test_game_metadata_present() -> None:
    for cls in GAME_CLASSES:
        assert cls.name
        assert cls.description
        assert cls.score_key


def test_config_constants_sane() -> None:
    assert config.SCREEN_WIDTH > 0
    assert config.SCREEN_HEIGHT > 0
    assert 0.0 <= config.DEFAULT_MUSIC_VOLUME <= 1.0
    assert 0.0 <= config.DEFAULT_SFX_VOLUME <= 1.0
