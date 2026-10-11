"""People made to fit a scene: anyone a scene describes ("a man in a suit, seated", "an old
woman, walking") is made once, on this computer, from one parametric body (MakeHuman, CC0),
and kept in the library like any model, so the same description is the same person every
time. A particular person (`who`) is the library's own model of them.

`content staging people` installs what it needs (the MPFB extension for Blender, and the
CC0 clothes and hair); without it, people are the engine's simple figurines."""

import hashlib
import json
import tempfile
from pathlib import Path

from content.providers.blender import LocalBlender
from content.schemas.staging import Person
from content.staging.library import Library, Model
from content.staging.store import Store

SOURCE = "MakeHuman (MPFB)"
# The standing height a person is made when the scene gives none.
USUAL_HEIGHT = {"man": 1.78, "woman": 1.65}


def person_id(person: Person, height: float) -> str:
    """The same description, the same person: an id from everything that shapes them."""
    described = json.dumps(_description(person, height), sort_keys=True)
    return f"person_{hashlib.sha256(described.encode()).hexdigest()[:10]}"


def made_person(library: Library, person: Person, height: float, *, make: bool) -> Model | None:
    """The person this description makes: from the library if made before, else made now
    (when `make`), else None."""
    model_id = person_id(person, height)
    if model_id in library.models:
        return library.models[model_id]
    if not make or library.folder is None:
        return None
    store = Store(library.folder)
    described = _description(person, height)
    with tempfile.TemporaryDirectory() as work:
        made = Path(work) / "person.glb"
        facts = LocalBlender().person(described, made)
        kept = store.keep_file(made)
    model = Model(
        model_id=model_id,
        names=(f"{person.age} {person.sex} {person.dress} {person.pose}",),
        describe=f"A {person.build} {person.age} {person.sex} in {person.dress} clothes, "
        f"{person.pose}",
        size=(facts["width"], facts["depth"], facts["height"]),
        capabilities=("person", *(("seated",) if person.pose == "seated" else ())),
        source=SOURCE,
        licence="CC0",
        file=kept,
        seat=facts.get("seat", 0.0),
        motions=tuple(facts.get("motions", ())),
    )
    library.add(model, alongside=True)
    store.note(model_id, "made", described)
    return model


def _description(person: Person, height: float) -> dict[str, object]:
    return {
        "sex": person.sex,
        "age": person.age,
        "build": person.build,
        "dress": person.dress,
        "pose": person.pose,
        "motion": "" if person.motion == "still" else person.motion,
        "height": round(height or USUAL_HEIGHT[person.sex], 2),
    }
