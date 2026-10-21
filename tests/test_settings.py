"""Tests for settings persistence."""

from __future__ import annotations

import json

import config
from utils import Settings, load_settings, save_settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.music_volume == config.DEFAULT_MUSIC_VOLUME
    assert s.sfx_volume == config.DEFAULT_SFX_VOLUME
    assert s.fullscreen is False


def test_save_and_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(music_volume=0.25, sfx_volume=0.9, show_fps=True)
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.music_volume == 0.25
    assert loaded.sfx_volume == 0.9
    assert loaded.show_fps is True


def test_load_missing_file_returns_defaults(tmp_path) -> None:
    loaded = load_settings(tmp_path / "nonexistent.json")
    assert loaded == Settings()


def test_load_corrupt_file_returns_defaults(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{ not valid json", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_load_ignores_unknown_keys(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"music_volume": 0.3, "bogus_key": 1}), encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.music_volume == 0.3


def test_volumes_clamped_on_load(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"music_volume": 5.0, "sfx_volume": -1.0}), encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.music_volume == 1.0
    assert loaded.sfx_volume == 0.0
