"""A staged scene: what the Visual Director wants in a 3D shot, described, not assembled. It
names the room, the things in it (what each is, how many, how it looks, where it goes in
relation to something else), what they do and how the camera moves; the toolkit finds or
makes every thing and places it (`staging/compose.py`, `docs/staging.md`). Settings are
text, read by each block (`content/blender/blocks/base.read`), so one shape serves every
block."""

from typing import Literal

from pydantic import Field

from content.schemas.base import ImmutableModel
from content.schemas.visuals import Scene, VisualPackage

# Where a thing goes, in relation to its `target` (another thing, or something the room
# offers: a mark, a surface, a piece of furniture, or `floor`).
Relation = Literal[
    "on",  # standing on its top: a phone on the desk
    "scattered_on",  # lying here and there on it, turned every way: papers on the floor
    "stacked_on",  # one on another, on its top: files on the cabinet
    "in_row_on",  # side by side along it: bottles on the shelf
    "beside",  # next to it, on what it stands on: a bin beside the desk
    "in_front_of",  # before it, as it faces: a glass in front of each man
    "behind",
    "around",  # in a ring round it, facing it: guards around the car
    "seated_at",  # on chairs round it, facing it (chairs are added where none are free)
    "against_wall",  # back to a wall, facing into the room
    "at",  # standing on one of the room's marks: a man at the window
    "held_by",  # in a person's hand (a glass, a phone, a document): they are posed to hold it
]


# What a person's hands do. Holding something (a drink, a document, writing on paper, a
# phone) is usually set by what a scene puts in their hand (`held_by`).
Activity = Literal[
    "resting", "lap", "folded", "pointing", "pockets", "drink", "reading", "writing", "phone"
]


class Setting(ImmutableModel):
    name: str
    value: str


class BlockChoice(ImmutableModel):
    """A block by name, and the settings that differ from its defaults."""

    block: str
    settings: list[Setting] = Field(default_factory=list)


class Placement(ImmutableModel):
    relation: Relation
    target: str
    # One for each of the target's copies (a glass in front of each of eight men).
    each: bool = False


class Person(ImmutableModel):
    """Who a person is, for a figure built to fit: a particular person from the library
    (`who`), or anyone of this description. What is left empty varies from one copy to the
    next (eight men at a table are not eight of the same man doing the same thing)."""

    who: str = ""
    sex: Literal["man", "woman"] = "man"
    age: Literal["young", "middle", "old"] | None = None
    build: Literal["slim", "average", "heavy"] | None = None
    dress: Literal["suit", "casual", "uniform", "work"] = "suit"
    pose: Literal["standing", "seated", "walking"] = "standing"
    # What their hands do: resting on the table, in the lap, arms folded, pointing, hands in
    # pockets; holding something is set by what they hold (`held_by`).
    activity: Activity | None = None


class Thing(ImmutableModel):
    """Something in the shot. `what` is plain words for it ("water glass", "oil tanker");
    the toolkit finds a model for it, makes one, or fetches one."""

    thing_id: str
    what: str
    count: int = Field(default=1, ge=1, le=40)
    # Its real height in metres: what a model of any size is scaled to. 0 keeps the model's.
    height: float = Field(default=0.0, ge=0.0, le=200.0)
    # Its width and depth in metres, when they matter (a table eight metres long); 0 keeps
    # the model's proportions.
    width: float = Field(default=0.0, ge=0.0, le=500.0)
    depth: float = Field(default=0.0, ge=0.0, le=500.0)
    # How it looks: colour, material, style, era ("colour: red", "material: brass").
    looks: list[Setting] = Field(default_factory=list)
    place: Placement
    person: Person | None = None


class Action(ImmutableModel):
    """Something that happens: an action block, done by every copy of `who` (each in turn,
    `stagger` of the shot apart)."""

    block: str
    who: str
    settings: list[Setting] = Field(default_factory=list)
    stagger: float = Field(default=0.0, ge=0.0, le=0.5)


class StagePlan(ImmutableModel):
    # The room or place: a layout block, with its settings.
    layout: BlockChoice
    things: list[Thing] = Field(default_factory=list)
    # How much background detail the room is given beyond the things named.
    furnish: Literal["bare", "some", "lived_in"] = "some"
    actions: list[Action] = Field(default_factory=list)
    lights: list[BlockChoice] = Field(default_factory=list)
    # The camera's move; its `subject` may name a thing (every copy is framed).
    camera: BlockChoice


class StagedScene(Scene):
    """A scene that may be a 3D shot. Without `staging` it is drawn as a keyframe."""

    staging: StagePlan | None = None
    # How this scene turns into the next, when joins are rendered: a transition from the
    # catalogue. Empty leaves it to the theme.
    transition: BlockChoice | None = None
    # What the toolkit lacks to stage this scene, when it is left as a keyframe because of
    # it: kept so the missing ability or model can be built later.
    missing: str = ""


class StagedVisualPackage(VisualPackage):
    scenes: list[StagedScene] = Field(min_length=1)  # type: ignore[assignment]
