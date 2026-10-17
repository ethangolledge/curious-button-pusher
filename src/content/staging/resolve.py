"""What each thing in a scene is drawn with. A thing is plain words ("a red leather armchair",
"water glass", "a man in a suit, seated"); it resolves to a model at its real size, made to
fit the words: its colour and material become paint, its height a scale.

The cascade, cheapest first: the channel's library (its own models, the engine's props, and
versions of either); then (when a run allows it) the free online sources, searched, scored
and taken automatically (`staging/sourcing.py`). Everything found is kept, so a thing is
looked for once."""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from content.blender.blocks.base import Prop, settings
from content.blender.job import ModelFile
from content.blender.materials import BY_COLOUR, linear, nearest_role
from content.blender.maths import Vec
from content.schemas.staging import Thing
from content.staging.compose import Resolve, Resolved
from content.staging.library import PICTURES, Library, Model
from content.staging.people import character, character_id, posture, recipe

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


def from_library(library: Library, *, make_people: bool = False) -> Resolve:
    """Things resolved from the library alone (what the free check before a run can do);
    people the scene describes are made when `make_people`."""

    def resolve(thing: Thing) -> Resolved | None:
        if thing.person is not None:
            return _person(library, thing, make=make_people)
        model = _search(library, thing.what)
        return None if model is None else fitted(library, model, thing)

    return resolve


def with_online(
    library: Library, find_model: FindModel | None, *, make_people: bool = False
) -> Resolve:
    """Things resolved from the library, what it lacks found online (each looked for once),
    and people made: the cascade a run uses."""
    local = from_library(library, make_people=make_people)
    tried: dict[str, Model | None] = {}

    def resolve(thing: Thing) -> Resolved | None:
        found = local(thing)
        if found is not None or thing.person is not None or find_model is None:
            return found
        if thing.what not in tried:
            tried[thing.what] = find_model(thing.what)
        model = tried[thing.what]
        return None if model is None else fitted(library, model, thing)

    return resolve


def fitted(library: Library, model: Model, thing: Thing) -> Resolved:
    """A library model made to fit a thing: a family given the settings its words call for
    (an espresso cup, a conference table eight metres long), painted as its words say, and
    stretched to the size given (a family that has a setting for a size takes it there)."""
    look = look_of(thing)
    params = (
        settings_for(library.props[model.model_id], thing)
        if model.model_id in library.props
        else {}
    )
    fit = tuple(
        0.0 if name in params else given
        for name, given in (
            ("width", thing.width),
            ("depth", thing.depth),
            ("height", thing.height),
        )
    )
    if model.file.endswith(PICTURES):
        # A picture is its width, as wide as asked; lying flat, as deep as it is tall.
        w, _, h = model.size
        wide = thing.width or w
        return Resolved(model.model_id, Vec(wide, wide * h / w, 0.002), None, picture=True)
    if not look.paint and not params and not any(fit):
        w, d, h = model.size
        return Resolved(model.model_id, Vec(w, d, h), library.model_file(model.model_id))
    key = f"{model.model_id}~{_digest([look.paint, params, fit])}"
    file = library.model_file(
        model.model_id, key=key, paint=look.paint, params=params, fit=(fit[0], fit[1], fit[2])
    )
    assert file is not None
    w, d, h = file.size
    return Resolved(key, Vec(w, d, h), file)


def settings_for(family: type[Prop], thing: Thing) -> dict[str, str]:
    """A family's settings from a thing's words: a choice named in its words or its looks
    ("espresso cup": style espresso; "material: brass" for a material), a number its looks
    give by name, and its width, depth or height where the family has a setting for them.
    Numbers are kept within the setting's range."""
    looks = {setting.name.lower(): setting.value for setting in thing.looks}
    words = set(re.findall(r"[a-z0-9]+", " ".join([thing.what, *looks.values()]).lower()))
    sizes = {"width": thing.width, "depth": thing.depth, "height": thing.height}
    chosen: dict[str, str] = {}
    for setting in settings(family):
        if setting.options:
            named = looks.get(setting.name)
            picked = (
                named
                if named in setting.options
                else next(
                    (option for option in setting.options if set(option.split("_")) <= words), None
                )
            )
            if picked:
                chosen[setting.name] = picked
        elif setting.low is not None and setting.high is not None:
            value = sizes.get(setting.name) or _number(looks.get(setting.name, ""))
            if value:
                value = min(max(value, setting.low), setting.high)
                chosen[setting.name] = f"{value:g}" if setting.type != "int" else str(round(value))
    return chosen


def _number(text: str) -> float:
    found = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
    return float(found.group()) if found else 0.0


def _search(library: Library, words: str) -> Model | None:
    found = library.search(words)
    return found[0].model if found and found[0].score >= GOOD_MATCH else None


def _person(library: Library, thing: Thing, *, make: bool) -> Resolved:
    """A person: the library's own (`who`, a person made from a design), or one made to the
    scene's description (made now when `make`; until then, the room an average person that
    tall takes, enough to compose and check a shot), in the pose the scene asks."""
    assert thing.person is not None
    person = thing.person
    own = library.models.get(person.who)
    model = own if own is not None and own.postures and own.placeable else None
    if model is None:
        made = recipe(person, thing.height)
        model = character(library, made, make=make)
        model_id, height = character_id(made), made.height
    else:
        model_id, height = model.model_id, model.size[2]
    doing = person.activity or ""
    room = posture(model, person.pose, doing, height)
    # Not made yet: named with nothing to draw it from, so it cannot be rendered by mistake.
    file = library.model_file(model_id) if model else ModelFile(model_id, "", room.size)
    return Resolved(
        model_id, Vec(*room.size), file, pose=person.pose, doing=doing,
        holds={name: Vec(*at) for name, at in room.holds.items()},
        middle=Vec(*room.middle, 0.0),
    )  # fmt: skip


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:8]
