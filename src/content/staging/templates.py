"""The starting point for a new block, one per kind: `content staging new <kind> <name>`
writes it, ready to fill in. Each is the smallest complete block of its kind."""

TEMPLATES: dict[str, str] = {
    "moves": '''"""TODO: what the camera does, in a sentence a director would use."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Framing, Shot, around, film
from content.blender.maths import Still
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("an actor or a mark")]
    framing: Framing = "medium"
    lens: Annotated[float, Range(14, 135, "mm")] = 35.0


class {Name}(Move):
    name = "{name}"
    settings = Settings
    example = Settings(subject=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.subject.name)
        stand = around(stage, box, p.framing, p.lens, front(stage, p.subject.name), 10.0)
        shot = Shot(Still(stand.position), Still(box.centre), stand.lens, stand.lens)
        film(stage, shot, watching=box)
''',
    "actions": '''"""TODO: what happens, in a sentence a director would use."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Pose, Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.maths import progress


@dataclass(frozen=True)
class Settings:
    actor: Annotated[Ref, About("the actor it happens to")]
    start: Annotated[float, Range(0, 1, "when it starts, as a fraction of the shot")] = 0.0
    end: Annotated[float, Range(0, 1, "when it ends, as a fraction of the shot")] = 1.0


class {Name}(Action):
    name = "{name}"
    settings = Settings
    example = Settings(actor=Ref("thing"))

    def build(self, stage: Stage, p: Settings) -> None:
        actor = stage.actor(p.actor.name)
        rest = stage.poses(actor)[0]
        amounts = progress(stage.frames, "in_out", p.start, p.end)
        stage.animate(actor, [Pose(i + 1, rest.at, rest.rotation) for i, _ in enumerate(amounts)])
''',
    "layouts": '''"""TODO: the place, in a sentence. Marks: TODO. Paths: TODO."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Mark, Stage
from content.blender.blocks.base import Layout, Range
from content.blender.maths import FRONT, Vec
from content.blender.sets import room


@dataclass(frozen=True)
class Settings:
    width: Annotated[float, Range(2, 30, "metres")] = 5.0


class {Name}(Layout):
    name = "{name}"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        room(stage, p.width, 4.0, 2.8)
        stage.mark(Mark("TODO", Vec(), FRONT))
''',
    "lights": '''"""TODO: the light, in a sentence."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Light, Range, Ref
from content.blender.maths import Vec
from content.blender.motion import where


@dataclass(frozen=True)
class Settings:
    over: Annotated[Ref, About("an actor or mark")] = Ref("centre")
    colour: Annotated[str, About("hex")] = "#fff4e6"
    power: Annotated[float, Range(1, 5000, "watts")] = 200.0


class {Name}(Light):
    name = "{name}"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.over.name)
        at = box.centre + Vec(0, 0, 2)
        stage.light("point", name=f"{name}_{{p.over.name}}", at=at, colour=p.colour, power=p.power)
''',
    "actors": '''"""TODO: how this actor is placed, in a sentence."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Actor, Ref
from content.blender.sets import stand


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("a mark in the layout")]


class {Name}(Actor):
    name = "{name}"
    settings = Settings
    example = Settings(at=Ref("centre"))

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        thing = stage.model(model, name=actor_id)
        stand(stage, thing, stage.find_mark(p.at.name))
        stage.cast(actor_id, thing)
''',
    "props": '''"""TODO: what it is, in a sentence (searches read this)."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class {Name}(Prop):
    name = "{name}"
    names = ("TODO: other words for it",)

    def build(self, stage: Stage, name: str) -> Thing:
        thing = stage.group(name)
        size = Vec(0.3, 0.3, 0.3)
        stage.shape("box", size, Vec(), role="wood", name=f"{{name}}.body", parent=thing)
        return thing
''',
}


def render(kind: str, name: str) -> str:
    """The template with the block's name in it; `{{` and `}}` are braces the new file keeps."""
    title = "".join(part.title() for part in name.split("_"))
    text = TEMPLATES[kind].replace("{{", "\0").replace("}}", "\1")
    text = text.replace("{Name}", title).replace("{name}", name)
    return text.replace("\0", "{").replace("\1", "}")
