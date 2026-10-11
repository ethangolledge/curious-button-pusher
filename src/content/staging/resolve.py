"""What each thing in a scene is drawn with. A thing is plain words ("a red leather armchair",
"water glass", "a man in a suit, seated"); it resolves to a model at its real size, made to
fit the words: its colour and material become paint, its height a scale.

The cascade, cheapest first: the channel's library (its own models, the engine's props, and
versions of either); then (when a run allows it) the free online sources, searched, scored
and taken automatically (`staging/sourcing.py`). Everything found is kept, so a thing is
looked for once."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from content.blender.materials import BY_COLOUR, linear, nearest_role
from content.blender.maths import Vec
from content.schemas.staging import Thing
from content.staging.compose import Resolve, Resolved
from content.staging.library import Library, Model

# Finding a model online for some words: taken into the library, or None.
FindModel = Callable[[str], Model | None]
# A library model is taken for a thing when a search scores it at least this.
GOOD_MATCH = 0.6
# Words for what a thing is made of, and the role that draws it.
MATERIALS = {
    "wood": "wood", "wooden": "wood", "oak": "wood", "pine": "wood", "mahogany": "dark_wood",
    "walnut": "dark_wood", "ebony": "dark_wood", "metal": "metal", "steel": "metal",
    "iron": "metal", "brass": "metal", "gold": "metal", "golden": "metal", "silver": "metal",
    "chrome": "metal", "copper": "metal", "aluminium": "metal", "glass": "glass",
    "crystal": "glass", "paper": "paper", "card": "card", "cardboard": "card",
    "leather": "leather", "stone": "stone", "marble": "stone", "granite": "stone",
    "brick": "brick", "concrete": "concrete", "plastic": "plastic", "fabric": "fabric",
    "cloth": "fabric", "velvet": "fabric", "wool": "fabric", "cotton": "fabric",
    "rubber": "rubber", "ceramic": "paper", "porcelain": "paper", "china": "paper",
}  # fmt: skip
# Colour words, as the eye sees them; each draws in the role nearest that colour.
COLOURS = {
    "white": "#f2f0ea", "cream": "#e9e0c9", "black": "#141414", "grey": "#7f7f7f",
    "gray": "#7f7f7f", "silver": "#c0c0c0", "red": "#9b2a24", "crimson": "#8e1b2b",
    "brown": "#6b4a2f", "tan": "#b08a5c", "beige": "#d6c6a5", "green": "#3c6a3a",
    "olive": "#6b6b35", "blue": "#2c4a7a", "navy": "#1f2a44", "yellow": "#d8b33a",
    "gold": "#b8962e", "orange": "#c4672b", "pink": "#d49aa0", "purple": "#5a3a6a",
}  # fmt: skip


@dataclass(frozen=True)
class Look:
    """What a thing's words say about its surfaces: one role for all of them, or none."""

    role: str = ""

    @property
    def paint(self) -> dict[str, str]:
        return {"*": self.role} if self.role else {}


def look_of(thing: Thing) -> Look:
    """Its material if it names one, else the role nearest its colour."""
    words = " ".join(f"{s.name} {s.value}" for s in thing.looks).lower().split()
    for word in words:
        if word in MATERIALS:
            return Look(MATERIALS[word])
    for word in words:
        if word in COLOURS:
            role = nearest_role(linear(COLOURS[word]))
            return Look(role if role in BY_COLOUR else "paint")
    return Look()


def from_library(library: Library, *, people: Callable[[Thing], str] | None = None) -> Resolve:
    """Things resolved from the library alone (what the free check before a run can do)."""

    def resolve(thing: Thing) -> Resolved | None:
        model = _person(library, thing) if thing.person else _search(library, thing.what)
        return None if model is None else fitted(library, model, thing)

    return resolve


def with_online(library: Library, find_model: FindModel) -> Resolve:
    """Things resolved from the library, and what it lacks found online (each looked for
    once): the cascade a run uses."""
    local = from_library(library)
    tried: dict[str, Model | None] = {}

    def resolve(thing: Thing) -> Resolved | None:
        found = local(thing)
        if found is not None or thing.person is not None:
            return found
        if thing.what not in tried:
            tried[thing.what] = find_model(thing.what)
        model = tried[thing.what]
        return None if model is None else fitted(library, model, thing)

    return resolve


def fitted(library: Library, model: Model, thing: Thing) -> Resolved:
    """A library model made to fit a thing: painted as its words say, at its height."""
    look = look_of(thing)
    height = thing.height or 0.0
    if not look.paint and not height:
        w, d, h = model.size
        file = library.model_file(model.model_id)
        return Resolved(model.model_id, Vec(w, d, h), file, seated=_seated(model))
    key = f"{model.model_id}~{_digest([look.paint, height])}"
    file = library.model_file(model.model_id, key=key, paint=look.paint, height=height)
    assert file is not None
    w, d, h = file.size
    return Resolved(key, Vec(w, d, h), file, seated=_seated(model))


def _search(library: Library, words: str) -> Model | None:
    found = library.search(words)
    return found[0].model if found and found[0].score >= GOOD_MATCH else None


def _person(library: Library, thing: Thing) -> Model | None:
    """A particular person from the library, or a figurine in the pose asked for."""
    assert thing.person is not None
    if thing.person.who and thing.person.who in library.models:
        return library.get(thing.person.who)
    wanted = "seated_person" if thing.person.pose == "seated" else "person"
    return library.models.get(wanted)


def _seated(model: Model) -> bool:
    return "seated" in model.capabilities or model.model_id == "seated_person"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:8]
