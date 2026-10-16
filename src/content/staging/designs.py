"""A channel's designs: each recurring person, place or object drawn once, alone, in the
channel's look ([docs/3d-reuse.md](../../../docs/3d-reuse.md#designs)). Every keyframe that shows
it is drawn from its design, so it looks the same in every scene; a design made for one video is
reused by every later one; and its plain background makes it ready to become a 3D model.

Kept in `themes/<name>/designs/` and saved with the channel: `index.json` holds a record per
design, the pictures and any 3D models sit beside it. A design is known by what it is (its kind
and query), and by the look it was drawn in: when the channel's look changes, it is drawn again."""

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

import numpy as np

from content.providers import sam3d
from content.schemas.references import ReferenceKind

FOLDER = "designs"
INDEX = "index.json"
# Words that do not change what a thing is.
FILLER = re.compile(r"^(the|a|an) ")
# Which SAM 3D model makes each kind of design (a place stays a picture: it is lifted).
MAKERS: dict[str, sam3d.Model] = {"object": "objects", "person": "body"}
# Checked for free before a design is sent to the GPU: the thing found in it with at least this
# confidence (on real keyframes a person scored 0.84 and a lamp that was not there 0.40),
# filling this share of the picture, clear of the frame's edge by this many pixels,
# and this much of it in one piece.
FIND_THRESHOLD = 0.5
AREA = (0.02, 0.9)
EDGE = 2
ONE_PIECE = 0.9


@dataclass(frozen=True)
class Design:
    design_id: str
    kind: ReferenceKind
    query: str
    picture: str  # relative to the designs folder
    # The channel's look when it was drawn (`Theme.look_signature`): another look draws it again.
    look: str
    attempt: int
    # The video it was first drawn for.
    made_for: str
    # "vetoed": a person turned it down; it is drawn again, differently, when next needed.
    status: Literal["kept", "vetoed"] = "kept"
    # Its 3D model (`content designs model`), relative to the designs folder, once made.
    model: str = ""


def design_id(kind: ReferenceKind, query: str) -> str:
    """The same thing asked for in other words or capitals is the same design."""
    words = FILLER.sub("", re.sub(r"[^a-z0-9]+", " ", query.lower()).strip())
    # Short enough to name a job item (64 characters).
    return f"{kind}-{words.replace(' ', '-')}"[:64]


class Designs:
    def __init__(self, theme_root: Path) -> None:
        self.folder = theme_root / FOLDER

    def all(self) -> list[Design]:
        path = self.folder / INDEX
        if not path.is_file():
            return []
        return [Design(**record) for record in json.loads(path.read_text(encoding="utf-8"))]

    def get(self, key: str) -> Design | None:
        return next((design for design in self.all() if design.design_id == key), None)

    def usable(self, kind: ReferenceKind, query: str, look: str) -> Design | None:
        """The design to draw keyframes from, if there is a kept one in the current look."""
        design = self.get(design_id(kind, query))
        if design is None or design.status != "kept" or design.look != look:
            return None
        return design

    def next_attempt(self, kind: ReferenceKind, query: str) -> int:
        """A design drawn again (turned down, or its look changed) is drawn differently."""
        previous = self.get(design_id(kind, query))
        return 0 if previous is None else previous.attempt + 1

    def keep(
        self, kind: ReferenceKind, query: str, picture: Path, *, look: str, attempt: int, video: str
    ) -> Design:
        key = design_id(kind, query)
        self.folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(picture, self.folder / f"{key}.png")
        design = Design(key, kind, query, f"{key}.png", look, attempt, video)
        self._write([*(d for d in self.all() if d.design_id != key), design])
        return design

    def veto(self, key: str) -> Design:
        return self._update(key, status="vetoed")

    def add_model(self, key: str, model: Path) -> Design:
        shutil.copyfile(model, self.folder / f"{key}{model.suffix}")
        return self._update(key, model=f"{key}{model.suffix}")

    def path(self, design: Design) -> Path:
        return self.folder / design.picture

    def _update(self, key: str, **changes: str) -> Design:
        found = self.get(key)
        if found is None:
            raise KeyError(f"no design '{key}' (content designs list)")
        changed = replace(found, **changes)  # type: ignore[arg-type]
        self._write([changed if d.design_id == key else d for d in self.all()])
        return changed

    def _write(self, designs: list[Design]) -> None:
        records = [asdict(design) for design in sorted(designs, key=lambda d: d.design_id)]
        (self.folder / INDEX).write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


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


def prepare(designs: Designs, design: Design, scratch: Path) -> tuple[sam3d.Picture, list[str]]:
    """A design as a SAM 3D picture (an object's outline, a person's box), found on this
    computer with the vision models, and what the free checks found wrong with it."""
    from PIL import Image

    from content.providers import vision

    image = designs.path(design)
    phrase = "a person." if design.kind == "person" else f"{design.query}."
    found = vision.find(image, phrase, threshold=FIND_THRESHOLD)
    picture = sam3d.Picture(design.design_id, image)
    if not found:
        return picture, [f"no {design.kind} clearly found in it"]
    box = found[0].box
    mask = vision.outline(image, [box])[0]
    if design.kind == "person":
        return replace(picture, boxes=(box,)), mask_problems(mask)
    mask_path = scratch / f"{design.design_id}-mask.png"
    Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
    return replace(picture, masks=(mask_path,)), mask_problems(mask)


def waiting_for_models(designs: Designs) -> list[Design]:
    """Kept people and objects without a 3D model yet."""
    return [
        design
        for design in designs.all()
        if design.status == "kept" and not design.model and design.kind in MAKERS
    ]


def make_models(
    designs: Designs,
    ready: list[tuple[Design, sam3d.Picture]],
    out: Path,
    *,
    bucket: sam3d.Bucket,
    place: sam3d.Place,
    run: Callable[[sam3d.Place, str], None] = sam3d.run_job,
) -> list[str]:
    """One GPU job per SAM 3D model for every design ready, each model kept with its design."""
    report = []
    for kind, maker in MAKERS.items():
        batch = [(design, picture) for design, picture in ready if design.kind == kind]
        if not batch:
            continue
        result = sam3d.make(
            maker, [p for _, p in batch], out / maker, bucket=bucket, place=place, run=run
        )
        items = result.get("items", {})
        made = "0.glb" if maker == "objects" else "person_0.glb"
        for design, picture in batch:
            model = out / maker / picture.name / made
            if model.is_file():
                designs.add_model(design.design_id, model)
                report.append(f"{design.design_id}: 3D model kept ({maker})")
            else:
                why = items.get(picture.name, {}).get("error", result.get("error", "no model"))
                report.append(f"{design.design_id}: not made: {why}")
    return report
