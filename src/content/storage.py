"""Permanent storage in a cloud bucket: the signed-off files of finished runs and the
channel's own theme. Nothing else goes there.

The bucket is not a cache. Work in progress (every keyframe drawn, every take spoken,
every render) stays in `.cache/` on this machine; a run folder already holds only what
each sign-off approved, so a finished run's folder is what is kept for good.

Layout, one bucket:

    blobs/<sha256>        the bytes of every kept file, named by their hash: the same
                          file is stored once, whichever runs and themes use it
    runs/<slug>.json      a finished run's manifest: its file names and their hashes
    themes/<name>.json    a channel's theme folder, the same way
    themes/<name>/versions/<saved>.json
                          every earlier state of the theme, never deleted

A channel's theme is private: its settings, voice, music and taste data live here, not in
git, which holds only the starter theme.

Restoring reads a manifest and fetches its blobs, checking each against its hash.
"""

import hashlib
import mimetypes
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from content.schemas.base import ImmutableModel

# What a finished run keeps: what each sign-off approved, the final cut, and the record
# of how it was made (the approved state is a few KB and lets a re-cut start from it).
# Previews (the animatic, the story sheet), the review page and work files are left out:
# they were for deciding, and the kept files rebuild them.
RUN_FILES = (
    "brief.md",
    "1-script.md",
    "2-narration.m4a",
    "4-final.mp4",
    "decisions.md",
    "cost.csv",
    ".work/resume.json",
    ".work/choices.json",
)
# Each scene's signed-off picture: S4.png, or S4.mp4 where the scene moves.
RUN_SCENES = "3-scenes/S*"
FINAL_CUT = "4-final.mp4"
# A theme keeps its whole folder except what is fetched again (the embedding model) or was
# only auditioned. Whenever it changes, the theme as it was is kept as a version, for good:
# a version costs only the files that changed.
THEME_SKIPPED = ("learning/embedder/", "music/candidates/")


class StorageError(RuntimeError):
    pass


class BlobStore(Protocol):
    """The bucket, as the few operations permanent storage needs."""

    def exists(self, name: str) -> bool: ...

    def upload(self, name: str, source: Path, content_type: str) -> None: ...

    def download(self, name: str, target: Path) -> None: ...

    def names(self, prefix: str) -> list[str]: ...

    def delete(self, name: str) -> None: ...


class StoredFile(ImmutableModel):
    sha256: str
    bytes: int
    content_type: str


class Manifest(ImmutableModel):
    """A run or a theme's kept files, by their path inside its folder."""

    name: str
    saved: str
    files: dict[str, StoredFile]


def run_manifest(slug: str) -> str:
    return f"runs/{slug}.json"


def theme_manifest(name: str) -> str:
    return f"themes/{name}.json"


def theme_versions(name: str) -> str:
    return f"themes/{name}/versions/"


def _blob(sha256: str) -> str:
    return f"blobs/{sha256}"


def archive_run(store: BlobStore, folder: Path) -> Manifest:
    """Keep a finished run for good. Only files not already in the bucket are uploaded."""
    if not (folder / FINAL_CUT).is_file():
        raise StorageError(f"{folder} has no {FINAL_CUT}: only a finished run is archived")
    scenes = sorted(path for path in folder.glob(RUN_SCENES) if path.is_file())
    kept = [folder / name for name in RUN_FILES if (folder / name).is_file()] + scenes
    return _save(store, run_manifest(folder.name), folder, kept)


def restore_run(store: BlobStore, slug: str, folder: Path) -> Manifest:
    """Bring a kept run back into `folder`."""
    return _restore(store, run_manifest(slug), folder)


def save_theme(store: BlobStore, theme_root: Path) -> Manifest:
    """Keep a channel's theme folder. If it changed since the last save, the theme as it
    was is kept too, as a version (see `kept_versions`)."""
    name = theme_manifest(theme_root.name)
    files = _theme_files(theme_root)
    if store.exists(name):
        current = _load(store, name)
        now = {path.relative_to(theme_root).as_posix(): _sha256(path) for path in files}
        if {path: stored.sha256 for path, stored in current.files.items()} != now:
            stamp = current.saved.removesuffix("+00:00").replace(":", "-")
            _write(store, f"{theme_versions(theme_root.name)}{stamp}.json", current)
    return _save(store, name, theme_root, files)


def pull_theme(store: BlobStore, theme_root: Path, version: str | None = None) -> Manifest:
    """Bring a channel's theme back, for a fresh clone or another machine. With `version`
    (one of `kept_versions`), the theme becomes exactly that version: the current theme is
    saved first, so going back loses nothing."""
    name = theme_root.name
    if version is None:
        return _restore(store, theme_manifest(name), theme_root)
    if (theme_root / "theme.json").is_file():
        save_theme(store, theme_root)
    manifest = _restore(store, f"{theme_versions(name)}{version}.json", theme_root)
    for path in _theme_files(theme_root):
        if path.relative_to(theme_root).as_posix() not in manifest.files:
            path.unlink()
    # Saving again makes the version current and keeps what was current as a version.
    return save_theme(store, theme_root)


def kept_versions(store: BlobStore, name: str) -> list[str]:
    """The theme's earlier versions, oldest first, by when they were saved."""
    prefix = theme_versions(name)
    return [path.removeprefix(prefix).removesuffix(".json") for path in store.names(prefix)]


def _theme_files(theme_root: Path) -> list[Path]:
    return [
        path
        for path in sorted(theme_root.rglob("*"))
        if path.is_file() and not path.relative_to(theme_root).as_posix().startswith(THEME_SKIPPED)
    ]


def kept(store: BlobStore) -> list[str]:
    """Every manifest in the bucket: the kept runs, themes and theme versions."""
    return sorted(name for prefix in ("runs/", "themes/") for name in store.names(prefix))


def _save(store: BlobStore, manifest_name: str, root: Path, paths: Iterable[Path]) -> Manifest:
    files = {path.relative_to(root).as_posix(): _push(store, path) for path in paths}
    if not files:
        raise StorageError(f"Nothing to keep in {root}")
    manifest = Manifest(name=root.name, saved=datetime.now(UTC).isoformat(), files=files)
    replaced = _load(store, manifest_name) if store.exists(manifest_name) else None
    _write(store, manifest_name, manifest)
    if replaced is not None and _hashes(replaced) - _hashes(manifest):
        _drop_unused_blobs(store)
    return manifest


def _write(store: BlobStore, manifest_name: str, manifest: Manifest) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        written = Path(scratch) / "manifest.json"
        written.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        store.upload(manifest_name, written, "application/json")


def _push(store: BlobStore, path: Path) -> StoredFile:
    stored = StoredFile(
        sha256=_sha256(path),
        bytes=path.stat().st_size,
        content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )
    if not store.exists(_blob(stored.sha256)):
        store.upload(_blob(stored.sha256), path, stored.content_type)
    return stored


def _restore(store: BlobStore, manifest_name: str, root: Path) -> Manifest:
    if not store.exists(manifest_name):
        raise StorageError(f"Nothing kept under {manifest_name}")
    manifest = _load(store, manifest_name)
    for relative, stored in manifest.files.items():
        target = root / relative
        if target.is_file() and _sha256(target) == stored.sha256:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        store.download(_blob(stored.sha256), partial)
        if _sha256(partial) != stored.sha256:
            partial.unlink()
            raise StorageError(f"{relative} came back different from what was kept")
        partial.replace(target)
    return manifest


def _load(store: BlobStore, manifest_name: str) -> Manifest:
    with tempfile.TemporaryDirectory() as scratch:
        read = Path(scratch) / "manifest.json"
        store.download(manifest_name, read)
        return Manifest.model_validate_json(read.read_text(encoding="utf-8"))


def _drop_unused_blobs(store: BlobStore) -> None:
    """Delete blobs no manifest names any more, so a replaced file is not paid for twice."""
    used = set().union(*(_hashes(_load(store, name)) for name in kept(store)))
    for name in store.names("blobs/"):
        if name.removeprefix("blobs/") not in used:
            store.delete(name)


def _hashes(manifest: Manifest) -> set[str]:
    return {stored.sha256 for stored in manifest.files.values()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class GcsStore:
    """A Google Cloud Storage bucket, signed in with application-default credentials
    (`gcloud auth application-default login`). Needs the `cloud` extra."""

    def __init__(self, bucket: str) -> None:
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise StorageError("Install the cloud extra: pip install -e '.[cloud]'") from exc
        self._bucket = storage.Client().bucket(bucket)

    def exists(self, name: str) -> bool:
        return bool(self._bucket.blob(name).exists())

    def upload(self, name: str, source: Path, content_type: str) -> None:
        # The client checks the upload against its CRC32C checksum.
        self._bucket.blob(name).upload_from_filename(str(source), content_type=content_type)

    def download(self, name: str, target: Path) -> None:
        self._bucket.blob(name).download_to_filename(str(target))

    def names(self, prefix: str) -> list[str]:
        return [blob.name for blob in self._bucket.list_blobs(prefix=prefix)]

    def delete(self, name: str) -> None:
        self._bucket.blob(name).delete()


def describe(manifest: Manifest) -> str:
    size = sum(stored.bytes for stored in manifest.files.values())
    return f"{manifest.name}: {len(manifest.files)} files, {size / 1e6:.1f} MB"
