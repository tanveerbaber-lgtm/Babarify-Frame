"""Speech models (M9): which ones exist, where they live, download, verification, deletion.

Models are the faster-whisper conversions of OpenAI Whisper (MIT licence) published by
Systran on Hugging Face. Each is pinned to the revision checked during M9, and every file's
size and SHA-256 must match before the model is used ("installed"). A model is downloaded
only when the user asks for it; files go to a temporary folder first and are moved into
place only after they verify.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

LICENCE = "MIT (OpenAI Whisper weights; faster-whisper conversion by Systran)"


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class SpeechModel:
    name: str
    label: str
    repo: str
    revision: str
    files: tuple[ModelFile, ...]
    speed_x: float  # whole job (worker start, audio, recognition) vs. audio length, M9 test PC

    @property
    def speed_note(self) -> str:
        return f"about {self.speed_x:.0f} times faster than real time on the M9 test PC"

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def source(self) -> str:
        return f"https://huggingface.co/{self.repo}"


_TOKENIZER = ModelFile(
    "tokenizer.json", 2_203_239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"
)
_VOCABULARY = ModelFile(
    "vocabulary.txt", 459_861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"
)
MODELS: dict[str, SpeechModel] = {
    "tiny": SpeechModel(
        "tiny",
        "Tiny (fastest)",
        "Systran/faster-whisper-tiny",
        "d90ca5fe260221311c53c58e660288d3deb8d356",
        (
            ModelFile(
                "config.json", 2_249, "a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8"
            ),
            ModelFile(
                "model.bin", 75_538_270, "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1"
            ),
            _TOKENIZER,
            _VOCABULARY,
        ),
        10.0,
    ),
    "base": SpeechModel(
        "base",
        "Base (recommended)",
        "Systran/faster-whisper-base",
        "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
        (
            ModelFile(
                "config.json", 2_309, "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a"
            ),
            ModelFile(
                "model.bin", 145_217_532, "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"
            ),
            _TOKENIZER,
            _VOCABULARY,
        ),
        6.0,
    ),
}
DEFAULT_MODEL = "base"
# Spoken languages offered when generating subtitles (Whisper codes); "" = detect automatically.
SPEECH_LANGUAGES = {
    "": "Detect automatically",
    "en": "English", "ar": "Arabic", "zh": "Chinese", "nl": "Dutch", "fr": "French",
    "de": "German", "hi": "Hindi", "it": "Italian", "ja": "Japanese", "ko": "Korean",
    "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "es": "Spanish", "sv": "Swedish",
    "tr": "Turkish", "ur": "Urdu",
}  # fmt: skip


class ModelStatus(Enum):
    MISSING = "missing"
    INSTALLED = "installed"
    DAMAGED = "damaged"  # files present but sizes do not match (hashes are checked on download)


class ModelError(Exception):
    """A user-facing failure (download refused, hash mismatch, no network)."""


def models_dir() -> Path:
    """``%LOCALAPPDATA%\\Babarify\\Frame\\models`` (BABARIFY_MODELS_DIR overrides it)."""
    override = os.environ.get("BABARIFY_MODELS_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "models"


def model_path(name: str) -> Path:
    return models_dir() / f"faster-whisper-{MODELS[name].name}"


def status(name: str) -> ModelStatus:
    folder = model_path(name)
    if not folder.is_dir():
        return ModelStatus.MISSING
    for f in MODELS[name].files:
        path = folder / f.name
        if not path.is_file():
            return ModelStatus.MISSING if not any(folder.iterdir()) else ModelStatus.DAMAGED
        if path.stat().st_size != f.size:
            return ModelStatus.DAMAGED
    return ModelStatus.INSTALLED


def installed_models() -> list[str]:
    return [name for name in MODELS if status(name) is ModelStatus.INSTALLED]


def sha256_of(path: Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            if cancel is not None and cancel.is_set():
                raise ModelError("cancelled")
            digest.update(chunk)
    return digest.hexdigest()


def verify(name: str, folder: Path | None = None, cancel: threading.Event | None = None) -> None:
    """Raise ModelError unless every file has the expected size and SHA-256."""
    folder = folder or model_path(name)
    for f in MODELS[name].files:
        path = folder / f.name
        if not path.is_file() or path.stat().st_size != f.size:
            raise ModelError(f"{f.name} is missing or has the wrong size")
        if sha256_of(path, cancel) != f.sha256:
            raise ModelError(f"{f.name} does not match the expected checksum")


Fetch = Callable[[SpeechModel, ModelFile, Path], None]


def _hub_fetch(model: SpeechModel, file: ModelFile, folder: Path) -> None:
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from huggingface_hub import hf_hub_download

    hf_hub_download(model.repo, file.name, revision=model.revision, local_dir=folder)


def download(
    name: str,
    progress: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
    fetch: Fetch = _hub_fetch,
) -> None:
    """Download, verify and install a model. Only call after the user agreed to the download."""
    model = MODELS[name]
    target = model_path(name)
    staging = target.with_name(target.name + ".download")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        for f in model.files:
            if cancel is not None and cancel.is_set():
                raise ModelError("cancelled")
            if progress is not None:
                progress(f"Downloading {f.name} ({f.size / 1e6:.1f} MB)…")
            try:
                fetch(model, f, staging)
            except ModelError:
                raise
            except Exception as exc:  # network, server or disk errors from the hub client
                raise ModelError(f"could not download {f.name}: {exc}") from exc
        if progress is not None:
            progress("Checking the files…")
        verify(name, staging, cancel)
        for leftover in staging.iterdir():
            if leftover.name not in {f.name for f in model.files}:
                shutil.rmtree(leftover, ignore_errors=True) if leftover.is_dir() else leftover.unlink()
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def delete(name: str) -> None:
    shutil.rmtree(model_path(name), ignore_errors=True)
