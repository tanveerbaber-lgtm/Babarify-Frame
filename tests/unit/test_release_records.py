"""M16: each release has a changelog entry, and the security check audits what ships."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _windows_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]


def test_the_windows_version_has_a_changelog_entry() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text("utf-8")
    assert f"## Windows {_windows_version()}" in changelog


def test_the_android_version_has_a_changelog_entry() -> None:
    gradle = (ROOT / "android" / "player" / "app" / "build.gradle.kts").read_text("utf-8")
    match = re.search(r'versionName = "([^"]+)"', gradle)
    assert match is not None
    assert f"## Android {match.group(1)}" in (ROOT / "CHANGELOG.md").read_text("utf-8")


def test_runtime_pins_match_the_windows_version_and_are_exact() -> None:
    lines = (ROOT / "requirements" / "windows-runtime.txt").read_text("utf-8").splitlines()
    assert lines[0] == f"# Babarify Frame {_windows_version()} for Windows"
    assert len(lines) > 10
    assert all(re.fullmatch(r"[A-Za-z0-9._-]+==[^=\s]+", line) for line in lines[1:])
