"""What the person looks at on each sign-off page: the pieces (script units, narration
passages, scenes), what the checks noticed about each in plain words, and what approving
sets in motion and costs. Built from the run's state; the page only renders them."""

import re

from content.judging.outcomes import correction_line
from content.production.budget import NARRATION_TAKE_USD
from content.schemas.media import RenderedAsset
from content.schemas.review import ReviewItem, ReviewStage
from content.schemas.script import LineEdit
from content.state import ContentState
from content.story.notes import PASSAGE_CLASSES
from content.story.pace import passages
from content.theme import VoiceSpec

# A stretch this strong may be heard (the cap is 1.2×; 1.5× and over lurched).
NOTICEABLE_TEMPO = 1.15


def sign_off_items(
    state: ContentState, stage: ReviewStage, voice: VoiceSpec
) -> tuple[list[ReviewItem], str]:
    if stage == "plan":
        return [], (
            "Approving has the script written, checked by a first-time listener, and "
            "fact-checked; you see it at the Script sign-off before any narration is paid for."
        )
    if stage == "fact_check":
        return _script(state), _narration_cost(state, voice)
    if stage == "listen":
        return _narration(state), _pictures_cost(state)
    if stage == "storyboard":
        return _scenes(state), _morphs_cost(state)
    if stage == "final_cut":
        return _cut(state), "Approving finishes the package. Nothing more is spent."
    return [], ""


def _script(state: ContentState) -> list[ReviewItem]:
    script = state.get("script_package")
    if script is None:
        return []
    report = state.get("fact_check_report")
    flags: dict[str, list[str]] = {}
    for finding in report.claim_findings if report else []:
        if finding.status == "passed":
            continue
        for unit_id in finding.script_unit_ids:
            flags.setdefault(unit_id, []).append(
                f"Fact check, {finding.status.replace('_', ' ')}: {finding.issue}"
            )
    latest = {edit.unit_id: edit for edit in state.get("line_edits", [])}
    return [
        ReviewItem(
            item_id=unit.unit_id,
            title=f"{unit.unit_id} · {unit.narrative_function.replace('_', ' ').capitalize()}",
            text=unit.text,
            flags=flags.get(unit.unit_id, []),
            provenance=_provenance(latest[unit.unit_id])
            if unit.unit_id in latest and latest[unit.unit_id].after == unit.text
            else "",
            editable=True,
        )
        for unit in script.script_units
    ]


def _provenance(edit: LineEdit) -> str:
    who = {"person": "Your words", "editor": "Line edit", "writer": "Rewritten"}[edit.author]
    reason = edit.reason if len(edit.reason) <= 160 else edit.reason[:157] + "…"
    return f"{who}, revision {edit.script_revision}" + (
        "" if edit.author == "person" else f": {reason}"
    )


def _narration(state: ContentState) -> list[ReviewItem]:
    script, timeline = state.get("script_package"), state.get("timeline")
    if script is None or timeline is None:
        return []
    clips = state.get("narration", {})
    items = []
    for passage in passages(script.script_units):
        clip = clips.get(passage.passage_id)
        flags = [_without_id(issue) for issue in clip.issues] if clip else []
        # Speed is worth a director's ear only near the limit, where a stretch can show;
        # the take's own note says so when it hit the limit.
        if (
            clip is not None
            and clip.tempo >= NOTICEABLE_TEMPO
            and not any("limit" in flag for flag in flags)
        ):
            flags.insert(0, f"Sped up {clip.tempo:.2f}× to keep the pace: listen for a rush.")
        items.append(
            ReviewItem(
                item_id=passage.passage_id,
                title=f"{passage.passage_id} · {', '.join(passage.unit_ids)}",
                text=passage.text,
                start=timeline.passage_starts.get(passage.passage_id),
                flags=flags,
                note_kinds=list(PASSAGE_CLASSES),
            )
        )
    return items


def _scenes(state: ContentState) -> list[ReviewItem]:
    visuals, script = state.get("visual_package"), state.get("script_package")
    if visuals is None or script is None:
        return []
    lines = {unit.unit_id: unit.text for unit in script.script_units}
    keyframes = state.get("keyframes", {})
    return [
        ReviewItem(
            item_id=scene.scene_id,
            title=f"{scene.scene_id} · {scene.focus or scene.anchor.subject}",
            text=" ".join(lines.get(unit_id, "") for unit_id in scene.script_unit_ids),
            media=keyframes[scene.scene_id].path if scene.scene_id in keyframes else "",
            flags=_asset_flags(keyframes.get(scene.scene_id)),
        )
        for scene in visuals.scenes
    ]


def _cut(state: ContentState) -> list[ReviewItem]:
    visuals, timeline = state.get("visual_package"), state.get("timeline")
    if visuals is None or timeline is None:
        return []
    starts = {timing.scene_id: timing.start for timing in timeline.scenes}
    keyframes = state.get("keyframes", {})
    segments = state.get("segments", {})
    return [
        ReviewItem(
            item_id=scene.scene_id,
            title=f"{scene.scene_id} · {scene.focus or scene.anchor.subject}",
            media=keyframes[scene.scene_id].path if scene.scene_id in keyframes else "",
            start=starts.get(scene.scene_id),
            flags=_asset_flags(segments.get(scene.scene_id)),
        )
        for scene in visuals.scenes
    ]


def _asset_flags(asset: RenderedAsset | None) -> list[str]:
    """Code's measured problems first, then Jev's doubts, as the fix each would need."""
    if asset is None:
        return []
    doubts = [
        ("Possibly: " if judgement.outcome == "unsure" else "") + correction_line(judgement)
        for judgement in asset.judgements
        if judgement.outcome != "pass" and correction_line(judgement)
    ]
    return list(dict.fromkeys(_without_id(line) for line in [*asset.issues, *doubts]))


def _without_id(line: str) -> str:
    """'S3: too bright' → 'too bright', since the card already says which scene."""
    trimmed = re.sub(r"^(?:Possibly: )?[A-Z]\d+(?:\.\d+)?: ", "", line)
    return (
        ("Possibly: " if line.startswith("Possibly: ") else "") + trimmed[:1].upper() + trimmed[1:]
    )


def _narration_cost(state: ContentState, voice: VoiceSpec) -> str:
    script = state.get("script_package")
    count = len(passages(script.script_units)) if script else 0
    takes = voice.expected_takes
    return (
        f"Approving records the narration: {count} passages, "
        f"about ${count * takes * NARRATION_TAKE_USD:.2f} "
        f"(about {takes:.1f} takes a passage: one, and another when a take falls short of "
        "the pace)."
    )


def _pictures_cost(state: ContentState) -> str:
    budget = state.get("budget")
    if budget is None:
        return "Approving draws the pictures."
    return (
        f"Approving draws the pictures: about ${budget.keyframes:.2f}. "
        f"The run is projected at ${budget.projected:.2f} of its ${budget.cap:.2f} cap."
    )


def _morphs_cost(state: ContentState) -> str:
    budget = state.get("budget")
    if budget is None:
        return "Approving makes the morphs between the pictures."
    return (
        f"Approving makes the {budget.morphs} morphs between the pictures: about "
        f"${budget.transitions:.2f}. Redrawing a picture later re-makes its two morphs."
    )
