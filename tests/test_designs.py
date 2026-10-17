"""Designs: a person, place or object in several scenes is drawn once in the channel's look, and
every keyframe that shows it, in this video and later ones, is drawn from that design."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
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
from content.staging import designs
from content.staging.designs import design_id, make_models, mask_problems, waiting_for_models
from content.staging.library import Library, load_library
from content.staging.store import Store
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


def _library(tmp_path: Path) -> Library:
    return load_library(tmp_path / "theme/assets")


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
    assert Path(design).parent == tmp_path / "theme/assets/files"
    # It is a model in the channel's library, traced like any other, but no shot can use it
    # until its 3D model is made.
    library = _library(tmp_path)
    lamp = library.get("object_brass_lamp")
    assert lamp.identity is not None and not lamp.placeable
    assert "object_brass_lamp" not in [f.model.model_id for f in library.search("brass lamp")]
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


def test_a_cast_member_is_never_searched_for_and_drawn_from_its_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(ROOT / "themes/starter", tmp_path / "theme")
    spec = json.loads((tmp_path / "theme/theme.json").read_text())
    spec["visual"]["cast"] = {"Pat": "a round grey office worker with slit eyes"}
    (tmp_path / "theme/theme.json").write_text(json.dumps(spec))
    studio, media = _studio(tmp_path)
    prompts: list[str] = []
    drawn = media.image
    monkeypatch.setattr(media, "image", lambda **kw: (prompts.append(kw["prompt"]), drawn(**kw))[1])
    monkeypatch.setattr(studio, "_find_reference", lambda *a: pytest.fail("searched for"))
    pat = ReferenceRequest(ref_id="pat", kind="person", query="Pat", unit_ids=["u1"], purpose="")
    board = _storyboard(_scene("s1", "pat")).model_copy(update={"references": [pat]})
    state: Any = {"visual_package": board, "script_package": SimpleNamespace(script_units=[]),
                  "topic": "v"}  # fmt: skip

    found = studio.find_references(state)["references"]["pat"]

    # In one scene only, it is drawn all the same: the cast is always drawn from its design.
    assert found.relevant and found.chosen == [] and found.design is not None
    assert len(prompts) == 1 and "a round grey office worker with slit eyes" in prompts[0]


def test_a_design_jev_finds_wrong_is_drawn_again_differently(tmp_path: Path) -> None:
    studio, media = _studio(tmp_path, failing=frozenset({"design_view"}))
    board = _storyboard(_scene("s1", "lamp"), _scene("s2", "lamp"))

    references, _, _ = studio._designs(board, _found(), "v")

    assert media.calls.count("image") == 2
    kept = _library(tmp_path).get(design_id("object", "The brass lamp"))
    assert kept.identity is not None and kept.identity.attempt == 1
    assert references["lamp"].design is not None


def test_a_vetoed_design_is_drawn_again_and_a_changed_look_redraws(tmp_path: Path) -> None:
    studio, media = _studio(tmp_path)
    board = _storyboard(_scene("s1", "lamp"), _scene("s2", "lamp"))
    studio._designs(board, _found(), "v")
    _library(tmp_path).veto(design_id("object", "brass lamp"), "too shiny")

    studio._designs(board, _found(), "v")
    assert media.calls.count("image") == 2
    assert _library(tmp_path).get("object_brass_lamp").status == "kept"

    # Any other look (here a different image model) is not the design's: drawn again.
    restyled = replace(studio.config, image_model="another/model")
    studio.config = restyled
    studio._designs(board, _found(), "v")
    assert media.calls.count("image") == 3


@pytest.mark.parametrize(
    ("query", "key"),
    [("The brass lamp", "object_brass_lamp"), ("brass  LAMP!", "object_brass_lamp")],
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
    library = _library(tmp_path)
    picture_file = tmp_path / "lamp.png"
    Image.new("RGB", (8, 8)).save(picture_file)
    lamp = designs.keep(
        library, "object", "brass lamp", picture_file, look="x", attempt=0, video="v"
    )
    mask = tmp_path / "mask.png"
    Image.new("L", (8, 8), 255).save(mask)
    bucket = LocalStore(tmp_path / "bucket")

    def gpu(place: sam3d.Place, job_id: str) -> None:
        out = bucket.root / "jobs" / job_id / "out"
        (out / lamp.model_id).mkdir(parents=True)
        (out / lamp.model_id / "0.glb").write_bytes(b"glTF")
        (out / "result.json").write_text('{"model": "objects", "items": {}}')

    def ingest(made: Path, prepared: Path) -> dict[str, Any]:
        # Blender's import, standing in: the file as it is, measured.
        shutil.copyfile(made, prepared)
        return {"width": 0.3, "depth": 0.3, "height": 0.5}

    ready = [(lamp, sam3d.Picture(lamp.model_id, designs.picture(library, lamp), masks=(mask,)))]
    report = make_models(
        library, ready, tmp_path / "made", bucket=bucket, place=sam3d.Place("p", "r"),
        ingest=ingest, run=gpu,
    )  # fmt: skip

    assert report == ["object_brass_lamp: 3D model kept (objects)"]
    assert waiting_for_models(library) == []
    # Kept as the design's file: now a shot can find and use it, and its making is traced.
    again = _library(tmp_path)
    made = again.get("object_brass_lamp")
    assert made.placeable and made.size == (0.3, 0.3, 0.5)
    path = again.path(made)
    assert path is not None and path.read_bytes() == b"glTF"
    assert again.search("brass lamp")[0].model.model_id == "object_brass_lamp"
    assert [step for _, step, _ in Store(again.folder).lineage("object_brass_lamp")] == [  # type: ignore[arg-type]
        "drawn",
        "made",
    ]
