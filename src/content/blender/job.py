"""A render job: everything Blender needs to build and render one shot, as one JSON file.
The pipeline writes it; `worker.py`, inside Blender, reads it. This module is the whole
contract between the two, defined once and imported by both."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

# still: a few frames for a contact sheet; draft: every frame, quickly; final: full quality.
Quality = Literal["still", "draft", "final"]


@dataclass(frozen=True, slots=True)
class BlockCall:
    """A block by name, with its settings as text (read by `blocks.base.read`)."""

    block: str
    settings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActorCall:
    """An actor: its name in the shot, the actor block that places it, and its model (a
    library model or a prop made in code)."""

    actor_id: str
    block: str
    model: str
    settings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelFile:
    """A library model the shot uses: its file (or, for a version of a prop made in code, that
    prop), its real width, depth and height in metres, and how its surfaces are painted:
    each part, material or role named (`seat`, `Body_Mat`, `wood`) drawn as another role. A
    version made at another size is scaled to `height`."""

    model_id: str
    path: str
    size: tuple[float, float, float]
    prop: str = ""
    paint: dict[str, str] = field(default_factory=dict)
    height: float = 0.0
    # The library model it is made from, when it is made to fit a scene (what it can do).
    base: str = ""
    # A family made to fit: its settings (a cup's style, a table's length).
    params: dict[str, str] = field(default_factory=dict)
    # Stretched to this width, depth and height in metres (0 for any: in proportion).
    fit: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Grade:
    """How a scene's feeling shifts the look: stops of exposure, and warmth from −1 (cold) to
    1 (warm). Applied after the look, so every look takes it the same way."""

    exposure: float = 0.0
    warmth: float = 0.0


NEUTRAL = Grade()


@dataclass(frozen=True, slots=True)
class Job:
    shot_id: str
    seconds: float
    layout: BlockCall
    camera: BlockCall
    look: BlockCall
    actors: tuple[ActorCall, ...] = ()
    actions: tuple[BlockCall, ...] = ()
    lights: tuple[BlockCall, ...] = ()
    # Names for sets of actors (every copy of a thing), so a move or an action can take
    # them together: an orbit round "the men" frames all of them.
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    models: tuple[ModelFile, ...] = ()
    palette: dict[str, str] = field(default_factory=dict)
    grade: Grade = field(default_factory=Grade)
    # A channel's own blocks and looks (`themes/<name>/blender`), beside the engine's.
    channel_blocks: tuple[str, ...] = ()
    width: int = 1080
    height: int = 1920
    fps: int = 30
    quality: Quality = "draft"
    # The frames to render for a still; empty renders every frame.
    frames: tuple[int, ...] = ()
    seed: int = 1
    # Also save the built scene as a .blend, to open and look around in Blender.
    save_scene: bool = False

    @property
    def frame_count(self) -> int:
        return max(1, round(self.seconds * self.fps))

    def dumps(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def loads(cls, text: str) -> "Job":
        data: dict[str, Any] = json.loads(text)
        data["layout"] = BlockCall(**data["layout"])
        data["camera"] = BlockCall(**data["camera"])
        data["look"] = BlockCall(**data.get("look", {"block": "plain"}))
        data["grade"] = Grade(**data.get("grade", {}))
        data["actors"] = tuple(ActorCall(**actor) for actor in data.get("actors", ()))
        data["actions"] = tuple(BlockCall(**action) for action in data.get("actions", ()))
        data["lights"] = tuple(BlockCall(**light) for light in data.get("lights", ()))
        data["groups"] = {name: tuple(ids) for name, ids in data.get("groups", {}).items()}
        data["models"] = tuple(
            ModelFile(
                **{**model, "size": tuple(model["size"]), "fit": tuple(model.get("fit", (0, 0, 0)))}
            )
            for model in data.get("models", ())
        )
        data["channel_blocks"] = tuple(data.get("channel_blocks", ()))
        data["frames"] = tuple(data.get("frames", ()))
        return cls(**data)

    @classmethod
    def read(cls, path: Path) -> "Job":
        return cls.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class Join:
    """A transition rendered between two pictures: the last frame of one scene and the first
    of the next, both at the frame's size."""

    join_id: str
    seconds: float
    transition: BlockCall
    first: str
    last: str
    width: int = 1080
    height: int = 1920
    fps: int = 30
    # A channel's own transitions (`themes/<name>/blender`), beside the engine's.
    channel_blocks: tuple[str, ...] = ()
    # The frames to render for a still; empty renders every frame.
    frames: tuple[int, ...] = ()
    # When a side is a moving shot: the folder of its frames, and the frame the join starts
    # on, so the picture keeps moving through the join instead of holding still.
    first_frames: str = ""
    first_from: int = 1
    last_frames: str = ""
    last_from: int = 1

    @property
    def frame_count(self) -> int:
        return max(1, round(self.seconds * self.fps))

    def dumps(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def loads(cls, text: str) -> "Join":
        data: dict[str, Any] = json.loads(text)
        data["transition"] = BlockCall(**data["transition"])
        data["channel_blocks"] = tuple(data.get("channel_blocks", ()))
        data["frames"] = tuple(data.get("frames", ()))
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Report:
    """What the worker writes beside the frames."""

    shot_id: str
    frames: list[str]
    issues: list[str]
    seconds_building: float
    seconds_rendering: float
    blend: str | None = None

    def dumps(self) -> str:
        return json.dumps(asdict(self), indent=2)
