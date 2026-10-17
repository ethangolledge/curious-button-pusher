"""People's motions: free motion capture fetched one take at a time and kept as library
motions, each known by exactly how it was taken, and a walking person's travel played at the
pace of their own walk."""

import io
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from content.blender.job import ModelFile
from content.blender.maths import Vec
from content.providers import motions as recordings
from content.schemas.staging import StagePlan, Thing
from content.staging import motions
from content.staging.catalogue import load_catalogue
from content.staging.compose import Resolved, compose
from content.staging.library import load_library

CATALOGUE = load_catalogue(None)


def test_a_cmu_take_is_fetched_from_its_subjects_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as out:
        out.writestr("113_15.bvh", "HIERARCHY")

    def get(url: str, headers: dict[str, str] | None = None) -> bytes:
        asked.append(url)
        return zipped.getvalue()

    monkeypatch.setattr(recordings, "_get", get)

    first = recordings.fetch("cmu", "113_15", tmp_path)
    again = recordings.fetch("cmu", "113_15", tmp_path)

    assert asked == [f"{recordings.CMU_MIRROR}/Sequence-113-128/113/Data/113_15.zip"]
    assert first == again and first.read_text() == "HIERARCHY"


def test_a_motion_taken_differently_is_another_motion(monkeypatch: pytest.MonkeyPatch) -> None:
    before = motions.motion_id("sit")
    clips = {**motions.CLIPS, "sit": replace(motions.CLIPS["sit"], start=2.0)}
    monkeypatch.setattr(motions, "CLIPS", clips)

    assert motions.motion_id("sit") != before
    assert motions.motion_id("sit").startswith("motion_sit_")


def test_a_motion_not_made_is_not_made_without_leave(tmp_path: Path) -> None:
    library = load_library(tmp_path)

    assert motions.motion(library, "walk", make=False) is None
    assert motions.stance(library, "seated", make=False) is None
    assert "not made yet" in motions.describe(library)


def _walker(thing: Thing) -> Resolved | None:
    if thing.person is None:
        return None
    gait = ModelFile("motion_walk_test", "walk.blend", (0.0, 0.0, 0.0))
    return Resolved("person_test", Vec(0.5, 0.5, 1.8), pose="walking", gait=gait, stride=0.9)


def _walk(settings: list[dict[str, Any]]) -> dict[str, str]:
    plan = StagePlan.model_validate({
        "layout": {"block": "corridor"},
        "things": [{"thing_id": "aide", "what": "man", "person": {"pose": "walking"},
                    "place": {"relation": "at", "target": "start"}}],
        "furnish": "bare",
        "actions": [{"block": "travel", "who": "aide", "settings": [
            {"name": "actor", "value": "aide"}, {"name": "path", "value": "corridor"},
            *settings]}],
        "camera": {"block": "hold"},
    })  # fmt: skip
    shot = compose(plan, CATALOGUE.registry, _walker, seed="test")
    assert any(m.model_id == "motion_walk_test" for m in shot.models)
    return shot.actions[0].settings


def test_a_walking_person_travels_at_the_pace_of_their_own_walk() -> None:
    walking = _walk([])

    assert walking["gait"] == "motion_walk_test"
    assert float(walking["stride"]) == pytest.approx(0.9)
    assert float(walking["speed"]) == pytest.approx(0.9)


def test_a_scene_that_says_how_fast_is_obeyed_and_the_walk_keeps_up() -> None:
    hurrying = _walk([{"name": "speed", "value": "1.6"}])

    # The walk is played faster to keep pace (`actions/travel.py`), never left to slide.
    assert hurrying["speed"] == "1.6" and float(hurrying["stride"]) == pytest.approx(0.9)
