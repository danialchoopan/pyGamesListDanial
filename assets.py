"""Asset loading and management, plus the hub-wide audio service.

Two responsibilities live here:

1. :class:`AssetManager` lazily loads and caches sounds, images and music
   from the ``assets/`` folder. Missing or unreadable assets return ``None``
   instead of raising, so the hub still runs on a machine with no asset
   files at all (CI, fresh checkout, missing audio device).

2. :class:`AudioService` plays sound effects and background music honouring
   the volumes in :class:`utils.Settings`. Every method is a safe no-op when
   the audio subsystem is unavailable, so games never need to guard their
   own sound calls.

Sounds that are not shipped as files are *synthesised* from a small table of
tone recipes (:data:`SFX_RECIPES`), and background music falls back to a
generated chiptune loop. That way the games have real audio feedback without
committing binary files to the repository; dropping a real ``.wav``/``.ogg``
into ``assets/sounds`` (or ``assets/music``) simply overrides the generated
version.
"""

from __future__ import annotations

import io
import math
import random
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pygame

import config
from utils import Settings, clamp

#: Extensions searched (in order) when resolving a named asset file.
SOUND_EXTENSIONS: tuple[str, ...] = (".wav", ".ogg", ".mp3")
IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp")
MUSIC_EXTENSIONS: tuple[str, ...] = (".ogg", ".mp3", ".wav")


# --------------------------------------------------------------------------
# Procedural sound-effect synthesis
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ToneRecipe:
    """A description of one synthesised sound effect.

    ``sweep`` is the total frequency change (in Hz) applied linearly across
    the sound's duration, which turns a plain tone into the classic arcade
    "pew" (downward sweep) or "pickup" (upward sweep).
    """

    freq: float          # starting frequency in Hz
    duration: float      # length in seconds
    wave: str = "sine"   # oscillator: sine | square | triangle | noise
    sweep: float = 0.0   # total frequency change across the sound
    volume: float = 0.5  # peak amplitude, 0.0 - 1.0
    attack: float = 0.004  # seconds of fade-in (kills clicks at the start)


#: Every sound effect the games ask for by name. Keys are the names used with
#: ``audio.play("...")``; if a file of the same name exists under
#: ``assets/sounds`` it wins over the generated version.
SFX_RECIPES: dict[str, ToneRecipe] = {
    # Shared / menu
    "select":      ToneRecipe(520, 0.05, "sine", volume=0.3),
    "confirm":     ToneRecipe(660, 0.12, "sine", sweep=220, volume=0.35),
    # Platformer
    "jump":        ToneRecipe(330, 0.16, "square", sweep=520, volume=0.30),
    "coin":        ToneRecipe(988, 0.12, "square", sweep=330, volume=0.28),
    "stomp":       ToneRecipe(240, 0.14, "square", sweep=-140, volume=0.35),
    "powerup":     ToneRecipe(440, 0.28, "square", sweep=1100, volume=0.32),
    "checkpoint":  ToneRecipe(600, 0.22, "sine", sweep=400, volume=0.35),
    "hurt":        ToneRecipe(320, 0.26, "square", sweep=-230, volume=0.40),
    "level_clear": ToneRecipe(440, 0.50, "square", sweep=900, volume=0.32),
    # Space shooter
    "shoot":       ToneRecipe(900, 0.08, "square", sweep=-460, volume=0.24),
    "enemy_shoot": ToneRecipe(420, 0.10, "square", sweep=-160, volume=0.20),
    "explode":     ToneRecipe(160, 0.38, "noise", volume=0.42, attack=0.001),
    "hit":         ToneRecipe(520, 0.06, "square", sweep=-200, volume=0.22),
    "boss_hit":    ToneRecipe(180, 0.12, "triangle", sweep=-60, volume=0.35),
    "player_hit":  ToneRecipe(260, 0.40, "square", sweep=-190, volume=0.45),
    "wave_clear":  ToneRecipe(560, 0.32, "sine", sweep=520, volume=0.32),
    "buy":         ToneRecipe(700, 0.16, "sine", sweep=400, volume=0.30),
    "achievement": ToneRecipe(880, 0.42, "triangle", sweep=260, volume=0.32),
    # Breakout
    "paddle":      ToneRecipe(300, 0.07, "square", sweep=-40, volume=0.26),
    "brick":       ToneRecipe(620, 0.06, "square", sweep=-180, volume=0.24),
    "brick_hard":  ToneRecipe(360, 0.07, "square", sweep=-90, volume=0.26),
    "laser":       ToneRecipe(1200, 0.18, "square", sweep=-880, volume=0.24),
    "life_lost":   ToneRecipe(400, 0.55, "square", sweep=-310, volume=0.40),
}


def note_freq(midi: int) -> float:
    """Convert a MIDI note number to a frequency in Hz (A4 = 440 = MIDI 69)."""
    return float(440.0 * 2.0 ** ((midi - 69) / 12.0))


def render_pcm(recipe: ToneRecipe, sample_rate: int = config.SFX_SAMPLE_RATE) -> array:
    """Synthesise 16-bit mono PCM samples for *recipe*.

    The envelope combines a short linear attack with a ``(1 - t)^1.5`` decay
    that reaches zero exactly at the end, so the sound starts and stops
    without the audible click you get from a raw square wave being switched
    on and off.
    """
    count = max(1, int(recipe.duration * sample_rate))
    attack_count = max(1, int(recipe.attack * sample_rate))
    peak = clamp(recipe.volume, 0.0, 1.0)
    slope = recipe.sweep / recipe.duration  # Hz per second
    out = array("h")
    phase = 0.0
    tau = 2.0 * math.pi
    # Deterministic noise keeps synthesised sounds (and their tests) stable.
    noise_rng = random.Random(0xC0FFEE)
    for i in range(count):
        t = i / sample_rate
        phase += tau * (recipe.freq + slope * t) / sample_rate
        if recipe.wave == "noise":
            osc = noise_rng.uniform(-1.0, 1.0)
        elif recipe.wave == "square":
            osc = 1.0 if math.sin(phase) >= 0.0 else -1.0
        elif recipe.wave == "triangle":
            osc = 2.0 * math.asin(math.sin(phase)) / math.pi
        else:
            osc = math.sin(phase)
        envelope = min(1.0, i / attack_count) * (1.0 - i / count) ** 1.5
        out.append(int(osc * envelope * peak * 32767))
    return out


def _interleaved_bytes(samples: array, channels: int) -> bytes:
    """Repeat each mono sample *channels* times (mixer-ready raw PCM)."""
    if channels <= 1:
        return samples.tobytes()
    interleaved = array("h")
    for sample in samples:
        interleaved.extend((sample,) * channels)
    return interleaved.tobytes()


# --------------------------------------------------------------------------
# Fallback music loop
# --------------------------------------------------------------------------
#: Four-bar chord progression (Am - F - C - G) as (bass root, triad) pairs.
_MUSIC_PROGRESSION: tuple[tuple[int, tuple[int, int, int]], ...] = (
    (45, (48, 52, 55)),  # A minor
    (41, (45, 48, 52)),  # F major
    (48, (52, 55, 60)),  # C major
    (43, (47, 50, 55)),  # G major
)


def render_music_loop(
    bpm: int = config.MUSIC_FALLBACK_BPM,
    sample_rate: int = config.MUSIC_SAMPLE_RATE,
) -> array:
    """Generate a soft looping chiptune: bass eighths + a gentle arpeggio.

    The two voices are *mixed* (played simultaneously, not concatenated), and
    each unique note is only rendered once then reused. The result is
    normalised, and the first/last ~30 ms are faded so looping the buffer does
    not click at the seam.
    """
    beat = 60.0 / bpm
    bar = beat * 4.0
    eighth = bar / 8.0
    out = array("h")
    # Unique notes are cached so a whole loop renders ~16 notes, not 64.
    cache: dict[tuple[float, str], array] = {}

    def note(freq: float, wave_kind: str, level: float) -> array:
        key = (round(freq, 2), wave_kind)
        if key not in cache:
            cache[key] = _render_note(freq, eighth, sample_rate, wave_kind, level)
        return cache[key]

    for root, triad in _MUSIC_PROGRESSION:
        bass = note(note_freq(root - 12), "triangle", 0.55)
        arps = [note(note_freq(midi), "square", 0.22) for midi in triad]
        # Classic up-down arpeggio pattern over the triad.
        pattern = (arps[0], arps[1], arps[2], arps[1]) * 2
        for arp in pattern:
            out.extend(_mix(bass, arp))
    # Normalise to the target amplitude, then crossfade the loop seam.
    peak = max(1, max(abs(s) for s in out))
    gain = 0.30 * 32767.0 / peak
    fade = max(1, int(sample_rate * 0.03))
    for i in range(min(fade, len(out))):
        edge = i / fade
        out[i] = int(out[i] * edge)
        out[-1 - i] = int(out[-1 - i] * edge)
    return array("h", (int(clamp(s * gain, -32767, 32767)) for s in out))


def _mix(base: array, other: array) -> array:
    """Sum two equal-length 16-bit buffers, clipping on overflow."""
    mixed = array("h", base)
    for i, sample in enumerate(other):
        mixed[i] = int(clamp(mixed[i] + sample, -32767, 32767))
    return mixed


def _render_note(
    freq: float, duration: float, sample_rate: int, wave_kind: str, level: float
) -> array:
    """Render one enveloped note (used by the music generator)."""
    count = max(1, int(duration * sample_rate))
    out = array("h")
    phase_step = 2.0 * math.pi * freq / sample_rate
    phase = 0.0
    for i in range(count):
        phase += phase_step
        if wave_kind == "square":
            osc = 1.0 if math.sin(phase) >= 0.0 else -1.0
        else:
            osc = 2.0 * math.asin(math.sin(phase)) / math.pi
        envelope = (1.0 - i / count) ** 0.6  # quick decay per note
        out.append(int(osc * envelope * level * 32767))
    return out


def wav_bytes(samples: array, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM samples in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.tobytes())
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Asset manager
# --------------------------------------------------------------------------
def mixer_ready() -> bool:
    """True when pygame's mixer is (or can be) opened for audio output."""
    if pygame.mixer.get_init() is not None:
        return True
    # Without an audio device this raises pygame.error - which we treat as
    # "no audio", never as a crash.
    try:
        pygame.mixer.init()
    except Exception:  # noqa: BLE001 - pygame raises several error types
        return False
    return pygame.mixer.get_init() is not None


class AssetManager:
    """Loads and caches sounds, images and music for the whole hub.

    Everything is resolved lazily on first request and cached forever after;
    the cache means a sound fired 60 times a second still only loads once.
    """

    def __init__(self, root: Path = config.ASSETS_DIR) -> None:
        self.root = Path(root)
        self._sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._images: dict[str, pygame.Surface | None] = {}
        self._music: dict[str, bytes | None] = {}
        #: Number of real asset files loaded so far (handy in tests / stats).
        self.loaded_files = 0

    # -- sounds ---------------------------------------------------------
    def sound(self, name: str) -> pygame.mixer.Sound | None:
        """Return a cached :class:`pygame.mixer.Sound` for *name*.

        Resolution order: ``assets/sounds/<name>.<ext>`` file, then the
        procedural recipe in :data:`SFX_RECIPES`. Returns ``None`` when audio
        is unavailable or the sound is simply unknown.
        """
        if name in self._sounds:
            return self._sounds[name]
        if not mixer_ready():
            return None  # don't cache: audio may become available later
        sound = self._load_sound_file(name)
        if sound is None:
            sound = self._synthesize_sound(name)
        self._sounds[name] = sound
        return sound

    def _load_sound_file(self, name: str) -> pygame.mixer.Sound | None:
        directory = self.root / "sounds"
        for extension in SOUND_EXTENSIONS:
            path = directory / f"{name}{extension}"
            if not path.is_file():
                continue
            try:
                self.loaded_files += 1
                return pygame.mixer.Sound(str(path))
            except (pygame.error, OSError):
                return None
        return None

    def _synthesize_sound(self, name: str) -> pygame.mixer.Sound | None:
        recipe = SFX_RECIPES.get(name)
        if recipe is None:
            return None
        state = pygame.mixer.get_init()
        if state is None:
            return None
        frequency, format_code, channels = state
        # The raw buffer must match the mixer's own format or playback would
        # be garbled; 16-bit signed is pygame's default, anything else (8-bit
        # or float mixers) is rare enough that we simply skip synthesis.
        if format_code != -16:
            return None
        pcm = render_pcm(recipe, sample_rate=max(1, int(frequency)))
        try:
            return pygame.mixer.Sound(buffer=_interleaved_bytes(pcm, channels))
        except pygame.error:
            return None

    # -- images ---------------------------------------------------------
    def image(self, name: str) -> pygame.Surface | None:
        """Return a cached image for *name*, or ``None`` when unavailable."""
        if name in self._images:
            return self._images[name]
        result: pygame.Surface | None = None
        directory = self.root / "images"
        for extension in IMAGE_EXTENSIONS:
            path = directory / f"{name}{extension}"
            if not path.is_file():
                continue
            try:
                result = pygame.image.load(str(path))
                self.loaded_files += 1
            except (pygame.error, OSError):
                result = None
            break
        self._images[name] = result
        return result

    # -- music ----------------------------------------------------------
    def music_path(self, track: str) -> Path | None:
        """Real music file for *track*, when one has been dropped in."""
        directory = self.root / "music"
        for extension in MUSIC_EXTENSIONS:
            path = directory / f"{track}{extension}"
            if path.is_file():
                return path
        return None

    def music_bytes(self, track: str) -> bytes | None:
        """Generated WAV bytes for *track*'s fallback loop (cached)."""
        if track not in self._music:
            self._music[track] = wav_bytes(
                render_music_loop(), config.MUSIC_SAMPLE_RATE
            )
        return self._music[track]

    def music_source(self, track: str) -> str | BinaryIO | None:
        """A ``pygame.mixer.music``-loadable source: file path or WAV bytes."""
        path = self.music_path(track)
        if path is not None:
            return str(path)
        data = self.music_bytes(track)
        return io.BytesIO(data) if data else None


_ASSET_MANAGER: AssetManager | None = None


def get_assets() -> AssetManager:
    """Process-wide :class:`AssetManager` singleton (loads are cached)."""
    global _ASSET_MANAGER
    if _ASSET_MANAGER is None:
        _ASSET_MANAGER = AssetManager()
    return _ASSET_MANAGER


# --------------------------------------------------------------------------
# Audio service
# --------------------------------------------------------------------------
class AudioService:
    """Plays SFX and music on behalf of a game, honouring Settings volumes.

    All methods tolerate a missing/uninitialised mixer, which keeps the same
    code path working in CI, on servers without sound cards, and for players
    who mute everything in the settings.
    """

    def __init__(self, assets: AssetManager, settings: Settings | None = None) -> None:
        self.assets = assets
        self.settings = settings or Settings()
        self._current_track: str | Path | None = None
        self._music_paused = False

    def update_settings(self, settings: Settings) -> None:
        """Adopt new volumes (e.g. after the settings screen changes them).

        Volumes are clamped on the way in so no caller - and no hand-edited
        settings file - can push a mixer volume out of the legal 0..1 range.
        """
        self.settings = settings.clamp()
        if self._current_track is not None and not self._music_paused:
            self._apply_music_volume()

    # -- sound effects --------------------------------------------------
    def play(self, name: str, *, volume: float = 1.0) -> None:
        """Trigger a one-shot sound effect; silently does nothing if muted."""
        if not mixer_ready():
            return
        sound = self.assets.sound(name)
        if sound is None:
            return
        try:
            sound.set_volume(clamp(self.settings.sfx_volume * volume, 0.0, 1.0))
            sound.play()
        except pygame.error:
            pass  # channel exhaustion etc. - never let audio break a frame

    # -- music ----------------------------------------------------------
    @property
    def current_track(self) -> str | Path | None:
        """Name or path of the music track requested most recently."""
        return self._current_track

    def play_music(self, track: str | Path) -> None:
        """Start looping *track* (a name or a file path); no-op if already playing."""
        track = Path(track) if isinstance(track, Path) else track
        if not mixer_ready():
            return
        if self._current_track == track and pygame.mixer.music.get_busy():
            return
        # A Path is resolved directly; a bare name may fall back to a
        # procedurally generated loop when no file exists.
        source = str(track) if isinstance(track, Path) else self.assets.music_source(track)
        if source is None:
            return
        try:
            pygame.mixer.music.load(source)
            self._music_paused = False
            self._apply_music_volume()
            pygame.mixer.music.play(loops=-1, fade_ms=400)
            self._current_track = track
        except (pygame.error, OSError):
            self._current_track = None

    def stop_music(self) -> None:
        """Stop playback and forget the current track."""
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass
        self._current_track = None
        self._music_paused = False

    def pause_music(self) -> None:
        """Suspend playback (used by the shared pause feature)."""
        if self._current_track is None or self._music_paused:
            return
        try:
            pygame.mixer.music.pause()
            self._music_paused = True
        except pygame.error:
            pass

    def resume_music(self) -> None:
        """Resume playback after :meth:`pause_music`."""
        if not self._music_paused:
            return
        try:
            pygame.mixer.music.unpause()
            self._music_paused = False
        except pygame.error:
            pass

    def _apply_music_volume(self) -> None:
        try:
            pygame.mixer.music.set_volume(
                clamp(self.settings.music_volume, config.MIN_VOLUME, config.MAX_VOLUME)
            )
        except pygame.error:
            pass
