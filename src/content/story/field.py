"""The emotional field: how each scene's space, light, and motion follow the way its lines
land on a listener.

Jev measures each unit's reaction as a gut response (lean in, brace, recoil, settle) with a
probability for each, and how strongly it lands. Code blends those into one field per scene
and turns the field into concrete visual wording from the theme. No emotion word reaches a
prompt: a tense line narrows the frame; it never says "tense".
"""

from collections.abc import Mapping, Sequence
from typing import Literal, cast

from content.schemas.judgement import Judgement
from content.schemas.research import ResearchPack
from content.schemas.script import ScriptPackage
from content.schemas.story import Feeling, Reaction
from content.schemas.visuals import VisualPackage
from content.theme import FieldSpec, ReactionLook, Theme

REACTIONS: tuple[Reaction, ...] = ("lean_in", "brace", "recoil", "settle")

# Valdez and Mehrabian (1994), "Effects of color on emotions": standardised regressions of
# how people felt about colour samples on the samples' brightness and saturation.
#   pleasure = 0.69 brightness + 0.22 saturation
#   arousal  = -0.31 brightness + 0.60 saturation
# Hue mattered far less than either, so these two carry the feeling.
PLEASURE_FROM = (0.69, 0.22)
AROUSAL_FROM = (-0.31, 0.60)


def unit_feelings(judgements: Sequence[Judgement]) -> dict[str, Feeling]:
    """Each unit's reaction and intensity, read from Jev's measurements."""
    reactions = {j.target_id: j.answer for j in judgements if j.question_id == "unit_reaction"}
    intensities = {j.target_id: j.answer for j in judgements if j.question_id == "unit_intensity"}
    feelings = {}
    for unit_id, answer in reactions.items():
        weights = {reaction: answer.probabilities.get(reaction, 0.0) for reaction in REACTIONS}
        if not any(weights.values()) and answer.choice in REACTIONS:
            weights[cast(Reaction, answer.choice)] = 1.0
        total = sum(weights.values()) or 1.0
        intensity = intensities.get(unit_id)
        feelings[unit_id] = Feeling(
            weights={reaction: weight / total for reaction, weight in weights.items()},
            intensity=intensity.score if intensity and intensity.score is not None else 1.0,
        )
    return feelings


def capped_units(script: ScriptPackage, research: ResearchPack) -> set[str]:
    """Units resting on anything short of a verified fact: an allegation never gets
    full-force visuals."""
    verified = {claim.claim_id for claim in research.verified_facts}
    return {
        unit.unit_id
        for unit in script.script_units
        if any(claim_id not in verified for claim_id in unit.claim_ids)
    }


def scene_feelings(
    visuals: VisualPackage,
    feelings: Mapping[str, Feeling],
    seconds: Mapping[str, float],
    capped: set[str],
) -> dict[str, Feeling]:
    """Each scene's field: its units' feelings, weighted by how long each is heard. A
    person's `feel` override replaces the blend."""
    fields = {}
    for scene in visuals.scenes:
        heard = [
            (unit, seconds.get(unit, 1.0)) for unit in scene.script_unit_ids if unit in feelings
        ]
        total = sum(share for _, share in heard)
        if not total and scene.feeling is None:
            continue
        intensity = (
            sum(_strength(feelings[unit], unit in capped) * share for unit, share in heard) / total
            if total
            else 1.0
        )
        weights = {
            reaction: sum(feelings[unit].weights[reaction] * share for unit, share in heard)
            / (total or 1.0)
            for reaction in REACTIONS
        }
        if scene.feeling is not None:
            weights = {reaction: float(reaction == scene.feeling) for reaction in REACTIONS}
        fields[scene.scene_id] = Feeling(weights=weights, intensity=intensity)
    return fields


def _strength(feeling: Feeling, capped: bool) -> float:
    return min(feeling.intensity, 1.0) if capped else feeling.intensity


def ripple_tint(
    feeling: Feeling | None, spec: FieldSpec, strongest: float
) -> tuple[str, float] | None:
    """The colour a scene's breathing ripples take on: each reaction's `ripple_colour`,
    blended by how much of the scene lands that way, at an opacity that grows with how
    strongly it lands (`strongest` at full intensity). None leaves them colourless."""
    if feeling is None or strongest <= 0:
        return None
    total = sum(feeling.weights.values()) or 1.0
    channels = [
        sum(
            int(spec.reactions[reaction].ripple_colour[1 + 2 * i : 3 + 2 * i], 16) * weight
            for reaction, weight in feeling.weights.items()
        )
        / total
        for i in range(3)
    ]
    colour = "#" + "".join(f"{round(channel):02X}" for channel in channels)
    return colour, round(strongest * min(feeling.intensity / 2, 1.0), 3)


def look(feeling: Feeling | None, spec: FieldSpec) -> ReactionLook:
    return spec.neutral if feeling is None else spec.reactions[feeling.dominant]


def field_slots(feeling: Feeling | None, spec: FieldSpec) -> dict[str, str]:
    """The keyframe and segment wording for a scene's field."""
    chosen = look(feeling, spec)
    level = 1 if feeling is None else feeling.level
    return {
        "field_frame": chosen.frame[level],
        "field_light": chosen.light[level],
        "field_motion": chosen.motion[level],
    }


def aperture(feeling: Feeling | None, spec: FieldSpec) -> float:
    if feeling is None:
        return spec.neutral.aperture
    return sum(weight * spec.reactions[r].aperture for r, weight in feeling.weights.items())


def shift_phrase(before: Feeling | None, after: Feeling | None, spec: FieldSpec) -> str:
    """How the space changes into the next scene: tunnelling in, blooming out, or flowing
    on, swiftly when the feeling changes a lot, slowly when it barely does."""
    change = aperture(after, spec) - aperture(before, spec)
    direction: Literal["inward", "outward", "sideways"] = (
        "inward" if change <= -0.5 else "outward" if change >= 0.5 else "sideways"
    )
    swing = (
        abs(change)
        + abs((after.intensity if after else 1) - (before.intensity if before else 1)) / 2
    )
    speed = spec.speeds["swift" if swing >= spec.swift_above else "slow"]
    return f"{spec.shifts[direction]}, {speed}"


def warmth(feeling: Feeling | None, spec: FieldSpec) -> float:
    """A scene's colour temperature, from −1 (cold) to 1 (warm): its reactions' blended."""
    if feeling is None:
        return 0.0
    return sum(weight * spec.reactions[r].temperature for r, weight in feeling.weights.items())


def expected_temperature(
    feeling: Feeling | None, spec: FieldSpec
) -> Literal["warm", "cool"] | None:
    """The colour temperature a scene's keyframe should measure, if it should lean at all."""
    if feeling is None:
        return None
    temperature = warmth(feeling, spec)
    if temperature >= 0.3:
        return "warm"
    if temperature <= -0.3:
        return "cool"
    return None


def circumplex(feeling: Feeling | None, spec: FieldSpec) -> tuple[float, float]:
    """The scene's (pleasure, arousal): its reactions' points blended by weight and scaled
    by how strongly they land (intensity 2 is the full point)."""
    if feeling is None:
        return spec.neutral.pleasure, spec.neutral.arousal
    scale = feeling.intensity / 2
    pleasure = sum(w * spec.reactions[r].pleasure for r, w in feeling.weights.items())
    arousal = sum(w * spec.reactions[r].arousal for r, w in feeling.weights.items())
    return round(pleasure * scale, 3), round(arousal * scale, 3)


def colour_units(pleasure: float, arousal: float) -> tuple[float, float]:
    """The brightness and saturation, in standard deviations, that carry this pleasure
    and arousal: Valdez and Mehrabian's two equations solved the other way round."""
    (pb, ps), (ab, as_) = PLEASURE_FROM, AROUSAL_FROM
    determinant = pb * as_ - ps * ab
    brightness = (as_ * pleasure - ps * arousal) / determinant
    saturation = (pb * arousal - ab * pleasure) / determinant
    return round(brightness, 3), round(saturation, 3)


def story_fields(
    script: ScriptPackage | None,
    visuals: VisualPackage | None,
    research: ResearchPack | None,
    feelings: Mapping[str, Feeling],
    seconds: Mapping[str, float],
) -> dict[str, Feeling]:
    """Every scene's field, from whatever the run has measured so far."""
    if script is None or visuals is None:
        return {}
    capped = capped_units(script, research) if research is not None else set()
    return scene_feelings(visuals, feelings, seconds, capped)


def scene_prompts(
    theme: Theme, visuals: VisualPackage, fields: Mapping[str, Feeling]
) -> list[tuple[str, str, str]]:
    """(scene ID, keyframe prompt, segment prompt) for each scene, shaped by its field."""
    spec = theme.spec.visual.field
    scenes = visuals.scenes
    prompts = []
    for index, scene in enumerate(scenes):
        following = scenes[index + 1] if index + 1 < len(scenes) else None
        here = fields.get(scene.scene_id)
        slots = field_slots(here, spec)
        prompts.append(
            (
                scene.scene_id,
                theme.keyframe_prompt(scene.anchor, field=slots),
                theme.segment_prompt(
                    scene.anchor,
                    camera=scene.camera,
                    motion=scene.motion,
                    morph_bridge=scene.morph_bridge,
                    next_anchor=following.anchor if following else None,
                    field=slots,
                    shift=shift_phrase(here, fields.get(following.scene_id), spec)
                    if following
                    else None,
                ),
            )
        )
    return prompts
