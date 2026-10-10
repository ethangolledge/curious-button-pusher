"""3D staging without Blender: every block builds its example and does exactly what it did
before (a snapshot of its calls on the stage), shots are checked before anything renders,
and the model library finds things however they are asked for, and never holds one twice."""

import json
import math
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pytest

from content.blender.api import Box, Mark
from content.blender.blocks.base import (
    Action,
    Actor,
    Block,
    Layout,
    Light,
    Move,
    Prop,
    read,
    settings,
    summary,
)
from content.blender.job import ActorCall, BlockCall, Job
from content.blender.maths import (
    FRONT,
    Quat,
    Spline,
    Vec,
    angle_between,
    axis_angle,
    even,
    limit_turn,
)
from content.blender.registry import KINDS, RegistryError, discover
from content.blender.rehearsal import RehearsalStage
from content.staging.catalogue import check, load_catalogue
from content.staging.library import Model, load_library
from content.staging.templates import TEMPLATES, render

SNAPSHOTS = Path(__file__).parent / "snapshots" / "staging"
REGISTRY = discover()
BLOCKS = [(kind, name) for kind in KINDS for name in sorted(REGISTRY.blocks[kind])]


def _stage(registry: Any = REGISTRY) -> RehearsalStage:
    """A stage with what block examples refer to: a `centre` mark on a table-top, an
    `across` and a `road` path, a `thing` and a `car` already cast."""
    stage = RehearsalStage(frames=60, props=registry.props())
    top = Box(Vec(-0.6, -0.4, 0), Vec(0.6, 0.4, 0.75))
    stage.mark(Mark("centre", Vec(0, 0, 0), FRONT, top))
    stage.path("across", [Vec(-3, -1, 0), Vec(0, 0, 0), Vec(3, -1, 0)])
    stage.path("road", [Vec(-20, -2, 0), Vec(20, -2, 0)])
    stage.cast("thing", stage.shape("box", Vec(0.3, 0.3, 0.3), Vec(), role="card", name="thing"))
    stage.cast("car", stage.model("car", name="car"))
    return stage


def _build(block: type[Block], stage: RehearsalStage) -> None:
    example = block.example
    if issubclass(block, Actor):
        block().build(stage, example, "actor", "desk")
    elif issubclass(block, Prop):
        block().build(stage, f"{block.name}_built")
    else:
        assert issubclass(block, (Layout, Action, Move, Light))
        block().build(stage, example)


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float):
        return round(value, 3) + 0.0
    return value


@pytest.mark.parametrize(("kind", "name"), BLOCKS, ids=[f"{k}/{n}" for k, n in BLOCKS])
def test_every_block_is_described_and_builds_exactly_as_it_did(kind: str, name: str) -> None:
    block = REGISTRY.get(kind, name)
    assert summary(block), f"{name}: its file needs a docstring saying what it is"
    for setting in settings(block):
        assert setting.default is not None or setting.type == "name", (
            f"{name}.{setting.name} needs a default"
        )
    assert isinstance(block.example, block.settings)

    stage = _stage()
    before = len(stage.calls)
    _build(block, stage)
    calls = _plain(stage.calls[before:])

    snapshot = SNAPSHOTS / f"{kind}-{name}.json"
    if os.environ.get("UPDATE_SNAPSHOTS") or not snapshot.exists():
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        # One call a line: a change shows as the lines that differ.
        lines = ",\n".join(json.dumps(call, separators=(",", ":")) for call in calls)
        snapshot.write_text(f"[\n{lines}\n]\n", encoding="utf-8")
    assert calls == json.loads(snapshot.read_text(encoding="utf-8")), (
        f"{name} now builds differently. If that was meant: UPDATE_SNAPSHOTS=1 pytest -k {name}"
    )


def test_settings_are_read_from_text_with_every_problem_named() -> None:
    orbit = REGISTRY.get("moves", "orbit")

    chosen = read(orbit, {"subject": "desk", "degrees": "360", "framing": "close"})

    assert (chosen.subject.name, chosen.degrees, chosen.framing) == ("desk", 360.0, "close")
    with pytest.raises(ValueError) as problem:
        read(orbit, {"degrees": "900", "framing": "tight", "speed": "1"})
    message = str(problem.value)
    assert "'subject' is required" in message
    assert "between -720 and 720" in message and "one of wide, medium, close, detail" in message
    assert "no setting 'speed'" in message


def _job(**changes: Any) -> Job:
    shot = {
        "shot_id": "test", "seconds": 2.0, "layout": BlockCall("office"),
        "look": BlockCall("plain"), "camera": BlockCall("orbit", {"subject": "desk"}),
        "actors": (ActorCall("phone", "prop", "telephone", {"at": "desk_top"}),),
        "lights": (BlockCall("lamp", {"at": "desk_lamp"}),),
    }  # fmt: skip
    return Job(**{**shot, **changes})


def test_a_good_shot_passes_the_check_and_survives_its_file() -> None:
    job = _job()

    assert check(job, load_catalogue(None)) == []
    assert Job.loads(job.dumps()) == job


@pytest.mark.parametrize(
    ("changes", "complaint"),
    [
        ({"camera": BlockCall("swoop", {})}, "no move called 'swoop'"),
        ({"camera": BlockCall("orbit", {"subject": "desk", "lens": "500"})}, "between 14 and 135"),
        ({"camera": BlockCall("orbit", {"subject": "sofa"})}, "no mark 'sofa'"),
        (
            {"actors": (ActorCall("phone", "prop", "teleporter", {"at": "desk_top"}),)},
            "no model 'teleporter'",
        ),
        (
            {"actions": (BlockCall("drive", {"vehicle": "phone", "path": "across"}),)},
            "'phone' is a telephone, which is not vehicle",
        ),
    ],
    ids=["unknown block", "setting out of range", "missing mark", "unknown model", "cannot drive"],
)
def test_a_shot_with_a_mistake_is_caught_before_rendering(
    changes: dict[str, Any], complaint: str
) -> None:
    issues = check(_job(**changes), load_catalogue(None))

    assert any(complaint in issue for issue in issues), issues


@pytest.mark.parametrize(
    ("asked", "found"),
    [
        ("sedan", "car"),
        ("a 1970s four-door saloon car", "car"),
        ("whisky glass", "glass"),
        ("dossier", "folder"),
        ("filing cabinets", "filing_cabinet"),
        ("bookshelves", "bookcase"),
        ("boardroom table", "long_table"),
    ],
)
def test_a_model_is_found_however_it_is_asked_for(asked: str, found: str) -> None:
    assert load_library(None).search(asked)[0].model.model_id == found


def _model(model_id: str, *names: str) -> Model:
    return Model(
        model_id,
        names,
        "A test model.",
        (0.1, 0.1, 0.1),
        source="Test",
        licence="CC0",
        file=f"{model_id}.glb",
    )


def test_the_library_never_holds_one_thing_twice_under_another_name(tmp_path: Path) -> None:
    library = load_library(tmp_path)
    library.add(_model("typewriter", "type writer"))

    with pytest.raises(ValueError, match="already in the library as 'typewriter'"):
        library.add(_model("old_typewriter", "typewriter"))
    with pytest.raises(ValueError, match="already in the library as 'car'"):
        library.add(_model("saloon_car", "sedan"))

    library.name("typewriter", "writing machine")
    again = load_library(tmp_path)
    assert again.search("writing machine")[0].model.model_id == "typewriter"
    assert again.get("typewriter").licence == "CC0"


def test_a_channel_block_with_an_engine_name_is_refused(tmp_path: Path) -> None:
    (tmp_path / "moves").mkdir()
    (tmp_path / "moves" / "orbit.py").write_text(render("moves", "orbit"), encoding="utf-8")

    with pytest.raises(RegistryError, match="cannot replace an engine block"):
        discover([tmp_path])


@pytest.mark.parametrize("kind", sorted(TEMPLATES))
def test_every_template_starts_a_block_that_loads_and_builds(tmp_path: Path, kind: str) -> None:
    (tmp_path / kind).mkdir()
    (tmp_path / kind / "fresh_block.py").write_text(render(kind, "fresh_block"), encoding="utf-8")

    registry = discover([tmp_path])
    block = registry.get(kind, "fresh_block")
    _build(block, _stage(registry))


def test_no_turn_snaps_and_a_path_is_walked_at_an_even_pace() -> None:
    turns = [Quat(), axis_angle(Vec(0, 0, 1), 170)]

    limited = limit_turn(turns, 12)
    walked = even(Spline((Vec(), Vec(1, 0, 0), Vec(10, 0, 0))))
    steps = [
        math.dist(walked.at(i / 10).tuple(), walked.at((i + 1) / 10).tuple()) for i in range(10)
    ]

    assert angle_between(limited[0], limited[1]) == pytest.approx(12)
    assert max(steps) - min(steps) < 0.05
