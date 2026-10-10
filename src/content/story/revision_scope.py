"""How far a script revision reaches.

A revision whose every note names its lines ("U3: …", "U3->U4: …") is a line edit: only
those lines are rewritten, and code keeps every other line byte for byte. A note on the
whole script, a listener's report, or a change touching too many lines is a whole rewrite.
A person's own words for a line stand exactly, in both."""

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence

from content.judging.questions import QUESTIONS
from content.schemas.judgement import Judgement
from content.schemas.review import RevisionScope
from content.schemas.script import LineEdit, ScriptUnit

UNIT = re.compile(r"\bU\d+\b")


def note_units(note: str) -> set[str]:
    """The lines a note names before its first colon (or anywhere, without one)."""
    return set(UNIT.findall(note.split(":", 1)[0]))


def most_lines(unit_count: int) -> int:
    """The most lines a line edit may touch; beyond it the change is the whole script's."""
    return max(2, math.ceil(unit_count / 3))


def line_targets(
    notes: Sequence[str],
    units: Sequence[ScriptUnit],
    *,
    locked: Iterable[str] = (),
    scope: RevisionScope | None = None,
) -> set[str] | None:
    """The lines to rewrite, or None for a whole rewrite. Lines in `locked` (a person's own
    words) are never targets. A person's `scope` overrides the size limit."""
    if scope == "script":
        return None
    known = {unit.unit_id for unit in units}
    targets: set[str] = set()
    for note in notes:
        named = note_units(note)
        if not named or not named <= known:
            return None
        targets |= named
    targets -= set(locked)
    if scope != "lines" and len(targets) > most_lines(len(units)):
        return None
    return targets


def locked_lines(edits: Sequence[LineEdit]) -> list[str]:
    """The person's own words still in force: every line they wrote, unless they later
    rewrote it themselves. Held as text, since a whole rewrite may renumber the lines."""
    locked: list[str] = []
    for edit in edits:
        if edit.author == "person":
            locked = [text for text in locked if text != edit.before] + [edit.after]
    return locked


def unchanged_judgements(
    previous: Sequence[Judgement],
    changed: set[str],
    units: Sequence[ScriptUnit],
    revision: int,
) -> list[Judgement]:
    """Judgements of the last revision that a line edit leaves standing, moved to the new
    revision so they are not asked again: every passing target the change does not touch.
    The whole-script question is always asked again, and anything that did not pass is
    asked again, as before."""
    opening_lines = {unit.unit_id for unit in units[:2]}
    groups: dict[tuple[str, str], list[Judgement]] = defaultdict(list)
    for judgement in previous:
        groups[(QUESTIONS[judgement.question_id].target, judgement.target_id)].append(judgement)
    kept: list[Judgement] = []
    for (target, target_id), judgements in groups.items():
        touched = {
            "script": True,
            "opening": bool(opening_lines & changed),
            "unit": target_id in changed,
            "transition": bool(set(target_id.split("->")) & changed),
        }.get(target, True)
        if touched or any(judgement.outcome != "pass" for judgement in judgements):
            continue
        kept += [judgement.model_copy(update={"revision": revision}) for judgement in judgements]
    return kept
