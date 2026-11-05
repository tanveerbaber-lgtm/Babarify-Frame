"""Picture and sound settings (M7). Immutable, validated, safe to build from untrusted data.

Units match libVLC's adjust filter and equalizer, which the selected engine maps directly:
brightness/contrast/gamma 1.0 = unchanged, saturation 1.0 = unchanged (0 = grey), hue in
degrees; equalizer amplification in dB per band (-20..+20) plus a preamp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

# Aspect and crop choices offered in the UI ("" = as the file says / no crop).
ASPECT_RATIOS: tuple[str, ...] = ("", "16:9", "4:3", "16:10", "21:9", "2.35:1", "1:1", "5:4")
# Zoom: 0 = fit the window; otherwise video pixels per screen pixel.
ZOOM_LEVELS: tuple[float, ...] = (0.0, 0.5, 1.0, 2.0)
EQ_BAND_MIN_DB, EQ_BAND_MAX_DB = -20.0, 20.0
EQ_BAND_COUNT = 10
BASS_MAX_DB = 12.0
BASS_WEIGHTS = (1.0, 0.8, 0.5, 0.2)  # from the lowest band up
MAX_PROFILES = 20
MAX_PROFILE_NAME = 60


def _number(raw: Any, default: float, low: float, high: float) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
        return default
    return max(low, min(high, float(raw)))


class VideoTransform(Enum):
    NONE = "none"
    ROTATE_90 = "90"
    ROTATE_180 = "180"
    ROTATE_270 = "270"
    FLIP_HORIZONTAL = "hflip"
    FLIP_VERTICAL = "vflip"


TRANSFORM_LABELS = {
    VideoTransform.NONE: "None",
    VideoTransform.ROTATE_90: "Rotate 90° clockwise",
    VideoTransform.ROTATE_180: "Rotate 180°",
    VideoTransform.ROTATE_270: "Rotate 90° anticlockwise",
    VideoTransform.FLIP_HORIZONTAL: "Mirror (flip horizontally)",
    VideoTransform.FLIP_VERTICAL: "Flip vertically",
}

# name: (default, minimum, maximum)
PICTURE_RANGES: dict[str, tuple[float, float, float]] = {
    "brightness": (1.0, 0.0, 2.0),
    "contrast": (1.0, 0.0, 2.0),
    "saturation": (1.0, 0.0, 3.0),
    "hue": (0.0, -180.0, 180.0),
    "gamma": (1.0, 0.5, 2.0),
}


@dataclass(frozen=True)
class PictureSettings:
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    hue: float = 0.0
    gamma: float = 1.0

    @property
    def is_default(self) -> bool:
        return self == PictureSettings()

    def normalized(self) -> PictureSettings:
        values = {
            name: _number(getattr(self, name), default, low, high)
            for name, (default, low, high) in PICTURE_RANGES.items()
        }
        return PictureSettings(**values)

    def to_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in PICTURE_RANGES}

    @classmethod
    def from_dict(cls, data: Any) -> PictureSettings:
        if not isinstance(data, dict):
            return cls()
        return cls(
            **{
                name: _number(data.get(name, default), default, low, high)
                for name, (default, low, high) in PICTURE_RANGES.items()
            }
        )


@dataclass(frozen=True)
class EqualizerSettings:
    enabled: bool = False
    preset: str = ""  # name of the engine preset the values came from, "" = custom
    preamp_db: float = 0.0
    bands_db: tuple[float, ...] = field(default=(0.0,) * EQ_BAND_COUNT)
    bass_pct: int = 0  # where the bass dial stands; its effect is already in bands_db

    def normalized(self) -> EqualizerSettings:
        bands = tuple(self.bands_db[:EQ_BAND_COUNT]) + (0.0,) * max(0, EQ_BAND_COUNT - len(self.bands_db))
        return replace(
            self,
            preset=self.preset[:60],
            preamp_db=_number(self.preamp_db, 0.0, EQ_BAND_MIN_DB, EQ_BAND_MAX_DB),
            bands_db=tuple(_number(b, 0.0, EQ_BAND_MIN_DB, EQ_BAND_MAX_DB) for b in bands),
            bass_pct=round(_number(self.bass_pct, 0.0, 0.0, 100.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "preset": self.preset,
            "preamp_db": self.preamp_db,
            "bands_db": list(self.bands_db),
            "bass_pct": self.bass_pct,
        }

    @classmethod
    def from_dict(cls, data: Any) -> EqualizerSettings:
        if not isinstance(data, dict):
            return cls()
        bands = data.get("bands_db")
        return cls(
            enabled=data.get("enabled") is True,
            preset=preset if isinstance(preset := data.get("preset"), str) else "",
            preamp_db=_number(data.get("preamp_db"), 0.0, EQ_BAND_MIN_DB, EQ_BAND_MAX_DB),
            bands_db=tuple(bands) if isinstance(bands, list) else (0.0,) * EQ_BAND_COUNT,
            bass_pct=round(_number(data.get("bass_pct"), 0.0, 0.0, 100.0)),
        ).normalized()


def with_bass(bands_db: tuple[float, ...], old_pct: int, new_pct: int) -> tuple[float, ...]:
    """The bass dial turns up the lowest bands by the difference it moved, which keeps changes made to
    those bands by hand. Rounded from the dial's position, so turning it back returns them exactly."""

    def lift(pct: int, weight: float) -> int:
        return round(pct / 100 * BASS_MAX_DB * weight)

    moved = []
    for band, value in enumerate(bands_db):
        weight = BASS_WEIGHTS[band] if band < len(BASS_WEIGHTS) else 0.0
        shifted = value + lift(new_pct, weight) - lift(old_pct, weight)
        moved.append(max(EQ_BAND_MIN_DB, min(EQ_BAND_MAX_DB, float(shifted))))
    return tuple(moved)


@dataclass(frozen=True)
class EnhancementProfile:
    """A named, saved combination of picture and sound settings."""

    name: str
    picture: PictureSettings = field(default_factory=PictureSettings)
    equalizer: EqualizerSettings = field(default_factory=EqualizerSettings)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "picture": self.picture.to_dict(), "equalizer": self.equalizer.to_dict()}

    @classmethod
    def from_dict(cls, data: Any) -> EnhancementProfile | None:
        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            return None
        name = " ".join(data["name"].split())[:MAX_PROFILE_NAME]
        if not name:
            return None
        return cls(
            name,
            PictureSettings.from_dict(data.get("picture")),
            EqualizerSettings.from_dict(data.get("equalizer")),
        )


def aspect_to_engine(ratio: str) -> str | None:
    """'2.35:1' -> '235:100' (libVLC wants integers); '' -> None (file default)."""
    if not ratio:
        return None
    width, _, height = ratio.partition(":")
    if "." in width:
        scale = 10 ** len(width.split(".")[1])
        return f"{round(float(width) * scale)}:{round(float(height) * scale)}"
    return ratio
