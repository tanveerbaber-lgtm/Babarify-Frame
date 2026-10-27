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

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SEEK_STEPS_S = (5, 10, 15, 30, 60)
PLAYBACK_RATES = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)


@dataclass(frozen=True)
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int
    maximized: bool = False


@dataclass(frozen=True)
class Preferences:
    volume: int = 80  # 0..100
    muted: bool = False
    remember_volume: bool = True
    seek_step_s: int = 10  # one of SEEK_STEPS_S
    controls_hide_delay_ms: int = 3000  # fullscreen auto-hide, 1000..10000 (whole seconds in the UI)
    start_fullscreen: bool = False
    window: WindowGeometry | None = field(default=None)

    @classmethod
    def from_dict(cls, data: Any) -> Preferences:
        """Build preferences from untrusted data; anything invalid falls back to the default."""
        if not isinstance(data, dict):
            return cls()
        default = cls()
        values: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data or f.name == "window":
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
        prefs = replace(default, **values)
        return replace(prefs, window=_geometry(data.get("window"))).normalized()

    def normalized(self) -> Preferences:
        return replace(
            self,
            volume=max(0, min(100, self.volume)),
            seek_step_s=self.seek_step_s if self.seek_step_s in SEEK_STEPS_S else 10,
            controls_hide_delay_ms=max(1000, min(10_000, self.controls_hide_delay_ms)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema"] = SCHEMA_VERSION
        return data


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
