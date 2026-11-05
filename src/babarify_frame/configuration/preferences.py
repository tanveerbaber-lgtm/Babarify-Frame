"""Typed UI preferences persisted as JSON in the user's local app-data folder.

Design rules:
* Local only. Nothing here is uploaded; the file holds no media paths or history
  (playback history is a separate, user-controlled feature in M6).
* Never trust the file: unknown keys are ignored, wrong types and out-of-range values
  fall back to defaults or are clamped, and a corrupt file is moved aside instead of
  crashing start-up.
* Writes are atomic (temp file + replace) so a crash cannot leave a half-written file.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from babarify_frame.ai.models import DEFAULT_MODEL, MODELS, SPEECH_LANGUAGES
from babarify_frame.core.enhancements import (
    MAX_PROFILES,
    EnhancementProfile,
    EqualizerSettings,
    PictureSettings,
)
from babarify_frame.core.models import SubtitleStyle
from babarify_frame.core.music import RepeatMode, VisualStyle
from babarify_frame.core.themes import DEFAULT_THEME, THEMES

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SEEK_STEPS_S = (5, 10, 15, 30, 60)
PLAYBACK_RATES = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
LIBRARY_SORTS = ("name", "date_added", "recently_played", "duration", "size")
# Track languages offered in Settings: ISO 639-2 codes as engines report them. "" = no preference.
LANGUAGES = {
    "": "No preference",
    "ara": "Arabic",
    "chi": "Chinese",
    "dut": "Dutch",
    "eng": "English",
    "fre": "French",
    "ger": "German",
    "hin": "Hindi",
    "ita": "Italian",
    "jpn": "Japanese",
    "kor": "Korean",
    "pol": "Polish",
    "por": "Portuguese",
    "rus": "Russian",
    "spa": "Spanish",
    "swe": "Swedish",
    "tur": "Turkish",
    "urd": "Urdu",
}
# Containers use either the bibliographic or the terminology ISO 639-2 code (fre/fra, ger/deu ...).
LANGUAGE_ALIASES = {
    "chi": {"zho", "zh"},
    "dut": {"nld", "nl"},
    "fre": {"fra", "fr"},
    "ger": {"deu", "de"},
    "eng": {"en"},
    "spa": {"es"},
    "ita": {"it"},
    "jpn": {"ja"},
    "kor": {"ko"},
    "por": {"pt"},
    "rus": {"ru"},
    "ara": {"ar"},
    "hin": {"hi"},
    "pol": {"pl"},
    "swe": {"sv"},
    "tur": {"tr"},
    "urd": {"ur"},
}


def language_matches(preferred: str, track_language: str | None) -> bool:
    if not preferred or not track_language:
        return False
    lang = track_language.strip().lower()
    return lang == preferred or lang in LANGUAGE_ALIASES.get(preferred, set())


@dataclass(frozen=True)
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int
    maximized: bool = False


@dataclass(frozen=True)
class Preferences:
    volume: int = 80  # 1..100
    muted: bool = False
    remember_volume: bool = True
    seek_step_s: int = 10  # one of SEEK_STEPS_S
    controls_hide_delay_ms: int = 3000  # fullscreen auto-hide, 1000..10000 (whole seconds in the UI)
    start_fullscreen: bool = False
    hardware_decoding: bool = True  # Automatic: use the GPU when the engine confirms support
    # Audio and subtitles (M5)
    subtitles_auto: bool = False  # select a subtitle track when a file opens without one
    preferred_audio_language: str = ""  # a LANGUAGES key
    preferred_subtitle_language: str = ""
    subtitle_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    # Library and history (M6)
    remember_history: bool = True  # local only; Settings → Privacy can clear it
    resume_playback: bool = True
    library_sort: str = "name"  # a SortOrder value
    # Picture and sound (M7)
    picture: PictureSettings = field(default_factory=PictureSettings)
    equalizer: EqualizerSettings = field(default_factory=EqualizerSettings)
    profiles: tuple[EnhancementProfile, ...] = ()
    allow_volume_boost: bool = False  # volume above 100 % (up to 200 %); never remembered
    # Advanced media (M8)
    seek_previews: bool = True  # pictures when hovering over the seek bar (local video files)
    # Music
    repeat_mode: str = "off"  # a RepeatMode value
    visual_style: str = "auto"  # a VisualStyle value
    colour_theme: str = DEFAULT_THEME  # a THEMES key
    show_status_bar: bool = False  # the line of technical details along the bottom of the window
    # Local AI (M9): off until the user switches it on; nothing is uploaded
    ai_enabled: bool = False
    ai_model: str = "base"  # an ai.models.MODELS key
    ai_language: str = ""  # an ai.models.SPEECH_LANGUAGES key; "" = detect
    window: WindowGeometry | None = field(default=None)

    @classmethod
    def from_dict(cls, data: Any) -> Preferences:
        """Build preferences from untrusted data; anything invalid falls back to the default."""
        if not isinstance(data, dict):
            return cls()
        default = cls()
        values: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data or f.name in (
                "window",
                "subtitle_style",
                "picture",
                "equalizer",
                "profiles",
            ):
                continue
            raw = data[f.name]
            current = getattr(default, f.name)
            if isinstance(current, bool):
                if isinstance(raw, bool):
                    values[f.name] = raw
            elif (
                isinstance(current, int)
                and isinstance(raw, int | float)
                and not isinstance(raw, bool)
                and math.isfinite(raw)
            ):
                values[f.name] = int(raw)
            elif isinstance(current, str) and isinstance(raw, str):
                values[f.name] = raw
        prefs = replace(default, **values)
        style = SubtitleStyle.from_dict(data.get("subtitle_style"))
        raw_profiles = data.get("profiles")
        profiles = tuple(
            p
            for p in (
                EnhancementProfile.from_dict(item)
                for item in (raw_profiles if isinstance(raw_profiles, list) else [])
            )
            if p is not None
        )
        return replace(
            prefs,
            window=_geometry(data.get("window")),
            subtitle_style=style,
            picture=PictureSettings.from_dict(data.get("picture")),
            equalizer=EqualizerSettings.from_dict(data.get("equalizer")),
            profiles=profiles,
        ).normalized()

    def normalized(self) -> Preferences:
        return replace(
            self,
            volume=max(1, min(100, self.volume)),
            seek_step_s=self.seek_step_s if self.seek_step_s in SEEK_STEPS_S else 10,
            controls_hide_delay_ms=max(1000, min(10_000, self.controls_hide_delay_ms)),
            preferred_audio_language=_language(self.preferred_audio_language),
            preferred_subtitle_language=_language(self.preferred_subtitle_language),
            library_sort=self.library_sort if self.library_sort in LIBRARY_SORTS else "name",
            repeat_mode=self.repeat_mode if self.repeat_mode in set(RepeatMode) else "off",
            visual_style=self.visual_style if self.visual_style in set(VisualStyle) else "auto",
            colour_theme=self.colour_theme if self.colour_theme in THEMES else DEFAULT_THEME,
            ai_model=self.ai_model if self.ai_model in MODELS else DEFAULT_MODEL,
            ai_language=self.ai_language if self.ai_language in SPEECH_LANGUAGES else "",
            picture=self.picture.normalized(),
            equalizer=self.equalizer.normalized(),
            profiles=_unique_profiles(self.profiles),
            subtitle_style=self.subtitle_style.normalized(),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["subtitle_style"] = self.subtitle_style.to_dict()
        data["picture"] = self.picture.to_dict()
        data["equalizer"] = self.equalizer.to_dict()
        data["profiles"] = [p.to_dict() for p in self.profiles]
        data["schema"] = SCHEMA_VERSION
        return data


def _unique_profiles(profiles: tuple[EnhancementProfile, ...]) -> tuple[EnhancementProfile, ...]:
    """Last profile with a given name wins (case-insensitive); at most MAX_PROFILES."""
    by_name: dict[str, EnhancementProfile] = {}
    for profile in profiles:
        by_name.pop(profile.name.casefold(), None)  # a re-saved profile counts as the newest
        by_name[profile.name.casefold()] = profile
    return tuple(by_name.values())[-MAX_PROFILES:]


def _language(code: str) -> str:
    return code if code in LANGUAGES else ""


def _geometry(raw: Any) -> WindowGeometry | None:
    if not isinstance(raw, dict):
        return None
    try:
        geo = WindowGeometry(
            x=int(raw["x"]),
            y=int(raw["y"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
            maximized=bool(raw.get("maximized", False)),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not (200 <= geo.width <= 20_000 and 150 <= geo.height <= 20_000):
        return None
    return geo


def default_settings_path() -> Path:
    base = os.environ.get("BABARIFY_CONFIG_DIR") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "settings.json"


class PreferencesStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> Preferences:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Preferences()
        except OSError as exc:
            log.warning("could not read preferences %s: %s", self.path, exc)
            return Preferences()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            self._quarantine()
            return Preferences()
        return Preferences.from_dict(data)

    def save(self, prefs: Preferences) -> bool:
        """Write atomically. Returns False (and logs) instead of raising on failure."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(prefs.normalized().to_dict(), handle, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError as exc:
            log.warning("could not save preferences %s: %s", self.path, exc)
            return False

    def _quarantine(self) -> None:
        """Keep a corrupt file for inspection and start from defaults."""
        target = self.path.with_suffix(".corrupt.json")
        try:
            os.replace(self.path, target)
            log.warning("corrupt preferences moved to %s", target)
        except OSError as exc:
            log.warning("corrupt preferences %s could not be moved: %s", self.path, exc)
