"""Build a signed Android release (M13): per-architecture APKs, source archive and checksums.

The key is never stored in the repository. Passwords come from the environment:
BABARIFY_KEYSTORE, BABARIFY_KEY_ALIAS, BABARIFY_KEYSTORE_PASSWORD, BABARIFY_KEY_PASSWORD.
Refuses a dirty tree unless --allow-dirty, so a release matches a commit.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "android" / "player"
APKS = PROJECT / "app" / "build" / "outputs" / "apk" / "release"
PHONE_ABIS = ("arm64-v8a", "armeabi-v7a")
BUILD_TOOLS = Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "build-tools" / "37.0.0"


def version() -> str:
    text = (PROJECT / "app" / "build.gradle.kts").read_text("utf-8")
    match = re.search(r'versionName = "([^"]+)"', text)
    if match is None:
        raise SystemExit("versionName not found")
    return match.group(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signing_environment() -> dict[str, str]:
    needed = {
        "BABARIFY_KEYSTORE": "babarify.keystore",
        "BABARIFY_KEY_ALIAS": "babarify.key.alias",
        "BABARIFY_KEYSTORE_PASSWORD": "babarify.keystore.password",
        "BABARIFY_KEY_PASSWORD": "babarify.key.password",
    }
    missing = [name for name in needed if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing signing settings: {', '.join(missing)}")
    env = dict(os.environ)
    for name, prop in needed.items():
        env[f"ORG_GRADLE_PROJECT_{prop}"] = os.environ[name]
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--output", type=Path, help="default: release/android-<version>")
    args = parser.parse_args()

    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    if dirty and not args.allow_dirty:
        raise SystemExit("the working tree has uncommitted changes; a release must match a commit")

    env = signing_environment()
    name = version()
    output = args.output or ROOT / "release" / f"android-{name}"
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)

    gradle = PROJECT / ("gradlew.bat" if os.name == "nt" else "gradlew")
    subprocess.run(
        [str(gradle), "-p", str(PROJECT), "clean", "testDebugUnitTest", "lintRelease", "assembleRelease"],
        check=True,
        env=env,
    )

    produced: list[Path] = []
    for abi in PHONE_ABIS:
        built = APKS / f"app-{abi}-release.apk"
        subprocess.run(
            [str(BUILD_TOOLS / "apksigner.bat"), "verify", "--print-certs", str(built)], check=True
        )
        target = output / f"BabarifyFrame-{name}-{abi}.apk"
        shutil.copy2(built, target)
        produced.append(target)

    source = output / f"BabarifyFrame-{name}-source.zip"
    subprocess.run(["git", "archive", "--format=zip", "-o", str(source), "HEAD"], cwd=ROOT, check=True)
    produced.append(source)

    sums = "".join(f"{sha256(path)}  {path.name}\n" for path in produced)
    (output / "SHA256SUMS.txt").write_text(sums, "utf-8")
    print(sums)
    print(f"written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
