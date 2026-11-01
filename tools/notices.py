"""Third-party notices for a release (M10).

Writes, into a release folder:
* ``THIRD_PARTY_NOTICES.txt``: every bundled component with version, licence and source.
* ``licenses/<component>/...``: the licence files shipped with each component.
Python packages are found as the dependency closure of RUNTIME_ROOTS (from installed metadata,
extras ignored); libVLC from the curated engine's ``plugins.json`` and its COPYING text.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

RUNTIME_ROOTS = ("PySide6-Essentials", "python-vlc", "huggingface-hub", "faster-whisper")
# Build and development tools are never bundled even if a root depends on them.
NOT_BUNDLED = {"pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile"}
VLC_SOURCE = "https://download.videolan.org/pub/videolan/vlc/3.0.24/vlc-3.0.24.tar.xz"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def closure(roots: tuple[str, ...] = RUNTIME_ROOTS) -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    todo = list(roots)
    while todo:
        name = _norm(todo.pop())
        if name in seen or name in NOT_BUNDLED:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen[name] = dist
        for req in dist.requires or []:
            if "extra ==" in req:
                continue
            marker = req.split(";", 1)[1] if ";" in req else ""
            if "sys_platform" in marker and "win32" not in marker and "!=" not in marker:
                continue
            todo.append(re.split(r"[\s;<>=!~\[(]", req, maxsplit=1)[0])
    return sorted(seen.values(), key=lambda d: _norm(d.metadata["Name"]))


def licence_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    text = (meta.get("License") or "").strip()
    if text and len(text) < 80 and "\n" not in text:
        return text
    classifiers = [
        c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")
    ]
    return "; ".join(classifiers) or (text.splitlines()[0][:80] if text else "see licence files")


def licence_files(dist: metadata.Distribution) -> list[Path]:
    out = []
    for file in dist.files or []:
        name = Path(str(file)).name.upper()
        if name.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")) or "/licenses/" in str(
            file
        ):
            path = Path(str(dist.locate_file(file)))
            if path.is_file():
                out.append(path)
    return out


def write(release: Path, vlc_dir: Path, version: str) -> list[dict[str, str]]:
    licenses = release / "licenses"
    shutil.rmtree(licenses, ignore_errors=True)
    licenses.mkdir(parents=True)
    rows: list[dict[str, str]] = []
    for dist in closure():
        name, ver = dist.metadata["Name"], dist.version
        folder = licenses / _norm(name)
        folder.mkdir()
        for i, path in enumerate(licence_files(dist)):
            shutil.copy2(path, folder / (path.name if i == 0 else f"{i}-{path.name}"))
        url = dist.metadata.get("Home-page") or next(
            (u.split(", ", 1)[-1] for u in dist.metadata.get_all("Project-URL") or []), ""
        )
        rows.append({"component": name, "version": ver, "licence": licence_of(dist), "source": url})
    python_licence = Path(sys.base_prefix) / "LICENSE.txt"
    if python_licence.is_file():
        (licenses / "python").mkdir()
        shutil.copy2(python_licence, licenses / "python" / "LICENSE.txt")
    rows.insert(0, {"component": "Python", "version": sys.version.split()[0], "licence": "PSF-2.0",
                    "source": "https://www.python.org/downloads/source/"})  # fmt: skip
    (licenses / "libvlc").mkdir()
    for text in ("COPYING.txt", "AUTHORS.txt", "THANKS.txt"):
        if (vlc_dir / text).is_file():
            shutil.copy2(vlc_dir / text, licenses / "libvlc" / text)
    plugins = json.loads((vlc_dir / "plugins.json").read_text(encoding="utf-8"))
    shipped = [p for p in plugins if p["shipped"] == "yes"]
    vlc_row = {
        "component": "libVLC (VideoLAN): core libraries and plugins",
        "version": "3.0.24",
        "licence": "LGPL-2.1-or-later and GPL-2.0-or-later (per plugin, below)",
        "source": VLC_SOURCE,
    }
    rows.insert(1, vlc_row)

    lines = [
        f"Babarify Frame {version} — third-party notices",
        "=" * 60,
        "",
        "Babarify Frame is free software: you can redistribute it and/or modify it under the terms",
        "of the GNU General Public License as published by the Free Software Foundation, either",
        "version 3 of the License, or (at your option) any later version (see LICENSE.txt). It is",
        "distributed WITHOUT ANY WARRANTY.",
        "",
        "It bundles the components below, each under its own licence (texts in licenses\\). Qt and",
        "PySide6 are used under the LGPL v3 as separate, replaceable libraries (_internal\\PySide6).",
        "",
        "Source code: the corresponding source for this release of Babarify Frame is published with",
        f"the release (BabarifyFrame-{version}-source.zip). Sources of the bundled components are",
        "listed below; on request the maintainer provides the exact sources used for this build, for",
        "at least three years after the last distribution of this version (GPL v3 section 6).",
        "",
        f"{'Component':44} {'Version':12} Licence",
        f"{'-' * 44} {'-' * 12} {'-' * 30}",
    ]
    for row in rows:
        lines.append(f"{row['component'][:44]:44} {row['version'][:12]:12} {row['licence']}")
        if row["source"]:
            lines.append(f"{'':57}source: {row['source']}")
    lines += [
        "",
        "Speech models (downloaded only if you choose to, M9): OpenAI Whisper weights converted by",
        "Systran (faster-whisper-tiny, faster-whisper-base), MIT licence, from huggingface.co.",
        "",
        f"libVLC plugins shipped ({len(shipped)} of {len(plugins)}; the licence each plugin declares for",
        "its own code; libraries linked into plugins are listed in licenses\\libvlc\\COPYING.txt):",
    ]
    for p in shipped:
        short = (
            "GPL-2.0-or-later"
            if "General Public License, version 2" in p["licence"] and "Lesser" not in p["licence"]
            else "LGPL-2.1-or-later"
        )
        lines.append(f"  {p['folder']}/{p['plugin']}: {short}")
    (release / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    for row in closure():
        print(f"{row.metadata['Name']:28} {row.version:12} {licence_of(row)}")
