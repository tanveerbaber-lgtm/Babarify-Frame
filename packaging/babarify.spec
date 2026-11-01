# PyInstaller spec for Babarify Frame (M10). Build with tools/build_release.py, not directly.
# Two folders:
#   Babarify Frame\           the player (windowed; no speech engine inside)
#   ai\babarify-ai-worker.exe  the local transcription worker (console, started hidden; M9),
#                             an optional installer component (about 240 MB)
# libVLC is not collected here: build_release.py copies the curated engine to engines/vlc.
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ICON = str(SRC / "babarify_frame" / "resources" / "icons" / "babarify-frame.ico")
VERSION_FILE = str(ROOT / "build" / "version_info.txt")
COMMON_EXCLUDES = [
    "tkinter", "unittest", "pydoc", "pytest", "mypy", "ruff", "IPython", "matplotlib",
    "mpv",  # the opt-in development engine is not shipped
    "PyInstaller",
]  # fmt: skip

app = Analysis(
    [str(ROOT / "packaging" / "entry_app.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "babarify_frame" / "resources"), "babarify_frame/resources")],
    hiddenimports=["vlc", "huggingface_hub"],  # vlc is imported lazily; the hub for model download
    excludes=COMMON_EXCLUDES + ["faster_whisper", "ctranslate2", "onnxruntime", "av", "numpy"],
)
# Qt parts a widget-based, English-only player never loads (M10 size review).
QT_UNUSED = ("opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "\\translations\\",
             "qpdf.dll")  # fmt: skip
app.binaries = [b for b in app.binaries if not any(u in b[0].lower() for u in QT_UNUSED)]
app.datas = [d for d in app.datas if not any(u in d[0].lower() for u in QT_UNUSED)]

worker = Analysis(
    [str(ROOT / "packaging" / "entry_worker.py")],
    pathex=[str(SRC)],
    datas=collect_data_files("faster_whisper"),  # the voice-activity model
    hiddenimports=["vlc"],
    excludes=COMMON_EXCLUDES + ["PySide6", "shiboken6"],
)
app_exe = EXE(
    PYZ(app.pure),
    app.scripts,
    [],
    exclude_binaries=True,
    name="Babarify Frame",
    icon=ICON,
    version=VERSION_FILE,
    console=False,
    upx=False,
)
worker_exe = EXE(
    PYZ(worker.pure),
    worker.scripts,
    [],
    exclude_binaries=True,
    name="babarify-ai-worker",
    icon=ICON,
    version=VERSION_FILE,
    console=True,
    upx=False,
)
COLLECT(app_exe, app.binaries, app.datas, name="Babarify Frame", upx=False)
COLLECT(worker_exe, worker.binaries, worker.datas, name="ai", upx=False)
