import json
import re
from pathlib import Path
from typing import Any

import pytest

from content.config import ContentConfig, load_config
from content.errors import ConfigurationError
from content.judging.outcomes import answer_outcome
from content.judging.questions import QUESTIONS
from content.production import ffmpeg
from content.production.checks import colour_issues, measure, temperature_issues
from content.schemas.judgement import Answer, Judgement
from content.schemas.research import ResearchPack
from content.schemas.script import ScriptPackage
from content.schemas.story import Feeling, Reaction
from content.schemas.visuals import VisualPackage
from content.story.field import (
    REACTIONS,
    capped_units,
    circumplex,
    colour_units,
    expected_temperature,
    field_slots,
    ripple_tint,
    scene_feelings,
    shift_phrase,
    unit_feelings,
)
from content.story.notes import feel_overrides
from content.theme import load_theme
from content.workflow.demo import demo_response

THEME = load_theme(Path(__file__).parents[1] / "themes/starter")
FIELD = THEME.spec.visual.field
EMOTION_WORDS = ["angry", "anger", "sad", "tense", "happy", "fear", "curious", "negative"]


def test_reactions_are_read_from_jevs_probabilities() -> None:
    judgements = [
        _judgement("U1", "unit_reaction", Answer(kind="choice", choice="brace", confidence=0.4,
                   probabilities={"brace": 0.6, "lean_in": 0.3, "recoil": 0.1})),
        _judgement("U1", "unit_intensity", Answer(kind="score", score=1.8, confidence=0.7)),
    ]  # fmt: skip

    (feeling,) = unit_feelings(judgements).values()

    assert feeling.dominant == "brace"
    assert feeling.weights["lean_in"] == pytest.approx(0.3)
    assert feeling.label() == "brace · strong"


def test_scene_fields_blend_by_seconds_cap_allegations_and_take_overrides() -> None:
    visuals = _demo(VisualPackage)
    feelings = {
        "U1": _feeling("brace", 2.0),
        "U2": _feeling("lean_in", 1.0),
        "U3": _feeling("brace", 2.0),
    }

    fields = scene_feelings(visuals, feelings, {"U1": 8.0, "U2": 4.0}, capped={"U3"})

    assert fields["S1"].dominant == "brace" and fields["S1"].intensity == 2.0
    assert fields["S3"].intensity == 1.0  # an allegation never lands at full force
    overridden = visuals.model_copy(
        update={
            "scenes": [
                scene.model_copy(update={"feeling": "settle"}) if scene.scene_id == "S1" else scene
                for scene in visuals.scenes
            ]
        }
    )
    assert scene_feelings(overridden, feelings, {}, set())["S1"].dominant == "settle"


def test_only_verified_claims_escape_the_cap() -> None:
    script, research = _demo(ScriptPackage), _demo(ResearchPack)
    verified = {claim.claim_id for claim in research.verified_facts}

    capped = capped_units(script, research)

    assert all(
        any(claim not in verified for claim in unit.claim_ids)
        for unit in script.script_units
        if unit.unit_id in capped
    )


def test_field_wording_never_names_an_emotion() -> None:
    for reaction in REACTIONS:
        for strength in (0.2, 1.0, 2.0):
            text = " ".join(field_slots(_feeling(reaction, strength), FIELD).values()).lower()
            assert [w for w in EMOTION_WORDS if re.search(rf"\b{w}\b", text)] == []


def test_transitions_tunnel_in_bloom_out_and_move_faster_for_bigger_changes() -> None:
    curious, braced = _feeling("lean_in", 1.0), _feeling("brace", 2.0)

    inward = shift_phrase(curious, braced, FIELD)
    outward = shift_phrase(braced, curious, FIELD)
    level = shift_phrase(curious, _feeling("lean_in", 1.2), FIELD)

    assert inward.startswith(FIELD.shifts["inward"]) and inward.endswith(FIELD.speeds["swift"])
    assert outward.startswith(FIELD.shifts["outward"])
    assert level.startswith(FIELD.shifts["sideways"]) and level.endswith(FIELD.speeds["slow"])


def test_colour_temperature_is_measured_against_the_field(tmp_path: Path) -> None:
    ochre, slate = tmp_path / "ochre.png", tmp_path / "slate.png"
    ffmpeg.run("-f", "lavfi", "-i", "color=c=0x9C7A3C:s=90x160", "-frames:v", "1", ochre)
    ffmpeg.run("-f", "lavfi", "-i", "color=c=0x2F5559:s=90x160", "-frames:v", "1", slate)
    warm = expected_temperature(_feeling("lean_in", 1.0), FIELD)
    cool = expected_temperature(_feeling("brace", 1.0), FIELD)

    assert (warm, cool) == ("warm", "cool")
    assert temperature_issues(measure(ochre), warm) == []
    assert temperature_issues(measure(slate), warm)[0].startswith("colour too cool")
    assert temperature_issues(measure(ochre), cool)[0].startswith("colour too warm")


def test_colour_targets_invert_the_published_colour_emotion_model() -> None:
    for pleasure, arousal in [(0.4, 0.4), (-0.6, 0.6), (0.0, 0.0), (0.5, -0.5)]:
        brightness, saturation = colour_units(pleasure, arousal)
        # Put back through Valdez and Mehrabian's equations, the same feeling comes out.
        assert 0.69 * brightness + 0.22 * saturation == pytest.approx(pleasure, abs=0.01)
        assert -0.31 * brightness + 0.60 * saturation == pytest.approx(arousal, abs=0.01)


def test_a_braced_scene_asks_for_a_darker_image_than_a_settled_one() -> None:
    braced = circumplex(_feeling("brace", 2.0), FIELD)
    settled = circumplex(_feeling("settle", 2.0), FIELD)
    faint = circumplex(_feeling("brace", 0.5), FIELD)

    assert colour_units(*braced)[0] < 0 < colour_units(*settled)[0]
    # A reaction that barely lands barely moves the image.
    assert abs(colour_units(*faint)[0]) < abs(colour_units(*braced)[0]) / 2


def test_a_keyframe_far_from_its_colour_target_is_named(tmp_path: Path) -> None:
    ink = tmp_path / "ink.png"
    ffmpeg.run("-f", "lavfi", "-i", "color=c=0x1C1C22:s=90x160", "-frames:v", "1", ink)
    signal = measure(ink)
    near = {"target_brightness": signal.brightness + 5, "target_saturation": signal.saturation}
    far = {"target_brightness": signal.brightness + 30, "target_saturation": signal.saturation}
    tolerances = {"brightness_tolerance": 13.0, "saturation_tolerance": 6.0}

    assert colour_issues(signal, **near, **tolerances) == []
    (issue,) = colour_issues(signal, **far, **tolerances)
    assert issue.startswith("too dark for the scene")


def test_measurements_never_pass_judgement_or_block(
    tmp_path: Path, app_config: ContentConfig, project_root: Path
) -> None:
    unsure = Answer(kind="choice", choice="brace", confidence=0.1)
    assert answer_outcome(QUESTIONS["unit_reaction"], unsure, None, app_config.decisions) == "pass"

    data: dict[str, Any] = json.loads((project_root / "config/config.json").read_text())
    for agent in data["agents"].values():
        agent["prompt"] = str(project_root / agent["prompt"])
    data["decisions"]["blocking"].append("unit_reaction")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ConfigurationError, match="Measurements cannot block: unit_reaction"):
        load_config(path)


def test_feel_notes_set_a_scene_field_without_a_redesign() -> None:
    overrides, rest = feel_overrides(["S4: feel brace", "S2: show the lectern"])

    assert overrides == {"S4": "brace"}
    assert rest == ["S2: show the lectern"]


def _feeling(reaction: Reaction, intensity: float) -> Feeling:
    weights: dict[Reaction, float] = {r: float(r == reaction) for r in REACTIONS}
    return Feeling(weights=weights, intensity=intensity)


def _judgement(target: str, question: str, answer: Answer) -> Judgement:
    return Judgement(
        stage="script",
        revision=0,
        target_id=target,
        question_id=question,
        answer=answer,
        expected=None,
        outcome="pass",
        blocking=False,
        model="jev",
    )


def _demo(output_type: type[Any]) -> Any:
    return output_type.model_validate(demo_response(json.dumps({"topic": "x"}), output_type))


def test_ripples_take_the_scenes_colour_more_strongly_the_harder_it_lands() -> None:
    braced = Feeling(weights={r: float(r == "brace") for r in REACTIONS}, intensity=2.0)
    faint = braced.model_copy(update={"intensity": 0.5})
    half = Feeling(
        weights={r: 0.5 if r in {"brace", "lean_in"} else 0.0 for r in REACTIONS}, intensity=2.0
    )

    colour, strength = ripple_tint(braced, FIELD, 0.12) or ("", 0.0)
    _, quieter = ripple_tint(faint, FIELD, 0.12) or ("", 0.0)
    mixed, _ = ripple_tint(half, FIELD, 0.12) or ("", 0.0)

    assert colour == FIELD.reactions["brace"].ripple_colour.upper()
    assert strength == 0.12 and quieter == 0.03
    brace, lean = FIELD.reactions["brace"].ripple_colour, FIELD.reactions["lean_in"].ripple_colour
    assert all(
        min(channel(brace, i), channel(lean, i))
        <= channel(mixed, i)
        <= max(channel(brace, i), channel(lean, i))
        for i in range(3)
    )
    # No measured feeling, or no tint in the theme: the ripples stay colourless.
    assert ripple_tint(None, FIELD, 0.12) is None
    assert ripple_tint(braced, FIELD, 0.0) is None


def channel(hex_colour: str, index: int) -> int:
    return int(hex_colour[1 + 2 * index : 3 + 2 * index], 16)
