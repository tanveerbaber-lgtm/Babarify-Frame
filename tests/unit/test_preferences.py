import json
from pathlib import Path

import pytest

from babarify_frame.configuration import Preferences, PreferencesStore, WindowGeometry
from babarify_frame.configuration.preferences import SCHEMA_VERSION, default_settings_path


def test_defaults() -> None:
    p = Preferences()
    assert (p.volume, p.muted, p.seek_step_s, p.controls_hide_delay_ms) == (80, False, 10, 3000)
    assert p.window is None


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert PreferencesStore(tmp_path / "none.json").load() == Preferences()


def test_round_trip(tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "sub" / "settings.json")
    prefs = Preferences(volume=35, muted=True, seek_step_s=30, window=WindowGeometry(10, 20, 900, 600, True))
    assert store.save(prefs)
    assert store.load() == prefs
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["schema"] == SCHEMA_VERSION


def test_save_leaves_no_temp_files(tmp_path: Path) -> None:
    store = PreferencesStore(tmp_path / "settings.json")
    store.save(Preferences())
    store.save(Preferences(volume=10))
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"volume": 250}, {"volume": 100}),
        ({"volume": -5}, {"volume": 1}),
        ({"volume": 0}, {"volume": 1}),
        ({"volume": "loud"}, {"volume": 80}),
        ({"volume": True}, {"volume": 80}),
        ({"volume": float("nan")}, {"volume": 80}),
        ({"muted": "yes"}, {"muted": False}),
        ({"seek_step_s": 7}, {"seek_step_s": 10}),
        ({"controls_hide_delay_ms": 50}, {"controls_hide_delay_ms": 1000}),
        ({"controls_hide_delay_ms": 10**9}, {"controls_hide_delay_ms": 10_000}),
        ({"unknown_key": 1, "volume": 40}, {"volume": 40}),
    ],
)
def test_untrusted_values_are_clamped_or_defaulted(
    raw: dict[str, object], expected: dict[str, object]
) -> None:
    prefs = Preferences.from_dict(raw)
    for key, value in expected.items():
        assert getattr(prefs, key) == value


@pytest.mark.parametrize(
    "window",
    [
        "not a dict",
        {"x": 0, "y": 0, "width": 50, "height": 50},
        {"x": 0, "y": 0},
        {"x": "a", "y": 0, "width": 800, "height": 600},
    ],
)
def test_invalid_window_geometry_is_dropped(window: object) -> None:
    assert Preferences.from_dict({"window": window}).window is None


def test_non_dict_json_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert PreferencesStore(path).load() == Preferences()


def test_corrupt_file_is_quarantined(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ not json", encoding="utf-8")
    assert PreferencesStore(path).load() == Preferences()
    assert not path.exists()
    assert (tmp_path / "settings.corrupt.json").read_text(encoding="utf-8") == "{ not json"


def test_save_failure_returns_false(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert PreferencesStore(blocker / "settings.json").save(Preferences()) is False


def test_default_path_respects_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BABARIFY_CONFIG_DIR", str(tmp_path))
    assert default_settings_path() == tmp_path / "Babarify" / "Frame" / "settings.json"
