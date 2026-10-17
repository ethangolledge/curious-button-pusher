"""A person's design fitted onto the skeleton everyone shares: the body that matches their
design's outline, front and side, so the layout a keyframe is drawn over has their shape
(a big head, a paunch, narrow shoulders), and the person moves as everyone does.

Free: the design's outlines are found on this computer (`designs.outlines`), and the body is
fitted in Blender (`blender/fit.py`), turning its dials until the outlines overlap most. The
fitted body becomes the design's file, so a scene naming them (`who`) places them."""

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from content.providers.blender import LocalBlender
from content.staging import designs
from content.staging.library import Library, Model
from content.staging.people import Recipe, character

# The dials fitted, and how far round from the front each view of a design sheet is drawn,
# left to right (`blender/fit.py`: a profile facing left is seen from the person's right).
DIALS = ("weight", "muscle", "head", "shoulders", "hips", "belly")
VIEWS = (0.0, -90.0)


@dataclass(frozen=True)
class Fitted:
    """The design as fitted, how well (the outlines' overlap, 0 to 1), and the pictures of
    each view's outlines over each other."""

    model: Model
    fit: float
    overlays: list[Path]


def fit(library: Library, design: Model, start: Recipe, out: Path) -> Fitted:
    """The design's person, made to `start` (what the director says of them: sex, age,
    dress, height) with the body that best matches their design, kept as the design's file."""
    from PIL import Image

    masks = designs.outlines(library, design)
    if not masks:
        raise ValueError(f"{design.model_id}: no person clearly found in its design")
    out.mkdir(parents=True, exist_ok=True)
    views = []
    for index, (mask, turn) in enumerate(zip(masks, VIEWS, strict=False)):
        path = out / f"design-{index}.png"
        Image.fromarray(mask.astype(np.uint8) * 255).save(path)
        views.append({"mask": str(path), "turn": turn})
    found = LocalBlender().fit({"recipe": asdict(start), "views": views, "dials": list(DIALS)}, out)
    made = replace(start, body=tuple(sorted(found["body"].items())))
    person = character(library, made, make=True)
    assert person is not None
    fitted = replace(
        design, file=person.file, size=person.size, postures=person.postures,
        capabilities=person.capabilities,
    )  # fmt: skip
    library.save(fitted, "fitted", {"fit": found["fit"], "recipe": asdict(made)})
    return Fitted(fitted, found["fit"], [out / f"overlay-{i}.png" for i in range(len(views))])
