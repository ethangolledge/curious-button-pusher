"""A channel's designs: each recurring person, place or object drawn once, alone, in the
channel's look ([docs/3d-reuse.md](../../../docs/3d-reuse.md#designs)). Every keyframe that
shows it is drawn from its design, so it looks the same in every scene; a design made for one
video is reused by every later one; and its plain background makes it ready to become a 3D
model.

A design is a model in the channel's library (`library.Identity`): kept, turned down and traced
like any other (`content staging keep | veto | history`), its drawing stored with the library's
files. It is known by what it is (its kind and query) and by the look it was drawn in: when the
channel's look changes, it is drawn again. Its 3D model, once made, becomes its file, and only
then can a shot use it."""

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from content.providers import sam3d
from content.schemas.references import ReferenceKind
from content.staging.library import DESIGNED, Identity, Library, Model
from content.staging.store import Store

# Words that do not change what a thing is.
FILLER = re.compile(r"^(the|a|an) ")
# Which SAM 3D model makes each kind of design. A place stays a picture (it is lifted); a
# person is made on the skeleton every person shares, fitted to their design
# (`staging/people.py`), never as a mesh of their own: everyone is posed the same way.
MAKERS: dict[str, sam3d.Model] = {"object": "objects"}
# The file each SAM 3D model makes for the first thing in a picture.
MADE = {"objects": "0.glb"}
# Checked for free before a design is sent to the GPU: the thing found in it with at least this
# confidence (on real keyframes a person scored 0.84 and a lamp that was not there 0.40),
# filling this share of the picture, clear of the frame's edge by this many pixels,
# and this much of it in one piece.
FIND_THRESHOLD = 0.5
AREA = (0.02, 0.9)
EDGE = 2
ONE_PIECE = 0.9

# A 3D model brought into the library's form (upright, in metres, facing −Y): its facts
# (`LocalBlender.ingest`), written to the second path.
Ingest = Callable[[Path, Path], dict[str, Any]]


def design_id(kind: ReferenceKind, query: str) -> str:
    """The same thing asked for in other words or capitals is the same design. Short enough
    to name a SAM 3D job's item (64 characters)."""
    words = FILLER.sub("", re.sub(r"[^a-z0-9]+", " ", query.lower()).strip())
    return f"{kind}_{words.replace(' ', '_')}"[:64]


def usable(library: Library, kind: ReferenceKind, query: str, look: str) -> Model | None:
    """The design to draw keyframes from, if the channel keeps one in the current look."""
    model = library.models.get(design_id(kind, query))
    if model is None or model.identity is None or model.status == "vetoed":
        return None
    return model if model.identity.look == look else None


def next_attempt(library: Library, kind: ReferenceKind, query: str) -> int:
    """A design drawn again (turned down, or its look changed) is drawn differently."""
    previous = library.models.get(design_id(kind, query))
    return 0 if previous is None or previous.identity is None else previous.identity.attempt + 1


def keep(
    library: Library,
    kind: ReferenceKind,
    query: str,
    drawing: Path,
    *,
    look: str,
    attempt: int,
    video: str,
) -> Model:
    """A design that passed its checks, kept in the library (replacing any earlier drawing)."""
    assert library.folder is not None
    picture = Store(library.folder).keep_file(drawing)
    model = Model(
        model_id=design_id(kind, query),
        names=(query,),
        describe=f"the channel's design of {query} ({kind})",
        size=(0.0, 0.0, 0.0),
        source=DESIGNED,
        licence="own",
        identity=Identity(kind, query, picture, look, attempt),
    )
    library.save(model, "drawn", {"video": video, "attempt": attempt, "picture": picture})
    return model


def picture(library: Library, model: Model) -> Path:
    assert library.folder is not None and model.identity is not None
    return library.folder / model.identity.picture


def waiting_for_models(library: Library) -> list[Model]:
    """Kept people and objects without a 3D model yet."""
    return [
        model
        for model in sorted(library.models.values(), key=lambda m: m.model_id)
        if model.identity is not None
        and model.status != "vetoed"
        and not model.file
        and model.identity.kind in MAKERS
    ]


def mask_problems(mask: np.ndarray) -> list[str]:
    """What would make a thing's outline a waste of a GPU run: too small or too large, cut off
    by the frame, or in pieces."""
    from scipy import ndimage

    problems = []
    share = float(mask.mean())
    if not AREA[0] <= share <= AREA[1]:
        problems.append(f"it fills {share:.0%} of the picture")
    if mask[:EDGE].any() or mask[-EDGE:].any() or mask[:, :EDGE].any() or mask[:, -EDGE:].any():
        problems.append("it touches the frame's edge")
    labels, pieces = ndimage.label(mask)
    if pieces > 1 and np.bincount(labels.ravel())[1:].max() < ONE_PIECE * mask.sum():
        problems.append("it is in pieces")
    return problems


def outline(library: Library, model: Model) -> np.ndarray | None:
    """The outline of what a design shows (the person, the object), found on this computer
    with the vision models; None when it is not clearly there."""
    from content.providers import vision

    assert model.identity is not None
    image = picture(library, model)
    phrase = "a person." if model.identity.kind == "person" else f"{model.identity.query}."
    found = vision.find(image, phrase, threshold=FIND_THRESHOLD)
    return vision.outline(image, [found[0].box])[0] if found else None


def prepare(library: Library, model: Model, scratch: Path) -> tuple[sam3d.Picture, list[str]]:
    """An object's design as a SAM 3D picture (with its outline), and what the free checks
    found wrong with it."""
    from PIL import Image

    assert model.identity is not None
    sent = sam3d.Picture(model.model_id, picture(library, model))
    mask = outline(library, model)
    if mask is None:
        return sent, [f"no {model.identity.kind} clearly found in it"]
    mask_path = scratch / f"{model.model_id}-mask.png"
    Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
    return replace(sent, masks=(mask_path,)), mask_problems(mask)


def make_models(
    library: Library,
    ready: list[tuple[Model, sam3d.Picture]],
    out: Path,
    *,
    bucket: sam3d.Bucket,
    place: sam3d.Place,
    ingest: Ingest,
    run: Callable[[sam3d.Place, str], None] = sam3d.run_job,
) -> list[str]:
    """One GPU job per SAM 3D model for every design ready; each model brought into the
    library's form and kept as its design's file, its making in the design's lineage."""
    assert library.folder is not None
    store = Store(library.folder)
    report = []
    for kind, maker in MAKERS.items():
        batch = [
            (m, sent) for m, sent in ready if m.identity is not None and m.identity.kind == kind
        ]
        if not batch:
            continue
        result = sam3d.make(
            maker, [sent for _, sent in batch], out / maker, bucket=bucket, place=place, run=run
        )
        items = result.get("items", {})
        for model, sent in batch:
            made = out / maker / sent.name / MADE[maker]
            if not made.is_file():
                why = items.get(sent.name, {}).get("error", result.get("error", "no model"))
                report.append(f"{model.model_id}: not made: {why}")
                continue
            prepared = out / maker / sent.name / "prepared.glb"
            facts = ingest(made, prepared)
            file = store.keep_file(prepared)
            library.save(
                replace(model, file=file, size=(facts["width"], facts["depth"], facts["height"])),
                "made",
                {"by": f"sam3d {maker}", "job": result["job"], "file": file},
            )
            report.append(f"{model.model_id}: 3D model kept ({maker})")
    return report
