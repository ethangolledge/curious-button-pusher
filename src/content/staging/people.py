"""People made to fit a scene: anyone a scene describes ("a man in a suit", "an old woman") is
made once, on this computer, from one parametric body (MakeHuman, CC0) on the one skeleton
every person shares, and kept in the library like any model, so the same description is the
same person every time. A shot poses them where it puts them (`blender/body.py`): the same
person sits at one desk and walks down another street.

`content staging people` installs what it needs (the MPFB extension for Blender, and the
CC0 clothes and hair). Without it a scene with people in it cannot be staged: it is drawn."""

import hashlib
import json
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from content.blender.body import STANDARD_HEIGHT
from content.providers.blender import LocalBlender
from content.schemas.staging import Person
from content.staging.library import Library, Model, Posture
from content.staging.motions import STANCES_MADE, stance_files
from content.staging.store import Store

SOURCE = "MakeHuman (MPFB)"
# The standing height a person is made when the scene gives none.
USUAL_HEIGHT = {"man": 1.78, "woman": 1.65}
# How people are made (`blender/person.py`): raised when that changes, so everyone is made
# again rather than kept as they were.
MAKER = 16
# Words for a thing that is a person, when a scene forgot to say so.
HUMAN = frozenset(
    {"person", "people", "man", "men", "woman", "women", "figure", "figures", "official",
     "officials", "guard", "guards", "aide", "aides", "crowd", "worker", "workers", "clerk",
     "banker", "lawyer", "politician", "minister", "delegate", "silhouette", "child"}
)  # fmt: skip
# The room a person takes in each pose, for someone `STANDARD_HEIGHT` tall, before they are
# made (as `blender/person.py` measured an average man): enough to compose a shot and check
# it before any Blender runs. Made, their own measures replace these.
STAND_INS = {
    "standing": Posture((0.54, 0.35, 1.8), (0.0, -0.11)),
    "seated": Posture((0.6, 0.78, 1.47), (0.0, -0.34), 0.457),
    "walking": Posture((0.53, 0.56, 1.785), (0.0, -0.11)),
}


@dataclass(frozen=True)
class Recipe:
    """Everything that shapes a person as they are made (not how they are posed: a shot does
    that)."""

    sex: Literal["man", "woman"]
    age: str
    build: str
    dress: str
    height: float
    maker: int = MAKER
    # The stances each pose is measured in as they are made.
    stances: str = STANCES_MADE


def recipe(person: Person, height: float) -> Recipe:
    """A person as described (what a scene leaves open, the most usual), at their standing
    height: a seated person's height is still how tall they stand."""
    return Recipe(
        sex=person.sex,
        age=person.age or "middle",
        build=person.build or "average",
        dress=person.dress,
        height=round(height or USUAL_HEIGHT[person.sex], 2),
    )


def character_id(made: Recipe) -> str:
    """The same recipe, the same person."""
    described = json.dumps(asdict(made), sort_keys=True)
    return f"person_{hashlib.sha256(described.encode()).hexdigest()[:10]}"


def is_person(what: str) -> bool:
    """Whether a thing's words name a person (a scene that forgot to describe them)."""
    return bool(HUMAN & set(re.findall(r"[a-z]+", what.lower())))


def character(library: Library, made: Recipe, *, make: bool) -> Model | None:
    """The person this recipe makes: from the library if made before, else made now (when
    `make`), else None."""
    model_id = character_id(made)
    if model_id in library.models:
        return library.models[model_id]
    if not make or library.folder is None:
        return None
    store = Store(library.folder)
    with tempfile.TemporaryDirectory() as work:
        file = Path(work) / "person.glb"
        # Each pose measured as it stands in the shot: the same motions.
        facts = LocalBlender().person({**asdict(made), "stances": stance_files(library)}, file)
        kept = store.keep_file(file)
    model = Model(
        model_id=model_id,
        names=(f"{made.age} {made.sex} {made.dress}",),
        describe=f"A {made.build} {made.age} {made.sex} in {made.dress} clothes",
        size=(facts["width"], facts["depth"], facts["height"]),
        capabilities=("person",),
        source=SOURCE,
        licence="CC0",
        file=kept,
        postures={name: Posture.read(p) for name, p in facts["postures"].items()},
    )
    library.save(model, "made", asdict(made))
    return model


def posture(model: Model | None, pose: str, doing: str, height: float) -> Posture:
    """The room a person takes doing this: as they were measured, or (not made yet) as an
    average person this tall would."""
    if model is not None and model.postures:
        return model.postures.get(f"{pose}:{doing}") or model.postures[f"{pose}:"]
    stand_in = STAND_INS[pose]
    s = height / STANDARD_HEIGHT
    w, d, h = stand_in.size
    return Posture((w * s, d * s, h * s), (stand_in.middle[0] * s, stand_in.middle[1] * s),
                   stand_in.seat)  # fmt: skip
