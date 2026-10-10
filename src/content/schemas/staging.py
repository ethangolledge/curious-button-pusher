"""A staged scene: the 3D shot the Visual Director plans for a scene, named from the
catalogue of blocks and models (`docs/staging.md`). Settings are text, read by each block
(`content/blender/blocks/base.read`), so one plan shape serves every block."""

from pydantic import Field

from content.schemas.base import ImmutableModel
from content.schemas.visuals import Scene, VisualPackage


class Setting(ImmutableModel):
    name: str
    value: str


class BlockChoice(ImmutableModel):
    """A block by name, and the settings that differ from its defaults."""

    block: str
    settings: list[Setting] = Field(default_factory=list)


class StagedActor(ImmutableModel):
    """Something placed in the shot: its name in the shot, the actor block that places it,
    and the model it is (a library model or a prop made in code, by id)."""

    actor_id: str
    block: str
    model: str
    settings: list[Setting] = Field(default_factory=list)


class StagePlan(ImmutableModel):
    layout: BlockChoice
    actors: list[StagedActor] = Field(default_factory=list)
    actions: list[BlockChoice] = Field(default_factory=list)
    lights: list[BlockChoice] = Field(default_factory=list)
    camera: BlockChoice


class StagedScene(Scene):
    """A scene that may be a 3D shot. Without `staging` it is drawn as a keyframe."""

    staging: StagePlan | None = None
    # What the toolkit lacks to stage this scene, when it is left as a keyframe because of
    # it: kept so the missing ability or model can be built later.
    missing: str = ""


class StagedVisualPackage(VisualPackage):
    scenes: list[StagedScene] = Field(min_length=1)  # type: ignore[assignment]
