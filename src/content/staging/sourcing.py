"""Where a library's models come from, other than code. A model the library lacks is searched
for in every free source at once; the closest matches are downloaded, brought into the
library's form, and drawn side by side in the channel's look, so the best is picked by eye.
Nothing joins the library until one is taken, and it then carries its rights (who made it,
the licence, the page) so the finished video can credit it.

Everything here is free; the only cost is Blender's time on this computer."""

import importlib
import io
import json
import math
import re
import shutil
import tempfile
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
from content.staging.library import PICTURES, Model, match
from content.staging.plan import themed
from content.staging.scoring import ACCEPT, Scorer
from content.staging.store import Store
from content.theme import Theme

# A library model has at most this many faces (more are simplified away as it is added).
MAX_FACES = 150_000
# Candidates with more than this are passed over: slow to download, and simplified to mush.
TOO_DETAILED = 1_000_000
SHORTLIST = 6
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
    status: str = "kept",
    score: float = 0.0,
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
    store = Store(library.folder)
    with tempfile.TemporaryDirectory() as work:
        if file.suffix.lower() in PICTURES:
            prepared = Path(work) / f"picture{file.suffix.lower()}"
            facts = _picture_facts(file, prepared, width=height or 1.0)
        else:
            prepared = Path(work) / "model.glb"
            facts = LocalBlender().ingest(
                file,
                prepared,
                height=height,
                max_faces=MAX_FACES,
                turn=turn or candidate.turn,
                up=candidate.up,
            )
        kept = store.keep_file(prepared)
    model = Model(
        model_id=model_id,
        names=tuple(names),
        describe=describe,
        size=(facts["width"], facts["depth"], facts["height"]),
        source=candidate.source,
        licence=candidate.licence,
        page=candidate.page,
        author=candidate.author,
        file=kept,
        parts=tuple(facts.get("parts", ())),
        motions=tuple(facts.get("motions", ())),
        capabilities=tuple(sorted(capabilities)),
        status=status,
        score=score,
    )
    library.add(model, alongside=alongside)
    store.note(model_id, "prepared", {
        "from": candidate.file_url, "up": candidate.up, "turn": turn, "height": height,
        "faces": facts.get("faces"), "size": model.size, "file": kept,
    })  # fmt: skip
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
        collada = sorted(folder.rglob("*.dae"))
        if collada:
            return _from_collada(collada[0], folder / "converted.glb")
        raise ValueError("no model file inside the download")
    path = folder / f"model.{file_type or 'glb'}"
    path.write_bytes(data)
    return path


def _from_collada(source: Path, target: Path) -> Path:
    """A COLLADA model (which Blender no longer reads) as glTF, in metres with Y up as glTF
    expects: its own unit applied, and the scale a Gazebo model file gives it."""
    try:
        trimesh: Any = importlib.import_module("trimesh")
    except ImportError as exc:
        raise ValueError("a COLLADA model: install the models extra to read it") from exc
    text = source.read_text(encoding="utf-8", errors="ignore")
    unit = re.search(r'<unit[^>]*meter="([0-9.eE+-]+)"', text)
    scale = float(unit.group(1)) if unit else 1.0
    sdf = next(source.parent.parent.glob("model.sdf"), None)
    if sdf is not None:
        given = re.search(r"<scale>\s*([0-9.eE+-]+)", sdf.read_text(encoding="utf-8"))
        scale *= float(given.group(1)) if given else 1.0
    scene = trimesh.load(str(source), force="scene")
    scene.apply_scale(scale)
    if "<up_axis>Z_UP" in text:
        scene.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    scene.export(str(target))
    return target


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
            download,
            prepared,
            height=None,
            max_faces=MAX_FACES,
            up=candidate.up,
            turn=candidate.turn,
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


def find(
    what: str,
    catalogue: Catalogue,
    sources: Sequence[AssetSource],
    scorer: Scorer,
    *,
    model_id: str,
) -> Model | None:
    """A model for `what`, found and taken without a person: every source searched, the
    best candidates prepared and drawn plainly, each scored by eye (`scoring.py`) and by
    its title, and the best taken if it is plainly the thing. It joins the library as
    `auto`, for a person to keep or turn down; every candidate's score is in its lineage.
    None when nothing is good enough: the scene is drawn instead."""
    library = catalogue.library
    turned_down = {m.page for m in library.models.values() if m.status == "vetoed"}
    folder = folder_for(what)
    entries, _ = shortlist(what, sources, folder, catalogue, None)
    scored = [
        (score_of(scorer, entry, what), entry)
        for entry in entries
        if entry.still and entry.candidate.page not in turned_down
    ]
    if not scored:
        return None
    (best, seen), entry = max(scored, key=lambda pair: pair[0][0])
    if seen < ACCEPT:
        return None
    unique = model_id
    while unique in library.models:
        unique = f"{model_id}_{len(unique)}"
    model = add_file(
        catalogue, Path(entry.download), entry.candidate, model_id=unique,
        describe=entry.candidate.title, names=(what,), status="auto", score=best,
        alongside=True,
    )  # fmt: skip
    Store(library.folder or folder).note(model.model_id, "chosen", {
        "asked": what,
        "candidates": [{"title": e.candidate.title, "page": e.candidate.page,
                        "seen": s[1], "score": s[0]} for s, e in scored],
    })  # fmt: skip
    return model


def score_of(scorer: Scorer, entry: Entry, what: str) -> tuple[float, float]:
    """How sure a candidate is the thing: mostly by eye, a little by its title."""
    seen = scorer(Path(entry.still), what)
    return round(0.8 * seen + 0.2 * match(what, entry.candidate.title), 3), seen
