"""Composing a shot from a description: every copy of every thing placed by its relation, on
what it should stand on, clear of everything else and inside the room; what cannot be found
said plainly; an action given to every copy in turn; and people varied, each holding what
they are given in their hand."""

import math
from typing import Any

from content.blender.api import Box
from content.blender.blocks.base import Layout
from content.blender.maths import UP, Vec, axis_angle
from content.blender.rehearsal import RehearsalStage
from content.schemas.staging import Person, StagePlan, Thing
from content.staging.catalogue import load_catalogue
from content.staging.compose import Composition, Resolved, compose
from content.staging.resolve import from_library, look_of

CATALOGUE = load_catalogue(None)
RESOLVE = from_library(CATALOGUE.library)


def _compose(layout: str, things: list[dict[str, Any]], **extra: Any) -> Composition:
    plan = StagePlan.model_validate(
        {
            "layout": {"block": layout},
            "things": things,
            "furnish": "bare",
            "camera": {"block": "hold"},
            **extra,
        }
    )
    return compose(plan, CATALOGUE.registry, RESOLVE, seed="test")


def _where(shot: Composition, actor_id: str) -> Vec:
    actor = next(a for a in shot.actors if a.actor_id == actor_id)
    return Vec(*(float(actor.settings[axis]) for axis in "xyz"))


def _thing(
    thing_id: str, what: str, relation: str, target: str, *, each: bool = False, **extra: Any
) -> dict[str, Any]:
    place = {"relation": relation, "target": target, "each": each}
    return {"thing_id": thing_id, "what": what, "place": place, **extra}


def _furniture(layout: str, name: str) -> Box:
    stage = RehearsalStage(frames=1, props=CATALOGUE.registry.props())
    block = CATALOGUE.registry.get("layouts", layout)
    assert issubclass(block, Layout)
    block().build(stage, block.example)
    return stage.bounds(stage.actor(name))


def test_people_take_the_rooms_seats_then_chairs_are_drawn_up_for_the_rest() -> None:
    shot = _compose(
        "boardroom",
        [_thing("men", "man in a suit", "seated_at", "table", count=11,
                person={"pose": "seated"})],
    )  # fmt: skip

    men = [a for a in shot.actors if a.actor_id.startswith("men_")]
    added = [a for a in shot.actors if a.actor_id.endswith("_added")]
    assert len(men) == 11 and shot.groups["men"] == tuple(a.actor_id for a in men)
    # The boardroom has nine seats (four a side and the head): two chairs are added.
    assert len(added) == 2
    assert {a.model for a in men} == {"seated_person"}


def test_a_glass_goes_on_the_table_in_front_of_each_man() -> None:
    shot = _compose(
        "boardroom",
        [
            _thing("men", "man", "seated_at", "table", count=8, person={"pose": "seated"}),
            _thing("glasses", "water glass", "in_front_of", "men", each=True),
        ],
    )

    men = [_where(shot, f"men_{i}") for i in range(8)]
    for index in range(8):
        glass = _where(shot, f"glasses_{index}")
        assert glass.z == _furniture("boardroom", "table").top  # on the table, not the floor
        nearest = min(range(8), key=lambda m: (men[m] - glass).flat().length())
        assert nearest == index


def test_things_on_a_surface_stand_on_it_inside_its_edges_and_clear_of_each_other() -> None:
    shot = _compose(
        "office",
        [
            _thing("papers", "document", "scattered_on", "desk", count=6),
            _thing("phone", "telephone", "on", "desk"),
            _thing("files", "folder", "stacked_on", "desk", count=4),
        ],
    )

    boxes = _boxes(shot)
    desk = _furniture("office", "desk")
    for actor_id, box in boxes.items():
        assert box.low.z >= desk.top - 0.001, actor_id
        assert desk.low.x - 0.01 <= box.low.x and box.high.x <= desk.high.x + 0.01, actor_id
    stack = sorted(_where(shot, f"files_{i}").z for i in range(4))
    assert all(b > a for a, b in zip(stack, stack[1:], strict=False))
    loose = {k: v for k, v in boxes.items() if not k.startswith("files")}
    for a, box in loose.items():
        for b, other in loose.items():
            if a < b:
                assert not _shrunk(box).overlaps(other), (a, b)


def test_a_thing_nobody_has_is_named_as_missing() -> None:
    shot = _compose("street", [_thing("ship", "oil tanker", "at", "kerb")])

    assert shot.missing == ["model: oil tanker"]


def test_an_action_is_given_to_every_copy_each_a_little_later() -> None:
    shot = _compose(
        "office",
        [_thing("cash", "banknote bundle", "on", "desk", count=3)],
        actions=[{"block": "turn", "who": "cash", "stagger": 0.1,
                  "settings": [{"name": "actor", "value": "cash"},
                               {"name": "start", "value": "0.2"}]}],
    )  # fmt: skip

    assert [call.settings["actor"] for call in shot.actions] == ["cash_0", "cash_1", "cash_2"]
    assert [float(call.settings["start"]) for call in shot.actions] == [0.2, 0.3, 0.4]


def test_a_lived_in_room_gains_furniture_against_its_walls_and_things_on_its_desk() -> None:
    plan = {"layout": {"block": "office"}, "things": [], "camera": {"block": "hold"}}
    bare = compose(StagePlan.model_validate({**plan, "furnish": "bare"}), CATALOGUE.registry,
                   RESOLVE, seed="s")  # fmt: skip
    lived = compose(StagePlan.model_validate({**plan, "furnish": "lived_in"}), CATALOGUE.registry,
                    RESOLVE, seed="s")  # fmt: skip

    assert bare.actors == []
    models = {a.model.split("~")[0] for a in lived.actors}  # a family made to fit: "cup~…"
    assert {"bookcase", "filing_cabinet", "cup"} <= models


def test_words_for_a_things_look_become_the_role_it_is_drawn_in() -> None:
    def role(*looks: str) -> str:
        thing = _thing("t", "chair", "on", "floor", looks=[
            {"name": k, "value": v} for k, v in (look.split(":") for look in looks)])  # fmt: skip
        return look_of(Thing.model_validate(thing)).role

    assert role("material: brass") == "metal"
    assert role("colour: red") == "brick"
    assert role("colour: black", "material: leather") == "leather"  # the material wins
    assert role("finish: gloss") == ""


def _boxes(shot: Composition) -> dict[str, Box]:
    sizes = {m.model_id: m.size for m in CATALOGUE.library.models.values()}
    out = {}
    for actor in shot.actors:
        w, d, h = sizes[actor.model]
        at = Vec(*(float(actor.settings[axis]) for axis in "xyz"))
        turn = math.radians(float(actor.settings["heading"]))
        c, s = abs(math.cos(turn)), abs(math.sin(turn))
        half = Vec((c * w + s * d) / 2, (s * w + c * d) / 2, 0)
        out[actor.actor_id] = Box(at - half, at + half + Vec(0, 0, h))
    return out


def _shrunk(box: Box) -> Box:
    return Box(box.low + Vec(0.01, 0.01, 0.01), box.high - Vec(0.01, 0.01, 0.01))


def test_a_thing_too_big_for_where_it_was_asked_is_said_not_squeezed_in() -> None:
    shot = _compose("office", [_thing("crate", "box", "on", "desk", width=2.5, depth=1.2)])

    assert shot.missing == ["room: no space for box on desk"]
    assert shot.actors == []


class _People:
    """Resolves people as figures posed for what their hands do (a holder's glass 0.4 m in
    front of their feet), noting who was asked for; anything else as the library has it."""

    def __init__(self) -> None:
        self.asked: list[Person] = []

    def __call__(self, thing: Thing) -> Resolved | None:
        if thing.person is None:
            return RESOLVE(thing)
        self.asked.append(thing.person)
        holds = {"drink": Vec(0.0, -0.4, 0.8)} if thing.person.activity == "drink" else {}
        return Resolved("seated_person", Vec(0.5, 0.5, 1.3), seated=True, holds=holds)


def _people_compose(things: list[dict[str, Any]], resolve: _People) -> Composition:
    plan = StagePlan.model_validate(
        {"layout": {"block": "boardroom"}, "things": things, "furnish": "bare",
         "camera": {"block": "hold"}}
    )  # fmt: skip
    return compose(plan, CATALOGUE.registry, resolve, seed="test")


def test_a_group_left_open_is_varied_with_no_two_neighbours_doing_the_same() -> None:
    people = _People()
    _people_compose(
        [_thing("men", "man", "seated_at", "table", count=8, person={"pose": "seated"})], people
    )

    men = people.asked[-8:]
    activities = [m.activity for m in men]
    assert all(a != b for a, b in zip(activities, activities[1:], strict=False))
    assert len({m.age for m in men}) > 1 and len({m.build for m in men}) > 1


def test_three_glasses_held_by_men_are_three_men_each_with_one_in_his_hand() -> None:
    people = _People()
    shot = _people_compose(
        [
            _thing("men", "man", "seated_at", "table", count=8, person={"pose": "seated"}),
            _thing("glasses", "water glass", "held_by", "men", count=3),
        ],
        people,
    )

    activities = [m.activity for m in people.asked[-8:]]
    assert activities[:3] == ["drink"] * 3 and "drink" not in activities[3:]
    for index in range(3):
        man, glass = _where(shot, f"men_{index}"), _where(shot, f"glasses_{index}")
        actor = next(a for a in shot.actors if a.actor_id == f"men_{index}")
        turn = axis_angle(UP, float(actor.settings["heading"]))
        assert (glass - (man + turn.rotate(Vec(0.0, -0.4, 0.8)))).length() < 0.01
