"""Where a channel's models come from and how they are drawn: only freely usable models are
offered, best match first; an imported model's surfaces take the roles their colours are
nearest; a version of a model is the same shape repainted and resized, made from the
original's file (or code) and carrying its rights."""

import json
import math
from pathlib import Path

import pytest

from content.blender.body import JOINTS, STANDING, TABLE_HEIGHT
from content.blender.job import ActorCall, BlockCall, Job, ModelFile
from content.blender.materials import linear, nearest_role
from content.providers.assets import Candidate, licence_terms
from content.schemas.staging import Thing
from content.staging.catalogue import load_catalogue, with_models
from content.staging.library import Model, Movement, load_library
from content.staging.poses import pose_id
from content.staging.resolve import from_library, with_online
from content.staging.sourcing import TOO_DETAILED, rank
from content.staging.store import Store


@pytest.mark.parametrize(
    ("label", "terms"),
    [
        ("CC0 Public Domain", "CC0"),
        ("Creative Commons Zero v1.0 Universal", "CC0"),
        ("CC Attribution", "CC-BY"),
        ("CC-BY 3.0", "CC-BY"),
        ("Creative Commons Attribution 4.0 International", "CC-BY"),
        ("CC Attribution-ShareAlike", ""),
        ("CC Attribution-NonCommercial", ""),
        ("CC Attribution-NoDerivs", ""),
        ("CC-BY-NC-SA 4.0", ""),
        ("Standard", ""),
    ],
)
def test_only_licences_that_allow_any_use_with_at_most_a_credit_are_accepted(
    label: str, terms: str
) -> None:
    assert licence_terms(label) == terms


def _candidate(title: str, licence: str = "CC0", faces: int = 1000, page: str = "") -> Candidate:
    return Candidate("a source", title, page or f"https://models/{title}", "", "glb", licence,
                     "a maker", faces)  # fmt: skip


def test_a_search_offers_usable_models_once_each_best_match_first() -> None:
    found = [
        _candidate("Office chair with wheels"),
        _candidate("Oil tanker"),
        _candidate("Oil tanker (share alike)", licence=""),
        _candidate("Oil tanker, every rivet", faces=TOO_DETAILED + 1),
        _candidate("Tanker ship", licence="CC-BY"),
        _candidate("Oil tanker", page="https://models/Oil tanker"),
    ]

    shortlist = rank("oil tanker", found)

    assert [c.title for c in shortlist] == ["Oil tanker", "Tanker ship", "Office chair with wheels"]


@pytest.mark.parametrize(
    ("colour", "metallic", "transmission", "role"),
    [
        ("#f4f4f2", 0.0, 0.0, "paper"),  # a white mug
        ("#8e2a24", 0.0, 0.0, "brick"),  # a deep red
        ("#3a2a1a", 0.0, 0.0, "dark_wood"),
        ("#2e5e2e", 0.0, 0.0, "foliage"),
        ("#202020", 0.0, 0.0, "rubber"),
        ("#c0c0c0", 1.0, 0.0, "metal"),  # what makes metal is its finish, not its colour
        ("#ffffff", 0.0, 0.95, "glass"),
    ],
)
def test_an_imported_surface_takes_the_role_it_is_most_like(
    colour: str, metallic: float, transmission: float, role: str
) -> None:
    assert nearest_role(linear(colour), metallic=metallic, transmission=transmission) == role


def test_a_version_is_its_original_repainted_and_resized_with_its_rights(
    tmp_path: Path,
) -> None:
    theme = tmp_path / "channel"
    catalogue = load_catalogue(theme)
    library = catalogue.library
    library.add(
        Model(
            model_id="statue", names=("bust",), describe="A marble bust", size=(0.4, 0.3, 0.6),
            source="sketchfab", licence="CC-BY", page="https://statue", author="a sculptor",
            file="statue.glb",
        )
    )  # fmt: skip
    library.vary("gold_statue", "statue", describe="The bust in gold", paint={"stone": "metal"})
    library.vary(
        "tall_gold_statue", "gold_statue", describe="Taller", paint={"base": "wood"}, height=1.2
    )
    library.vary("red_box", "box", describe="A red box", paint={"card": "brick"})
    with pytest.raises(ValueError, match="no role velvet"):
        library.vary("velvet_box", "box", describe="?", paint={"card": "velvet"})

    job = Job(
        shot_id="s", seconds=1, layout=BlockCall("studio"), camera=BlockCall("hold"),
        look=BlockCall("plain"),
        actors=tuple(
            ActorCall(m, "prop", m) for m in ("tall_gold_statue", "red_box", "box")
        ),
    )  # fmt: skip
    shipped = {m.model_id: m for m in with_models(job, catalogue).models}

    tall = shipped["tall_gold_statue"]
    assert tall.path.endswith("statue.glb") and not tall.prop
    assert tall.paint == {"stone": "metal", "base": "wood"}
    assert tall.fit == (0.0, 0.0, 1.2) and tall.size == (0.8, 0.6, 1.2)
    box = shipped["red_box"]
    assert box.prop == "box" and not box.path and box.paint == {"card": "brick"}
    assert "box" not in shipped  # made in code: Blender builds it from its file
    # Whoever made the original is credited for every version of it.
    assert library.credit("tall_gold_statue") == (
        "A marble bust by a sculptor (sketchfab, CC-BY): https://statue"
    )
    assert library.credit("red_box") == ""


def test_the_catalogue_keeps_one_copy_of_a_file_and_every_step_and_use(tmp_path: Path) -> None:
    store = Store(tmp_path)
    first, second = tmp_path / "a.glb", tmp_path / "b.glb"
    first.write_bytes(b"the same model")
    second.write_bytes(b"the same model")

    assert store.keep_file(first) == store.keep_file(second)
    store.note("vase", "fetched", {"from": "https://models/vase"})
    store.note("vase", "chosen", {"score": 0.8})
    store.used("vase", "video one")
    store.used("vase", "video one")

    assert [step for _, step, _ in store.lineage("vase")] == ["fetched", "chosen"]
    assert store.usage("vase") == ["video one"]


def test_an_old_json_library_is_moved_into_the_catalogue_once(tmp_path: Path) -> None:
    old = {"model_id": "vase", "names": ["urn"], "describe": "A vase", "size": [0.2, 0.2, 0.4],
           "source": "sketchfab", "licence": "CC0", "file": "vase.glb",
           "used_in": ["v1"]}  # fmt: skip
    (tmp_path / "library.json").write_text(json.dumps({"models": [old]}), encoding="utf-8")

    library = load_library(tmp_path)
    again = load_library(tmp_path)

    assert library.get("vase").names == ("urn",) and again.get("vase").licence == "CC0"
    assert not (tmp_path / "library.json").exists()
    assert library.search("urn")[0].model.model_id == "vase"


def test_a_turned_down_model_is_never_found_again(tmp_path: Path) -> None:
    library = load_library(tmp_path)
    library.add(Model(model_id="urn_scan", names=("urn",), describe="A broken scan",
                      size=(0.2, 0.2, 0.4), source="fuel", licence="CC0", file="u.glb",
                      status="auto", score=0.6))  # fmt: skip

    library.veto("urn_scan", "it is a mess")

    assert library.search("urn") == []
    assert load_library(tmp_path).get("urn_scan").status == "vetoed"


def test_what_the_library_lacks_is_looked_for_online_once_and_scaled_to_its_height(
    tmp_path: Path,
) -> None:
    library = load_library(tmp_path)
    asked: list[str] = []

    def find_model(what: str) -> Model | None:
        asked.append(what)
        if what != "traffic cone":
            return None
        cone = Model(model_id="traffic_cone", names=(what,), describe="A toy cone",
                     size=(0.08, 0.08, 0.08), source="fuel", licence="CC0", file="c.glb",
                     status="auto")  # fmt: skip
        library.add(cone, alongside=True)
        return cone

    resolve = with_online(library, find_model)
    cone = {"thing_id": "cone", "what": "traffic cone", "height": 0.7,
            "place": {"relation": "on", "target": "floor"}}  # fmt: skip
    ship = {**cone, "thing_id": "ship", "what": "oil tanker"}

    first = resolve(Thing.model_validate(cone))
    resolve(Thing.model_validate(cone))
    resolve(Thing.model_validate(ship))
    resolve(Thing.model_validate(ship))
    desk = resolve(Thing.model_validate({**cone, "what": "desk", "height": 0}))

    assert first is not None and first.size.z == pytest.approx(0.7)
    assert asked == ["traffic cone", "oil tanker"]  # each looked for once; the desk is on hand
    assert desk is not None and desk.model == "desk"


def _resolved(what: str, **extra: object) -> tuple[str, tuple[float, float, float], ModelFile]:
    library = load_catalogue(None).library
    thing = Thing.model_validate(
        {"thing_id": "t", "what": what, "place": {"relation": "on", "target": "floor"}, **extra}
    )
    found = from_library(library)(thing)
    assert found is not None and found.file is not None
    return found.model, found.file.size, found.file


def test_one_family_makes_every_kind_of_its_thing_from_the_words_for_it() -> None:
    _, espresso, file = _resolved("espresso cup")
    _, mug, _ = _resolved("coffee mug")
    _, flute, _ = _resolved("champagne glass")

    assert file.prop == "cup" and file.params == {"style": "espresso"}
    assert espresso[2] < mug[2]
    assert flute[2] > 0.2  # on its stem


def test_a_family_is_made_to_the_size_asked_and_anything_else_is_stretched_to_it() -> None:
    _, table, file = _resolved("conference table", width=8.0)
    _, desk, desk_file = _resolved("desk", width=2.4)

    assert table[0] == pytest.approx(8.0)
    assert file.params == {"style": "conference", "width": "8"}
    assert file.fit == (0.0, 0.0, 0.0)
    # The desk has no setting for its width: it is stretched, its height kept in proportion.
    assert desk[0] == pytest.approx(2.4) and desk_file.fit == (2.4, 0.0, 0.0)


def test_a_person_is_a_pose_of_recorded_motion_and_until_read_only_takes_room(
    tmp_path: Path,
) -> None:
    library = load_library(tmp_path)
    seated = {"thing_id": "men", "what": "man in a suit", "height": 1.8,
              "person": {"pose": "seated", "activity": "drink"},
              "place": {"relation": "seated_at", "target": "table"}}  # fmt: skip
    thing = Thing.model_validate(seated)
    clip = pose_id("sit")

    before = from_library(library)(thing)
    # A clip as `blender/poses.py` writes one: a figure with its thighs run forward.
    joints = {**STANDING, "knee.L": (0.1, -0.43, 0.94), "knee.R": (-0.1, -0.43, 0.94),
              "ankle.L": (0.1, -0.45, 0.51), "ankle.R": (-0.1, -0.45, 0.51)}  # fmt: skip
    written = tmp_path / "sit.json"
    written.write_text(json.dumps({"frames": [[joints[j] for j in JOINTS]], "fps": 30}))
    kept = Store(tmp_path).keep_file(written)
    library.add(Model(model_id=clip, names=("sit pose",), describe="a man sitting",
                      size=(0.0, 0.0, 0.0), capabilities=("pose",), source="Sketchfab",
                      licence="CC-BY", author="someone", file=kept,
                      movement=Movement(1, 0.0)), alongside=True)  # fmt: skip
    after = from_library(library)(thing)
    shorter = from_library(library)(Thing.model_validate({**seated, "height": 1.6}))

    # Not read yet: the room an average man takes, seated, named so it cannot be drawn.
    assert before is not None and before.model == clip and before.pose == "seated"
    assert before.file is not None and before.file.path == ""
    # Read: measured as the shot will pose him, on the engine's chair, his drink on the
    # usual table.
    assert after is not None and after.file is not None and after.file.path
    assert after.doing == "drink" and after.holds["drink"].z == pytest.approx(TABLE_HEIGHT)
    assert 1.2 < after.size.z < 1.6
    assert shorter is not None and shorter.size.z < after.size.z


def test_poses_taken_for_a_pose_are_used_in_turn_and_a_walk_is_one_loop(tmp_path: Path) -> None:
    from content.blender.api import Figure
    from content.blender.maths import Vec
    from content.staging.poses import chosen, take

    library = load_library(tmp_path)
    standing = Figure({name: Vec(*point) for name, point in STANDING.items()})
    rights = {"source": "Sketchfab", "licence": "CC-BY", "author": "someone", "page": "p"}
    first = take(library, [standing], "seated", name="Sitting Idle", rights=rights)
    second = take(library, [standing], "seated", name="Man Sitting", rights=rights)
    # A walk two steps long, recorded three times over: kept as one loop.
    stride = [Figure({n: p + Vec(0.0, 0.0, 0.05 * math.cos(i * math.tau / 30))
                      for n, p in standing.joints.items()}) for i in range(90)]  # fmt: skip
    walk = take(library, stride, "walking", name="Walk", rights=rights)

    picked = [chosen(library, "seated", n, make=False)[0] for n in range(4)]
    assert [m.model_id for m in picked if m] == [second.model_id, first.model_id] * 2
    assert walk.movement is not None and walk.movement.loop and walk.movement.frames == 30
    # Nothing taken for standing: the engine's own pose, not read yet.
    assert chosen(library, "standing", 0, make=False) == (None, 0.3)
