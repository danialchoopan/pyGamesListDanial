"""Tests for the shared ``BaseGame`` pause/resume behaviour.

Pausing is cross-cutting (every game inherits it), so it is tested against a
tiny stub subclass rather than any one game. The audio service is replaced by
a recorder so the assertions do not depend on a real audio device being
present - we assert the *calls* were made, not that sound was produced.
"""

from __future__ import annotations

from typing import Any

import pygame

import config
from base_game import BaseGame


class RecordingAudio:
    """Stand-in for AudioService that records the calls games make."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def play(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append("play")

    def play_music(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append("play_music")

    def pause_music(self) -> None:
        self.calls.append("pause_music")

    def resume_music(self) -> None:
        self.calls.append("resume_music")

    def stop_music(self) -> None:
        self.calls.append("stop_music")

    def update_settings(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append("update_settings")


class _StubSettings:
    """Only the attributes the shared BaseGame surface touches."""

    show_fps = False
    music_volume = 0.5
    sfx_volume = 0.5


class StubGame(BaseGame):
    """Minimal concrete game for exercising the shared loop and pause logic."""

    name = "Stub"
    score_key = "stub"
    music_track = "overworld"

    def __init__(self, screen: pygame.Surface) -> None:
        # Intentionally skip BaseGame.__init__ (which loads fonts/assets);
        # we only need the pause/scoring surface under test.
        self.screen = screen
        self.score = 0
        self.paused = False
        self.settings = _StubSettings()  # type: ignore[assignment]
        self.audio = RecordingAudio()  # type: ignore[assignment]
        self.highscores = _NullScores()  # type: ignore[assignment]
        self.update_calls = 0

    # -- BaseGame abstract surface -------------------------------------
    def handle_events(self, events):  # type: ignore[no-untyped-def]
        return True

    def update(self, dt: float) -> None:
        self.update_calls += 1

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.BLACK)

    @property
    def recorder(self) -> RecordingAudio:
        """Typed view of the audio stub (self.audio is AudioService-typed)."""
        return self.audio  # type: ignore[return-value]


class _NullScores:
    """Minimal high-score store stub (add_score / best_score)."""

    def __init__(self) -> None:
        self.scores: list[tuple[str, str, int]] = []

    def add_score(self, game: str, name: str, score: int) -> None:
        self.scores.append((game, name, score))

    def best_score(self, game: str) -> int:
        matching = [s for g, _n, s in self.scores if g == game]
        return max(matching, default=0)


def _surface() -> pygame.Surface:
    return pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))


def test_starts_unpaused() -> None:
    game = StubGame(_surface())
    assert game.paused is False


def test_toggle_pause_flips_state_and_returns_new_value() -> None:
    game = StubGame(_surface())
    assert game.toggle_pause() is True
    assert game.paused is True
    assert game.toggle_pause() is False
    assert game.paused is False


def test_pauses_and_resumes_music_in_step() -> None:
    game = StubGame(_surface())
    game.toggle_pause()
    assert game.recorder.calls == ["pause_music"]
    game.toggle_pause()
    assert game.recorder.calls == ["pause_music", "resume_music"]


def test_toggling_twice_leaves_music_paired() -> None:
    game = StubGame(_surface())
    game.toggle_pause()
    game.toggle_pause()
    assert game.recorder.calls == ["pause_music", "resume_music"]


def test_pause_overlay_draws_without_error() -> None:
    pygame.font.init()  # draw_text renders a font; the dummy driver has none
    game = StubGame(_surface())
    game.toggle_pause()
    surface = _surface()
    game.draw(surface)
    game.draw_pause_overlay(surface)  # must not raise


def test_submit_score_persists_and_updates_best() -> None:
    game = StubGame(_surface())
    game.score = 120
    game.submit_score(name="TST")
    assert game.best_score == 120
    game.score = 40
    game.submit_score(name="LOW")
    assert game.best_score == 120  # the higher score survives


def test_start_resets_pause_state() -> None:
    game = StubGame(_surface())
    game.paused = True
    game.start()  # type: ignore[call-arg]  # concrete games pass runtime args
    assert game.paused is False


def test_music_track_declared_for_enhanced_games() -> None:
    # The three enhanced games opt into background music via music_track.
    from games.breakout import BreakoutGame
    from games.platformer import PlatformerGame
    from games.space_shooter import SpaceShooterGame

    for game_cls in (PlatformerGame, SpaceShooterGame, BreakoutGame):
        assert game_cls.music_track is not None, game_cls.__name__
