"""M7 models and contract: picture/equalizer validation, geometry, rotation, frame step, snapshot."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from babarify_frame.configuration.preferences import Preferences, PreferencesStore
from babarify_frame.core.enhancements import (
    MAX_PROFILES,
    EnhancementProfile,
    EqualizerSettings,
    PictureSettings,
    VideoTransform,
    aspect_to_engine,
)
from babarify_frame.core.errors import ErrorCode, PlaybackError
from babarify_frame.core.models import EngineCapabilities
from babarify_frame.core.models import PlaybackState as S
from babarify_frame.playback.adapters.mock import MockEngine


class LimitedEngine(MockEngine):
    """Mock that supports only brightness and nothing else from M7."""

    def get_capabilities(self) -> EngineCapabilities:
        return replace(
            super().get_capabilities(),
            picture_adjustments=frozenset({"brightness"}),
            supports_aspect_ratio=False,
            supports_crop=False,
            supports_zoom=False,
            rotation="restart",
            supports_equalizer=False,
            supports_frame_step=False,
            supports_snapshot=False,
        )


@pytest.fixture
def limited() -> MockEngine:
    eng = LimitedEngine()
    eng.initialize()
    eng.open_media("mock://clip")
    return eng


# -------------------------------------------------------------------- models
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"brightness": 5}, PictureSettings(brightness=2.0)),
        ({"saturation": -1}, PictureSettings(saturation=0.0)),
        ({"hue": 999}, PictureSettings(hue=180.0)),
        ({"gamma": float("nan")}, PictureSettings()),
        ({"contrast": True}, PictureSettings()),
        ({"contrast": "1.5"}, PictureSettings()),
        ("not a dict", PictureSettings()),
    ],
)
def test_picture_from_untrusted_data(raw: object, expected: PictureSettings) -> None:
    assert PictureSettings.from_dict(raw) == expected


def test_picture_round_trip_and_default() -> None:
    picture = PictureSettings(1.2, 0.8, 1.5, -30.0, 1.1)
    assert PictureSettings.from_dict(picture.to_dict()) == picture
    assert PictureSettings().is_default and not picture.is_default


def test_equalizer_from_untrusted_data() -> None:
    eq = EqualizerSettings.from_dict({"enabled": "yes", "preamp_db": 99, "bands_db": [50, -50, "x", 3]})
    assert eq.enabled is False  # only a real true enables it
    assert eq.preamp_db == 20.0
    assert eq.bands_db[:4] == (20.0, -20.0, 0.0, 3.0) and len(eq.bands_db) == 10
    good = EqualizerSettings(True, "Rock", -3.0, (1.0,) * 10)
    assert EqualizerSettings.from_dict(good.to_dict()) == good


def test_profiles_from_untrusted_data() -> None:
    assert EnhancementProfile.from_dict({"name": "   "}) is None
    assert EnhancementProfile.from_dict({"name": 3}) is None
    profile = EnhancementProfile.from_dict({"name": "  Night   mode ", "picture": {"brightness": 0.7}})
    assert profile is not None and profile.name == "Night mode" and profile.picture.brightness == 0.7


@pytest.mark.parametrize(
    ("ratio", "engine"), [("", None), ("16:9", "16:9"), ("2.35:1", "235:100"), ("4:3", "4:3")]
)
def test_aspect_ratio_for_engine(ratio: str, engine: str | None) -> None:
    assert aspect_to_engine(ratio) == engine


def test_preferences_keep_picture_eq_and_profiles(tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "settings.json")
    profiles = (
        *(EnhancementProfile(f"P{i}") for i in range(MAX_PROFILES + 3)),
        EnhancementProfile("p0", PictureSettings(brightness=1.5)),  # same name, other case: replaces
    )
    prefs = Preferences(
        picture=PictureSettings(contrast=1.3),
        equalizer=EqualizerSettings(True, "Pop", 1.0, (2.0,) * 10),
        profiles=profiles,
        allow_volume_boost=True,
    )
    assert store.save(prefs)
    loaded = store.load()
    assert loaded.picture.contrast == 1.3
    assert loaded.equalizer.preset == "Pop" and loaded.equalizer.enabled
    assert len(loaded.profiles) == MAX_PROFILES
    assert loaded.profiles[-1].name == "p0" and loaded.profiles[-1].picture.brightness == 1.5
    assert loaded.allow_volume_boost


# ------------------------------------------------------------------ contract
def test_mock_applies_everything(engine: MockEngine, tmp_path: Path) -> None:
    engine.open_media("mock://clip")
    engine.set_picture(PictureSettings(brightness=1.4, hue=400))
    assert engine.picture.brightness == 1.4 and engine.picture.hue == 180.0  # normalized
    engine.set_video_geometry("4:3", "16:9", 2.0)
    assert engine.geometry == ("4:3", "16:9", 2.0)
    engine.set_equalizer(EqualizerSettings(True, "", 0.0, (30.0,) * 10))
    assert engine.equalizer.bands_db[0] == 20.0
    engine.set_rotation(VideoTransform.ROTATE_90)
    assert engine.transform is VideoTransform.ROTATE_90
    assert engine.equalizer_preset("Rock").bands_db[0] == 4.0


def test_invalid_geometry_values_are_rejected(engine: MockEngine) -> None:
    engine.open_media("mock://clip")
    for args in (("3:2", "", 0.0), ("", "7:5", 0.0), ("", "", 3.0)):
        with pytest.raises(PlaybackError) as exc:
            engine.set_video_geometry(*args)
        assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_unsupported_controls_are_refused_not_ignored(limited: MockEngine) -> None:
    limited.set_picture(PictureSettings(brightness=1.3))  # supported
    for call in (
        lambda: limited.set_picture(PictureSettings(gamma=1.5)),
        lambda: limited.set_video_geometry("4:3", "", 0.0),
        lambda: limited.set_video_geometry("", "4:3", 0.0),
        lambda: limited.set_video_geometry("", "", 2.0),
        lambda: limited.set_equalizer(EqualizerSettings(True)),
        lambda: limited.set_rotation(VideoTransform.ROTATE_90),  # "restart" engines refuse live changes
        lambda: limited.frame_step(),
        lambda: limited.take_snapshot("x.png"),
    ):
        with pytest.raises(PlaybackError) as exc:
            call()
        assert exc.value.code is ErrorCode.UNSUPPORTED
    limited.set_video_geometry("", "", 0.0)  # defaults are always accepted
    assert limited.state is S.PLAYING


def test_frame_step_pauses_and_advances(engine: MockEngine) -> None:
    engine.open_media("mock://clip?duration=10000")
    engine.frame_step()
    assert engine.state is S.PAUSED
    assert engine.get_playback_state().position_ms == 40
    with pytest.raises(PlaybackError) as exc:
        engine.frame_step(backward=True)  # the mock, like libVLC 3, cannot step back
    assert exc.value.code is ErrorCode.UNSUPPORTED


def test_frame_step_needs_media(engine: MockEngine) -> None:
    with pytest.raises(PlaybackError) as exc:
        engine.frame_step()
    assert exc.value.code is ErrorCode.INVALID_STATE


def test_snapshot_validation(engine: MockEngine, tmp_path: Path) -> None:
    engine.open_media("mock://clip")
    good = tmp_path / "shot.png"
    engine.take_snapshot(str(good))
    assert good.read_bytes().startswith(b"\x89PNG")
    for bad in (tmp_path / "shot.jpg", tmp_path / "missing" / "shot.png"):
        with pytest.raises(PlaybackError) as exc:
            engine.take_snapshot(str(bad))
        assert exc.value.code is ErrorCode.INVALID_ARGUMENT


def test_snapshot_refused_for_audio_only(engine: MockEngine, tmp_path: Path) -> None:
    engine.open_media("mock://clip")
    info = engine.get_media_info()
    assert info is not None
    engine._set_media_info(replace(info, video_codec=None, audio_codec="flac"))
    with pytest.raises(PlaybackError) as exc:
        engine.take_snapshot(str(tmp_path / "a.png"))
    assert exc.value.code is ErrorCode.UNSUPPORTED
