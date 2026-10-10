import json
import shutil
from pathlib import Path

import pytest

from content.config import load_config, load_storage
from content.errors import ConfigurationError
from content.storage import (
    StorageError,
    archive_run,
    kept,
    kept_versions,
    pull_theme,
    restore_run,
    save_theme,
)
from content.theme import Theme, ThemeError, load_theme

PROJECT_ROOT = Path(__file__).parents[1]


class MemoryStore:
    """The bucket, in memory: what was uploaded, by name."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads = 0

    def exists(self, name: str) -> bool:
        return name in self.objects

    def upload(self, name: str, source: Path, content_type: str) -> None:
        self.objects[name] = source.read_bytes()
        self.uploads += 1

    def download(self, name: str, target: Path) -> None:
        target.write_bytes(self.objects[name])

    def names(self, prefix: str) -> list[str]:
        return sorted(name for name in self.objects if name.startswith(prefix))

    def delete(self, name: str) -> None:
        del self.objects[name]

    def blobs(self) -> list[str]:
        return self.names("blobs/")


def _finished_run(root: Path, final: bytes = b"final cut") -> Path:
    files = {
        "brief.md": b"# Topic",
        "1-script.md": b"## Script",
        "2-narration.m4a": b"narration",
        "4-final.mp4": final,
        "decisions.md": b"# Decisions",
        "cost.csv": b"session,total",
        "review.html": b"<html>",
        "3-scenes/S1.png": b"keyframe one",
        "3-scenes/S2.mp4": b"moving scene two",
        "3-scenes/animatic.mp4": b"animatic",
        "3-scenes/story-sheet/index.html": b"<html>",
        ".work/resume.json": b"{}",
        ".work/choices.json": b"{}",
        ".work/steps.jsonl": b"steps",
        ".work/reviews/request-1.json": b"{}",
    }
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)
    return root


def test_a_finished_run_keeps_only_its_signed_off_files(tmp_path: Path) -> None:
    store = MemoryStore()
    manifest = archive_run(store, _finished_run(tmp_path / "the-dam"))

    assert sorted(manifest.files) == [
        ".work/choices.json",
        ".work/resume.json",
        "1-script.md",
        "2-narration.m4a",
        "3-scenes/S1.png",
        "3-scenes/S2.mp4",
        "4-final.mp4",
        "brief.md",
        "cost.csv",
        "decisions.md",
    ]
    assert kept(store) == ["runs/the-dam.json"]
    assert manifest.files["4-final.mp4"].content_type == "video/mp4"


def test_the_same_file_is_kept_once_whichever_runs_use_it(tmp_path: Path) -> None:
    store = MemoryStore()
    archive_run(store, _finished_run(tmp_path / "the-dam"))
    blobs = store.blobs()
    uploads = store.uploads

    archive_run(store, _finished_run(tmp_path / "the-dam-v2"))

    # A second run with the same files adds its manifest and nothing else.
    assert store.blobs() == blobs
    assert store.uploads == uploads + 1


def test_a_kept_run_comes_back_byte_for_byte(tmp_path: Path) -> None:
    store = MemoryStore()
    original = _finished_run(tmp_path / "the-dam")
    archive_run(store, original)

    restored = tmp_path / "elsewhere" / "the-dam"
    manifest = restore_run(store, "the-dam", restored)

    for relative in manifest.files:
        assert (restored / relative).read_bytes() == (original / relative).read_bytes()
    assert not (restored / "3-scenes/animatic.mp4").exists()


def test_a_blob_that_comes_back_different_is_refused(tmp_path: Path) -> None:
    store = MemoryStore()
    archive_run(store, _finished_run(tmp_path / "the-dam"))
    store.objects[store.blobs()[0]] = b"damaged"

    with pytest.raises(StorageError, match="came back different"):
        restore_run(store, "the-dam", tmp_path / "restored")
    assert not list((tmp_path / "restored").rglob("*.partial"))


def test_rekeeping_a_changed_run_drops_only_the_blobs_nothing_uses(tmp_path: Path) -> None:
    store = MemoryStore()
    archive_run(store, _finished_run(tmp_path / "the-dam"))
    archive_run(store, _finished_run(tmp_path / "other", final=b"other cut"))
    first_cut = archive_run(store, _finished_run(tmp_path / "the-dam")).files["4-final.mp4"]

    recut = archive_run(store, _finished_run(tmp_path / "the-dam", final=b"re-cut"))

    assert f"blobs/{first_cut.sha256}" not in store.objects
    assert f"blobs/{recut.files['4-final.mp4'].sha256}" in store.objects
    # The keyframes the other run shares are still there for it.
    restore_run(store, "other", tmp_path / "check")
    assert (tmp_path / "check/3-scenes/S1.png").read_bytes() == b"keyframe one"


def test_only_a_finished_run_is_archived(tmp_path: Path) -> None:
    run = _finished_run(tmp_path / "the-dam")
    (run / "4-final.mp4").unlink()

    with pytest.raises(StorageError, match="only a finished run"):
        archive_run(MemoryStore(), run)


def _channel_theme(root: Path) -> Theme:
    starter = load_theme(PROJECT_ROOT / "themes" / "starter")
    shutil.copytree(starter.root, root)
    files = {
        "voice/master.wav": b"the narrator",
        "music/bed.mp3": b"the bed",
        "music/bed.map.json": b"{}",
        "music/candidates/take-2.mp3": b"an audition",
        "learning/labels.jsonl": b"{}",
        "learning/models/registry.json": b"{}",
        "learning/embedder/model.onnx": b"downloaded again",
    }
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)
    spec = json.loads((root / "theme.json").read_text(encoding="utf-8"))
    spec["voice"]["reference_audio"] = "voice/master.wav"
    spec["music"]["track"] = "music/bed.mp3"
    (root / "theme.json").write_text(json.dumps(spec), encoding="utf-8")
    return load_theme(root)


def test_a_fresh_clone_gets_the_whole_channel_theme_back(tmp_path: Path) -> None:
    store = MemoryStore()
    theme = _channel_theme(tmp_path / "channel")
    manifest = save_theme(store, theme.root)
    # Everything but the downloadable embedding model and the auditions.
    assert sorted(manifest.files) == [
        "README.md",
        "SKILL.md",
        "examples/README.md",
        "examples/the-great-stink/negative.json",
        "fonts/ArchivoBlack-Regular.ttf",
        "fonts/OFL.txt",
        "learning/labels.jsonl",
        "learning/models/registry.json",
        "music/bed.map.json",
        "music/bed.mp3",
        "theme.json",
        "voice/master.wav",
    ]

    clone = tmp_path / "clone" / "channel"
    with pytest.raises(ThemeError, match="storage pull"):
        load_theme(clone)
    pull_theme(store, clone)
    assert (load_theme(clone).root / "voice/master.wav").read_bytes() == b"the narrator"


def test_every_change_keeps_the_theme_as_it_was(tmp_path: Path) -> None:
    store = MemoryStore()
    theme = _channel_theme(tmp_path / "channel")
    save_theme(store, theme.root)
    save_theme(store, theme.root)
    # Saving an unchanged theme is not a new version.
    assert kept_versions(store, "channel") == []

    for edit in range(3):
        (theme.root / "SKILL.md").write_text(f"# Edit {edit}", encoding="utf-8")
        save_theme(store, theme.root)
    assert len(kept_versions(store, "channel")) == 3
    # A version keeps only the changed files' bytes: the rest are shared.
    current = save_theme(store, theme.root)
    assert len(store.blobs()) == len({stored.sha256 for stored in current.files.values()}) + 3


def test_going_back_to_a_version_is_exact_and_loses_nothing(tmp_path: Path) -> None:
    store = MemoryStore()
    theme = _channel_theme(tmp_path / "channel")
    original = (theme.root / "SKILL.md").read_bytes()
    save_theme(store, theme.root)
    (theme.root / "SKILL.md").write_bytes(b"# A rewrite I regret")
    (theme.root / "learning/flags.jsonl").write_bytes(b"{}")
    save_theme(store, theme.root)
    [first] = kept_versions(store, "channel")

    pull_theme(store, theme.root, first)

    assert (theme.root / "SKILL.md").read_bytes() == original
    assert not (theme.root / "learning/flags.jsonl").exists()
    # The regretted state is itself a version now, so it can come back too.
    regretted = kept_versions(store, "channel")[-1]
    pull_theme(store, theme.root, regretted)
    assert (theme.root / "SKILL.md").read_bytes() == b"# A rewrite I regret"


def test_storage_is_off_unless_the_configuration_names_a_bucket(tmp_path: Path) -> None:
    assert load_config(PROJECT_ROOT / "config/config.json").storage is None
    with pytest.raises(ConfigurationError, match="no storage section"):
        load_storage(PROJECT_ROOT / "config/config.json")

    data = json.loads((PROJECT_ROOT / "config/config.json").read_text(encoding="utf-8"))
    data["storage"] = {"bucket": "a-bucket"}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    storage, theme_root = load_storage(tmp_path / "config.json")
    assert storage.bucket == "a-bucket"
    assert theme_root.name == "starter"
