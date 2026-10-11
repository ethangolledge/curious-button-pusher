"""Where a library's models come from, other than code. A model the library lacks is searched
for in every free source at once; the closest matches are downloaded, brought into the
library's form, and drawn side by side in the channel's look, so the best is picked by eye.
Nothing joins the library until one is taken, and it then carries its rights (who made it,
the licence, the page) so the finished video can credit it.

Everything here is free; the only cost is Blender's time on this computer."""

import io
import json
import re
import shutil
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from content.blender.job import ActorCall, BlockCall, Job, ModelFile
from content.providers import ffmpeg
from content.providers.assets import ALLOWED, AssetSource, Candidate
from content.providers.blender import LocalBlender
from content.staging.catalogue import Catalogue, with_models
from content.staging.library import Model, match
from content.staging.plan import themed
from content.theme import Theme

# A library model has at most this many faces (more are simplified away as it is added).
MAX_FACES = 150_000
# Candidates with more than this are passed over: slow to download, and simplified to mush.
TOO_DETAILED = 1_000_000
SHORTLIST = 6
# Pictures (maps, paintings, views) join the library as they are, for the picture actor.
PICTURES = (".png", ".jpg", ".jpeg", ".webp")
MODEL_FILES = (".glb", ".gltf", ".obj", ".fbx", ".stl")
CANDIDATES = "candidates.json"


@dataclass(frozen=True)
class Entry:
    """A shortlisted candidate: what the source said, where its download is, and (if it could
    be brought into the library's form) the prepared model and its picture."""

    candidate: Candidate
    download: str = ""
    model: str = ""
    size: tuple[float, float, float] = (0.0, 0.0, 0.0)
    still: str = ""
    problem: str = ""


def rank(words: str, candidates: Sequence[Candidate], limit: int = SHORTLIST) -> list[Candidate]:
    """The candidates worth looking at, best first: free to use, not absurdly detailed, each
    once, ordered by how well their titles match the words (sources' own order breaking
    ties)."""
    seen: set[str] = set()
    usable = []
    for candidate in candidates:
        if candidate.licence not in ALLOWED or candidate.faces > TOO_DETAILED:
            continue
        if candidate.page not in seen:
            seen.add(candidate.page)
            usable.append(candidate)
    return sorted(usable, key=lambda c: -match(words, c.title))[:limit]


def shortlist(
    words: str,
    sources: Sequence[AssetSource],
    folder: Path,
    catalogue: Catalogue,
    theme: Theme | None,
) -> tuple[list[Entry], list[str]]:
    """Search every source, and prepare and draw the best candidates; kept in `folder`, so
    taking one later downloads nothing again. Returns the entries and any source that
    failed (a missing key, the source being down), which never stops the others."""
    found: list[Candidate] = []
    failed: list[str] = []
    for source in sources:
        try:
            found += source.search(words, SHORTLIST)
        except Exception as exc:  # one source failing must not stop the rest
            failed.append(f"{source.name}: {exc}")
    by_name = {source.name: source for source in sources}
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, candidate in enumerate(rank(words, found), 1):
        source = by_name[candidate.source]
        entries.append(_prepare(candidate, source, folder / str(index), catalogue, theme))
    (folder / CANDIDATES).write_text(
        json.dumps([asdict(entry) for entry in entries], indent=2), encoding="utf-8"
    )
    return entries, failed


def shortlisted(folder: Path) -> list[Entry]:
    """The shortlist kept in `folder` by the last search for the same words."""
    path = folder / CANDIDATES
    if not path.is_file():
        return []
    return [
        Entry(**{**data, "candidate": Candidate(**data["candidate"]), "size": tuple(data["size"])})
        for data in json.loads(path.read_text(encoding="utf-8"))
    ]


def add_file(
    catalogue: Catalogue,
    file: Path,
    candidate: Candidate,
    *,
    model_id: str,
    describe: str,
    names: Sequence[str] = (),
    height: float | None = None,
    turn: float = 0.0,
    capabilities: Sequence[str] = (),
    alongside: bool = False,
) -> Model:
    """A model file (or a picture) brought into the library's form and added, with its
    rights. Refused, leaving nothing behind, if its licence is not free enough or the
    library already has it under another name."""
    library = catalogue.library
    if library.folder is None:
        raise ValueError("models are added to a channel's library")
    if candidate.licence not in ALLOWED:
        raise ValueError(
            f"only free licences enter the library ({', '.join(sorted(ALLOWED))}): "
            f"'{candidate.licence}' forbids commercial use or changes"
        )
    model_id = re.sub(r"[^a-z0-9_]+", "_", model_id.lower()).strip("_")
    if file.suffix.lower() in PICTURES:
        target = library.folder / f"{model_id}{file.suffix.lower()}"
        facts = _picture_facts(file, target, width=height or 1.0)
    else:
        target = library.folder / f"{model_id}.glb"
        facts = LocalBlender().ingest(
            file, target, height=height, max_faces=MAX_FACES, turn=turn, up=candidate.up
        )
    model = Model(
        model_id=model_id,
        names=tuple(names),
        describe=describe,
        size=(facts["width"], facts["depth"], facts["height"]),
        source=candidate.source,
        licence=candidate.licence,
        page=candidate.page,
        author=candidate.author,
        file=target.name,
        parts=tuple(facts.get("parts", ())),
        motions=tuple(facts.get("motions", ())),
        capabilities=tuple(sorted(capabilities)),
    )
    try:
        library.add(model, alongside=alongside)
    except ValueError:
        target.unlink(missing_ok=True)
        raise
    return model


def turntable(catalogue: Catalogue, model_id: str, theme: Theme | None, out: Path) -> list[Path]:
    """Four views of a library model in the studio, in the channel's look, to judge it by."""
    job = with_models(_studio(model_id, (1, 40, 80, 120)), catalogue)
    job = themed(job, theme) if theme else job
    report = LocalBlender().render(job, out)
    return [Path(frame) for frame in report.frames]


def _unpack(data: bytes, folder: Path, file_type: str) -> Path:
    """The model file in a download: the file itself, or the model inside a zip."""
    folder.mkdir(parents=True, exist_ok=True)
    if data[:2] == b"PK":
        zipfile.ZipFile(io.BytesIO(data)).extractall(folder)
        for suffix in MODEL_FILES:
            found = sorted(folder.rglob(f"*{suffix}"))
            if found:
                return found[0]
        raise ValueError("no model file inside the download")
    path = folder / f"model.{file_type or 'glb'}"
    path.write_bytes(data)
    return path


def _prepare(
    candidate: Candidate,
    source: AssetSource,
    folder: Path,
    catalogue: Catalogue,
    theme: Theme | None,
) -> Entry:
    """Download a candidate, bring it into the library's form, and draw it on its own."""
    try:
        download = _unpack(source.download(candidate), folder / "download", candidate.file_type)
        prepared = folder / "model.glb"
        facts = LocalBlender().ingest(
            download, prepared, height=None, max_faces=MAX_FACES, up=candidate.up
        )
        size = (facts["width"], facts["depth"], facts["height"])
        job = replace(
            _studio("candidate", (60,)),
            models=(ModelFile("candidate", str(prepared), size),),
            channel_blocks=tuple(str(blocks) for blocks in catalogue.channel_blocks),
        )
        report = LocalBlender().render(themed(job, theme) if theme else job, folder / "still")
    except Exception as exc:  # a broken download is a candidate passed over
        lines = [line for line in str(exc).splitlines() if line.strip()]
        return Entry(candidate, problem=(lines[-1] if lines else type(exc).__name__)[:200])
    still = report.frames[0] if report.frames else ""
    return Entry(candidate, str(download), str(prepared), size, still)


def _studio(model_id: str, frames: tuple[int, ...]) -> Job:
    """A model alone on the studio's plinth, the camera going round it."""
    return Job(
        shot_id=f"model-{model_id}", seconds=4, width=540, height=960, quality="still",
        layout=BlockCall("studio"), look=BlockCall("plain"),
        actors=(ActorCall("model", "prop", model_id, {"at": "plinth_top"}),),
        lights=(BlockCall("studio", {"subject": "model"}),),
        camera=BlockCall("orbit", {
            "subject": "model", "degrees": "270", "start": "-30", "framing": "medium",
            "elevation": "20",
        }),
        frames=frames,
    )  # fmt: skip


def _picture_facts(source: Path, target: Path, *, width: float) -> dict[str, Any]:
    """A picture is kept as it is; its real size is its width and its own shape."""
    info = ffmpeg.probe(source)
    if not info.width or not info.height:
        raise ValueError(f"{source} is not a picture ffmpeg can read")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    height = round(width * info.height / info.width, 3)
    return {"width": width, "depth": 0.0, "height": height, "faces": 0}


def folder_for(words: str) -> Path:
    """Where a search's shortlist is kept."""
    slug = re.sub(r"[^a-z0-9]+", "-", words.lower()).strip("-")
    return Path(".cache/staging/candidates") / slug
