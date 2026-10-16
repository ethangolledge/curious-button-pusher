"""Designs: a person, place or object in several scenes is drawn once in the channel's look, and
every keyframe that shows it, in this video and later ones, is drawn from that design."""

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from content.config import load_config
from content.judging.judge import Judge
from content.production.media import FakeMediaProvider
from content.production.stages.references import References
from content.providers import sam3d
from content.providers.fake import FakeDecisionProvider
from content.schemas.references import ReferenceRequest, ReferenceSet
from content.schemas.visuals import Scene, SceneAnchor, VisualPackage
from content.staging.designs import (
    Designs,
    design_id,
    make_models,
    mask_problems,
    waiting_for_models,
)
from content.storage import LocalStore
from content.theme import load_theme
from content.workflow.demo import demo_answer

ROOT = Path(__file__).parents[1]
LAMP = ReferenceRequest(
    ref_id="lamp", kind="object", query="The brass lamp", unit_ids=["u1"], purpose=""
)


def _scene(scene_id: str, *refs: str) -> Scene:
    anchor = SceneAnchor(
        subject="a desk",
        setting="a study",
        composition="wide",
        key_elements=[],
        light_and_colour="",
    )
    return Scene(
        scene_id=scene_id, script_unit_ids=["u1"], purpose="", visual_function="show",
        evidence_presentation="reconstruction", anchor=anchor, camera="push_in", motion="",
        morph_bridge="", reference_ids=list(refs),
    )  # fmt: skip


def _studio(
    tmp_path: Path, failing: frozenset[str] = frozenset()
) -> tuple[References, FakeMediaProvider]:
    theme_root = tmp_path / "theme"
    if not theme_root.exists():
        shutil.copytree(ROOT / "themes/starter", theme_root)
    config = load_config(ROOT / "config/config.fake-video.json")
    assert config.production is not None
    production = replace(config.production, cache_directory=tmp_path / "cache")
    attempts = iter(range(100))

    def answer(question_id: str, state: Any) -> dict[str, Any]:
        # A question named in `failing` fails on the first design drawn, then passes.
        if question_id in failing and next(attempts) == 0:
            return {"kind": "noul", "noul": 0.05}
        return demo_answer(question_id, state)

    media = FakeMediaProvider()
    studio = References(
        config=production,
        theme=load_theme(theme_root),
        media=media,
        judge=Judge(FakeDecisionProvider(answer), config.decisions),
        image_sources=[],
    )
    return studio, media


def _found(request: ReferenceRequest = LAMP) -> dict[str, ReferenceSet]:
    return {request.ref_id: ReferenceSet(request=request, relevant=True, candidates=[], chosen=[])}


def _storyboard(*scenes: Scene) -> VisualPackage:
    return VisualPackage(overall_visual_direction="", scenes=list(scenes), continuity_notes=[])


def test_a_thing_in_two_scenes_is_designed_once_and_reused_by_the_next_video(
    tmp_path: Path,
) -> None:
    studio, media = _studio(tmp_path)
    board = _storyboard(_scene("s1", "lamp"), _scene("s2", "lamp"))

    references, judgements, _ = studio._designs(board, _found(), "first-video")

    design = references["lamp"].design
    assert design is not None and Path(design).is_file()
    assert Path(design).parent == tmp_path / "theme/designs"
    assert media.calls.count("image") == 1
    assert {j.question_id for j in judgements} == {"design_view", "design_matches"}

    # A later video, its cache gone: the channel's design is reused, nothing is drawn.
    shutil.rmtree(tmp_path / "cache")
    later, later_media = _studio(tmp_path)
    again, judged, calls = later._designs(_storyboard(_scene("s9", "lamp")), _found(), "next")
    assert again["lamp"].design == design
    assert later_media.calls == [] and judged == [] and calls == []


def test_a_thing_in_one_scene_is_not_designed(tmp_path: Path) -> None:
    studio, media = _studio(tmp_path)
    references, _, _ = studio._designs(_storyboard(_scene("s1", "lamp")), _found(), "v")
    assert references["lamp"].design is None and media.calls == []


def test_a_design_jev_finds_wrong_is_drawn_again_differently(tmp_path: Path) -> None:
    studio, media = _studio(tmp_path, failing=frozenset({"design_view"}))
    board = _storyboard(_scene("s1", "lamp"), _scene("s2", "lamp"))

    references, _, _ = studio._designs(board, _found(), "v")

    assert media.calls.count("image") == 2
    kept = Designs(tmp_path / "theme").get(design_id("object", "The brass lamp"))
    assert kept is not None and kept.attempt == 1 and references["lamp"].design is not None


def test_a_vetoed_design_is_drawn_again_and_a_changed_look_redraws(tmp_path: Path) -> None:
    studio, media = _studio(tmp_path)
    board = _storyboard(_scene("s1", "lamp"), _scene("s2", "lamp"))
    studio._designs(board, _found(), "v")
    designs = Designs(tmp_path / "theme")
    designs.veto(design_id("object", "brass lamp"))

    studio._designs(board, _found(), "v")
    assert media.calls.count("image") == 2
    assert designs.get("object-brass-lamp").status == "kept"  # type: ignore[union-attr]

    # Any other look (here a different image model) is not the design's: drawn again.
    restyled = replace(studio.config, image_model="another/model")
    studio.config = restyled
    studio._designs(board, _found(), "v")
    assert media.calls.count("image") == 3


@pytest.mark.parametrize(
    ("query", "key"),
    [("The brass lamp", "object-brass-lamp"), ("brass  LAMP!", "object-brass-lamp")],
)
def test_a_design_is_known_by_what_it_is_not_its_wording(query: str, key: str) -> None:
    assert design_id("object", query) == key


def _mask(top: int, left: int, size: int) -> np.ndarray:
    mask = np.zeros((100, 100), dtype=bool)
    mask[top : top + size, left : left + size] = True
    return mask


def test_a_whole_thing_clear_of_the_edges_is_ready_for_3d() -> None:
    assert mask_problems(_mask(20, 20, 50)) == []


def test_what_would_waste_a_gpu_run_is_caught_for_free() -> None:
    assert mask_problems(_mask(0, 20, 50)) == ["it touches the frame's edge"]
    assert mask_problems(_mask(40, 40, 5)) == ["it fills 0% of the picture"]
    pieces = _mask(10, 10, 30) | _mask(60, 60, 30)
    assert mask_problems(pieces) == ["it is in pieces"]


def test_a_model_made_on_the_gpu_is_kept_with_its_design(tmp_path: Path) -> None:
    designs = Designs(tmp_path / "theme")
    picture_file = tmp_path / "lamp.png"
    Image.new("RGB", (8, 8)).save(picture_file)
    lamp = designs.keep("object", "brass lamp", picture_file, look="x", attempt=0, video="v")
    mask = tmp_path / "mask.png"
    Image.new("L", (8, 8), 255).save(mask)
    bucket = LocalStore(tmp_path / "bucket")

    def gpu(place: sam3d.Place, job_id: str) -> None:
        out = bucket.root / "jobs" / job_id / "out"
        (out / lamp.design_id).mkdir(parents=True)
        (out / lamp.design_id / "0.glb").write_bytes(b"glTF")
        (out / "result.json").write_text('{"model": "objects", "items": {}}')

    ready = [(lamp, sam3d.Picture(lamp.design_id, designs.path(lamp), masks=(mask,)))]
    report = make_models(
        designs, ready, tmp_path / "made", bucket=bucket, place=sam3d.Place("p", "r"), run=gpu
    )

    assert report == ["object-brass-lamp: 3D model kept (objects)"]
    assert (tmp_path / "theme/designs/object-brass-lamp.glb").read_bytes() == b"glTF"
    assert waiting_for_models(designs) == []
