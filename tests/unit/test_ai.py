"""M9: cue building, SRT output, storage paths, model verification/download, transcript index."""

from __future__ import annotations

import hashlib
import itertools
import threading
from pathlib import Path

import pytest

import babarify_frame.ai.models as models
from babarify_frame.ai.models import ModelError, ModelFile, ModelStatus, SpeechModel
from babarify_frame.ai.subtitles import MACHINE_TAG, Cue, Word, build_cues, subtitle_path, to_srt
from babarify_frame.configuration.preferences import Preferences
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.ui.ai import is_machine_subtitle, worker_command


# ------------------------------------------------------------ cues and SRT
def words(text: str, start: int = 0, step: int = 300, gap_after: dict[int, int] | None = None) -> list[Word]:
    out, t = [], start
    for i, w in enumerate(text.split()):
        out.append(Word(t, t + step - 50, " " + w))
        t += step + (gap_after or {}).get(i, 0)
    return out


def test_cues_end_at_sentences_pauses_and_limits() -> None:
    cues = build_cues(words("The harbour lights came on one by one. Maria counted the boats and waited."))
    assert [c.text for c in cues] == [
        "The harbour lights came on one by one.",
        "Maria counted the boats and waited.",
    ]
    paused = build_cues(words("one two three four", gap_after={1: 2000}))
    assert [c.text for c in paused] == ["one two", "three four"]
    long = build_cues(words(" ".join(["word"] * 60)))
    assert all(len(c.text) <= 84 and c.end_ms - c.start_ms <= 7_000 for c in long) and len(long) > 2


def test_cues_never_overlap_and_have_a_minimum_length() -> None:
    cues = build_cues(
        [Word(0, 100, " Hi."), Word(150, 400, " There was a long story here."), Word(450, 600, " Ok")]
    )
    for a, b in itertools.pairwise(cues):
        assert a.end_ms <= b.start_ms
    assert all(c.end_ms > c.start_ms for c in cues)
    assert build_cues([]) == [] and build_cues([Word(0, 10, "   ")]) == []


def test_srt_format() -> None:
    srt = to_srt(
        [
            Cue(2_670, 6_270, "The harbor lights came on one by one as the fishing boats returned."),
            Cue(3_723_004, 3_724_000, "Late"),
        ]
    )
    assert srt.startswith(
        "1\n00:00:02,670 --> 00:00:06,270\n"
        "The harbor lights came on one by one as\nthe fishing boats returned.\n\n2\n"
    )
    assert "01:02:03,004 --> 01:02:04,000\nLate\n" in srt


def test_generated_subtitles_live_in_the_app_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BABARIFY_CONFIG_DIR", str(tmp_path / "cfg"))
    media = r"D:\Films\Harbour: Lights?.mkv"
    path = subtitle_path(media, "en")
    assert path.is_relative_to(tmp_path / "cfg") and path.name == f"Harbour_ Lights_.en.{MACHINE_TAG}.srt"
    assert subtitle_path(r"d:\films\HARBOUR: LIGHTS?.MKV", "en").parent == path.parent  # same file (path_key)
    assert subtitle_path(r"D:\Other\Harbour: Lights?.mkv", "en").parent != path.parent
    assert subtitle_path(media, "../../x").name.endswith(f".x.{MACHINE_TAG}.srt")  # language cannot escape
    assert is_machine_subtitle(str(path)) and not is_machine_subtitle(r"D:\Films\a.en.srt")


def test_ai_is_off_by_default_and_values_are_checked() -> None:
    prefs = Preferences()
    assert prefs.ai_enabled is False and prefs.ai_model == "base" and prefs.ai_language == ""
    data = {"ai_enabled": True, "ai_model": "huge", "ai_language": "xx"}
    loaded = Preferences.from_dict(data)
    assert loaded.ai_enabled is True and loaded.ai_model == "base" and loaded.ai_language == ""


def test_worker_command_uses_this_python_and_the_model_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BABARIFY_MODELS_DIR", str(tmp_path))
    cmd = worker_command("C:/a b.mkv", "tiny", "", tmp_path / "a.srt", tmp_path / "a.json")
    assert cmd[1:3] == ["-m", "babarify_frame.ai.worker"] and "C:/a b.mkv" in cmd
    assert cmd[cmd.index("--model-dir") + 1] == str(tmp_path / "faster-whisper-tiny")
    assert cmd[cmd.index("--language") + 1] == "auto"


# ------------------------------------------------------------ models
@pytest.fixture
def fake_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    monkeypatch.setenv("BABARIFY_MODELS_DIR", str(tmp_path / "models"))
    content = {"config.json": b"{}", "model.bin": b"weights" * 1000}
    files = tuple(ModelFile(n, len(b), hashlib.sha256(b).hexdigest()) for n, b in content.items())
    monkeypatch.setitem(models.MODELS, "tiny", SpeechModel("tiny", "Tiny", "x/y", "rev", files, 10.0))
    return content


def fetch_from(content: dict[str, bytes], corrupt: str = "") -> models.Fetch:
    def fetch(_model: SpeechModel, file: ModelFile, folder: Path) -> None:
        data = content[file.name]
        (folder / file.name).write_bytes(data + (b"!" if file.name == corrupt else b""))
        (folder / ".cache").mkdir(exist_ok=True)  # the hub client's own bookkeeping

    return fetch


def test_download_installs_only_verified_files(fake_model: dict[str, bytes]) -> None:
    assert models.status("tiny") is ModelStatus.MISSING
    messages: list[str] = []
    models.download("tiny", messages.append, fetch=fetch_from(fake_model))
    assert models.status("tiny") is ModelStatus.INSTALLED and models.installed_models() == ["tiny"]
    assert sorted(p.name for p in models.model_path("tiny").iterdir()) == ["config.json", "model.bin"]
    assert any("Checking" in m for m in messages)
    models.verify("tiny")
    models.delete("tiny")
    assert models.status("tiny") is ModelStatus.MISSING


def test_tampered_download_is_refused_and_nothing_is_installed(fake_model: dict[str, bytes]) -> None:
    with pytest.raises(ModelError, match="wrong size"):
        models.download("tiny", fetch=fetch_from(fake_model, corrupt="model.bin"))
    assert models.status("tiny") is ModelStatus.MISSING
    assert not models.model_path("tiny").with_name("faster-whisper-tiny.download").exists()


def test_same_size_but_different_content_is_refused(fake_model: dict[str, bytes]) -> None:
    def fetch(_model: SpeechModel, file: ModelFile, folder: Path) -> None:
        data = fake_model[file.name]
        (folder / file.name).write_bytes(data[::-1])  # same size, other bytes

    with pytest.raises(ModelError, match="checksum"):
        models.download("tiny", fetch=fetch)
    assert models.status("tiny") is ModelStatus.MISSING


def test_damaged_install_and_cancel(fake_model: dict[str, bytes]) -> None:
    models.download("tiny", fetch=fetch_from(fake_model))
    (models.model_path("tiny") / "model.bin").write_bytes(b"short")
    assert models.status("tiny") is ModelStatus.DAMAGED
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ModelError, match="cancelled"):
        models.download("tiny", cancel=cancel, fetch=fetch_from(fake_model))


def test_network_failure_is_a_model_error(fake_model: dict[str, bytes]) -> None:
    def offline(_model: SpeechModel, _file: ModelFile, _folder: Path) -> None:
        raise OSError("no network")

    with pytest.raises(ModelError, match=r"could not download config\.json: no network"):
        models.download("tiny", fetch=offline)


def test_pinned_models_are_described() -> None:
    for model in models.MODELS.values():
        assert len(model.revision) == 40 and model.source.startswith("https://huggingface.co/Systran/")
        assert {f.name for f in model.files} == {
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.txt",
        }
        assert all(len(f.sha256) == 64 for f in model.files)


# ------------------------------------------------------------ transcript index
def test_transcripts_are_indexed_replaced_and_deleted(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.db")
    cues = [(2_670, "The harbor lights came on one by one."), (11_870, "The wind had turned cold.")]
    db.save_transcript("C:/Films/a.mkv", "a.mkv", "C:/s/a.srt", "en", "base", cues)
    db.save_transcript(
        "C:/Films/b.mkv", "b.mkv", "C:/s/b.srt", "en", "tiny", [(5_000, "Harbour market at night")]
    )
    hits = db.search_spoken("harbor light")  # every word; the last one as a prefix
    assert [(h.title, h.start_ms) for h in hits] == [("a.mkv", 2_670)]
    assert "[harbor]" in hits[0].text and "[lights]" in hits[0].text
    assert [h.title for h in db.search_spoken("HARBOUR")] == ["b.mkv"]
    # Replacing a file's transcript replaces its index entries.
    db.save_transcript("c:/films/A.mkv", "a.mkv", "C:/s/a2.srt", "en", "base", [(1_000, "Something else")])
    assert db.search_spoken("lights") == [] and len(db.transcripts()) == 2
    assert db.transcript_for("C:/Films/a.mkv").srt_path == "C:/s/a2.srt"  # type: ignore[union-attr]
    removed = db.delete_all_transcripts()
    assert len(removed) == 2 and db.transcripts() == [] and db.search_spoken("something") == []
    db.close()


@pytest.mark.parametrize(
    "query", ['"', "*", "harbor OR x", "NEAR(a b)", "a:b", "-x", "^", "()", "' OR 1=1 --", ""]
)
def test_search_queries_cannot_use_fts_syntax(tmp_path: Path, query: str) -> None:
    db = LibraryDatabase(tmp_path / "library.db")
    db.save_transcript("C:/a.mkv", "a.mkv", "C:/a.srt", "en", "base", [(0, "harbor lights or x near a b")])
    db.search_spoken(query)  # never raises, whatever the text
    db.close()
