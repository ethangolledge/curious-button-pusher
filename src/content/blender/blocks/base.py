"""What every block is: a name, a docstring, its settings as a frozen dataclass, what its actors
must be able to do, an example, and a `build` method that uses only `Stage` verbs.

Settings arrive as text (from a storyboard or a job file) and are read here, once, for both
the checks before a render and the render itself."""

import dataclasses
import sys
import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, get_args, get_origin, get_type_hints

from content.blender.api import Stage, Thing
from content.blender.canvas_api import Canvas


@dataclass(frozen=True, slots=True)
class Ref:
    """The name of something in the shot: an actor, a layout's mark, or a layout's path."""

    name: str


@dataclass(frozen=True, slots=True)
class Range:
    """A number's limits, and what it measures, shown to whoever chooses it."""

    low: float
    high: float
    about: str = ""


@dataclass(frozen=True, slots=True)
class About:
    """What a setting means, shown to whoever chooses it."""

    text: str


@dataclass(frozen=True, slots=True)
class ModelName(About):
    """A text setting that names a model from the library (or a prop made in code): the
    model is checked, and its file sent to Blender with the shot."""


class SettingError(ValueError):
    pass


class Block:
    """The base of every kind; a block file defines exactly one subclass of one kind."""

    kind: ClassVar[str]
    name: ClassVar[str]
    # The block's settings: a frozen dataclass, with a default for every optional one.
    settings: ClassVar[type[Any]]
    example: ClassVar[Any]
    # For each actor setting, the capabilities its model must have ({"vehicle": {"vehicle"}}).
    needs: ClassVar[Mapping[str, frozenset[str]]] = {}


class Layout(Block):
    """Where things are: builds the set, and names its marks and paths."""

    kind = "layouts"

    def build(self, stage: Stage, p: Any) -> None:
        raise NotImplementedError


class Actor(Block):
    """Puts a model into the shot as a named actor."""

    kind = "actors"

    def build(self, stage: Stage, p: Any, actor_id: str, model: str) -> None:
        raise NotImplementedError


class Action(Block):
    """What happens over time to the actors."""

    kind = "actions"

    def build(self, stage: Stage, p: Any) -> None:
        raise NotImplementedError


class Move(Block):
    """What the camera does."""

    kind = "moves"

    def build(self, stage: Stage, p: Any) -> None:
        raise NotImplementedError


class Light(Block):
    """A lighting rig."""

    kind = "lights"

    def build(self, stage: Stage, p: Any) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class NoSettings:
    pass


class Prop(Block):
    """A model made in code, offered beside the library's models. Its docstring says what it
    is; `names` are other words for it, so a search finds it however it is asked for. It is
    built standing on the origin, facing −Y, at its usual size; the shot scales and places it."""

    kind = "props"
    settings = NoSettings
    example = NoSettings()
    names: ClassVar[tuple[str, ...]] = ()
    capabilities: ClassVar[frozenset[str]] = frozenset()

    def build(self, stage: Stage, name: str) -> Thing:
        raise NotImplementedError


class Transition(Block):
    """How one picture becomes the next: a small program on the frame, written with `Canvas`
    verbs (`canvas_api.py`) and the shared `patterns`."""

    kind = "transitions"

    def build(self, canvas: Canvas, p: Any) -> None:
        raise NotImplementedError


class Look(Block):
    """How everything is drawn: materials for each role, the world, the render settings, and
    how imported models are restyled. Its settings are the theme's numbers for the feel. A
    look is the one kind of block that uses Blender's own API, so looks are only loaded
    inside Blender."""

    kind = "looks"

    def __init__(self, values: Any, palette: Mapping[str, str]) -> None:
        self.values = values
        self.palette = palette

    def material(self, role: str) -> Any:
        """The material for a role (a Blender material, made once and reused)."""
        raise NotImplementedError

    def restyle(self, obj: Any) -> None:
        """Bring an imported model's own materials into the look."""
        raise NotImplementedError

    def world(self, scene: Any) -> None:
        raise NotImplementedError

    def render(self, scene: Any, quality: str) -> None:
        raise NotImplementedError


# --- Reading settings ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Setting:
    """One setting as a catalogue shows it."""

    name: str
    type: str
    default: str | None
    about: str
    options: tuple[str, ...] = ()
    low: float | None = None
    high: float | None = None


def settings(block: type[Block]) -> list[Setting]:
    hints = get_type_hints(block.settings, include_extras=True)
    out = []
    for field in dataclasses.fields(block.settings):
        base, extras = _unwrap(hints[field.name])
        limits = next((e for e in extras if isinstance(e, Range)), None)
        about = next(
            (e.text for e in extras if isinstance(e, About)), limits.about if limits else ""
        )
        default = None if field.default is dataclasses.MISSING else _text(field.default)
        names_model = any(isinstance(e, ModelName) for e in extras)
        out.append(
            Setting(
                name=field.name,
                type="model" if names_model else _type_name(base),
                default=default,
                about=about,
                options=tuple(str(o) for o in get_args(base))
                if get_origin(base) is Literal
                else (),
                low=limits.low if limits else None,
                high=limits.high if limits else None,
            )
        )
    return out


def read(block: type[Block], given: Mapping[str, Any]) -> Any:
    """A block's settings from text (numbers and yes/no written plainly in JSON are taken as
    their text), with every problem named."""
    known = {setting.name: setting for setting in settings(block)}
    problems = [f"{block.name}: no setting '{name}'" for name in given if name not in known]
    values: dict[str, Any] = {}
    for name, setting in known.items():
        if name not in given:
            if setting.default is None:
                problems.append(f"{block.name}: '{name}' is required")
            continue
        try:
            values[name] = _parse(setting, _text(given[name]))
        except ValueError as exc:
            problems.append(f"{block.name}: {name} {exc}")
    if problems:
        raise SettingError("; ".join(problems))
    return block.settings(**values)


def summary(block: type[Block]) -> str:
    """What a block is, from its file's docstring: its first paragraph, on one line."""
    text = sys.modules[block.__module__].__doc__ or ""
    return " ".join(text.strip().split("\n\n")[0].split())


def refs(params: Any) -> dict[str, str]:
    """Every `Ref` among a block's settings: what in the shot it refers to."""
    return {
        field.name: value.name
        for field in dataclasses.fields(params)
        if isinstance(value := getattr(params, field.name), Ref)
    }


def _unwrap(hint: Any) -> tuple[Any, tuple[Any, ...]]:
    if get_origin(hint) is typing.Annotated:
        base, *extras = get_args(hint)
        return base, tuple(extras)
    return hint, ()


def _type_name(base: Any) -> str:
    if get_origin(base) is Literal:
        return "choice"
    if isinstance(base, types.UnionType):
        raise TypeError("block settings are single types; use a default instead of None")
    return {float: "number", int: "whole number", bool: "yes/no", str: "text", Ref: "name"}[base]


def _text(value: Any) -> str:
    if isinstance(value, Ref):
        return value.name
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _parse(setting: Setting, text: str) -> Any:
    text = text.strip()
    if setting.type == "choice":
        if text not in setting.options:
            raise ValueError(f"must be one of {', '.join(setting.options)}, not '{text}'")
        return text
    if setting.type == "name":
        if not text:
            raise ValueError("needs a name")
        return Ref(text)
    if setting.type == "yes/no":
        if text.lower() not in ("yes", "no", "true", "false"):
            raise ValueError(f"must be yes or no, not '{text}'")
        return text.lower() in ("yes", "true")
    if setting.type in ("text", "model"):
        return text
    try:
        number: float = int(text) if setting.type == "whole number" else float(text)
    except ValueError:
        raise ValueError(f"must be a {setting.type}, not '{text}'") from None
    if (
        setting.low is not None
        and setting.high is not None
        and not (setting.low <= number <= setting.high)
    ):
        raise ValueError(f"must be between {setting.low:g} and {setting.high:g}, not {number:g}")
    return number
