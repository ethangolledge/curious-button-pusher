"""The node that acts on a person's story-sheet notes: narration first, then scenes, then
references; a passage note is fixed in code where it can be."""

from collections.abc import Callable

from content.state import CallRecord, ContentState
from content.story.notes import feel_overrides, narration_fixes, split_notes
from content.story.pace import passages

# The critic's sorting of untargeted notes onto what they are about (`Critic.sort_notes`).
SortNotes = Callable[[ContentState, str], tuple[list[str], CallRecord]]


def _narration_fixes(state: ContentState, notes: list[str]) -> tuple[ContentState, list[str]]:
    """The state changes for a person's passage notes, and the wording notes left for
    the writer."""
    script = state.get("script_package")
    if not notes or script is None:
        return {}, []
    fixes = narration_fixes(
        notes,
        {passage.passage_id: passage.unit_ids for passage in passages(script.script_units)},
    )
    update: ContentState = {}
    if fixes.say_as:
        direction = script.voice_direction
        update["script_package"] = script.model_copy(
            update={
                "voice_direction": direction.model_copy(
                    update={"say_as": {**direction.say_as, **fixes.say_as}}
                )
            }
        )
    if fixes.directions:
        asked = dict(state.get("passage_directions", {}))
        for passage_id, note in fixes.directions.items():
            asked[passage_id] = "; ".join(part for part in (asked.get(passage_id), note) if part)
        update["passage_directions"] = asked
    if fixes.retakes:
        retakes = dict(state.get("retakes_asked", {}))
        for passage_id in fixes.retakes:
            retakes[passage_id] = retakes.get(passage_id, 0) + 1
        update["retakes_asked"] = retakes
    return update, fixes.unit_notes


def apply_director_notes(state: ContentState, *, sort_notes: SortNotes) -> ContentState:
    """Send each of a person's story-sheet notes to its owner. Narration comes first:
    scene and reference notes wait while the writer revises. A note on a narration
    passage is fixed by its class, in code where it can be: a pronunciation, a pause or
    emphasis, or a fresh take re-records only that passage; wording goes to the writer
    as a note on the passage's lines."""
    notes = split_notes(state.get("human_review_feedback") or "")
    calls: list[CallRecord] = []
    if notes.untargeted:
        sorted_notes, call = sort_notes(state, notes.untargeted)
        calls.append(call)
        for note in sorted_notes:
            if note[:1] in {"U", "S", "R"}:
                notes.add(note)
    overrides, notes.scenes = feel_overrides(notes.scenes)
    visuals = state.get("visual_package")
    update: ContentState = {}
    narration, wording = _narration_fixes(state, notes.passages)
    notes.units += wording
    update.update(narration)
    if overrides and visuals is not None:
        # A feel note reshapes a scene's field in code; nothing is redesigned.
        update["visual_package"] = visuals.model_copy(
            update={
                "scenes": [
                    scene.model_copy(update={"feeling": overrides[scene.scene_id]})
                    if scene.scene_id in overrides
                    else scene
                    for scene in visuals.scenes
                ]
            }
        )
    if notes.units:
        route, now, later = "notes_script", notes.units, [*notes.scenes, *notes.references]
    elif notes.scenes:
        route, now, later = "notes_visuals", notes.scenes, notes.references
    else:
        # References are found again where rejected; the narration is recorded again
        # wherever its text, direction or take changed.
        route, now, later = "notes_references", [], notes.references
    return {
        **update,
        "routing_decision": route,
        "revision_notes": now,
        "director_notes": later,
        "human_review_feedback": None,
        "call_log": calls,
        "events": [{"stage": "director", "message": f"Director notes: {route}"}],
    }
