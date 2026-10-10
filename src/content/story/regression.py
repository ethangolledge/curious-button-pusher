"""Story-quality regression: do the listener test, Jev, and the free checks catch the
failures a person found in a real script, and leave its fix alone?

Fixtures live in the channel's theme, `themes/<name>/examples/<story>/`: `negative.json` is a
script a person rejected, with each failure they named pinned to its line;
`positive.json`, when there is one, is the version they approved. Running them costs a
listener call and a few dozen Jev calls (`content eval`), so they are run on demand, not
in the test suite. Scoring is pure and free."""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from content.schemas.audience import AudienceReport
from content.schemas.base import ImmutableModel
from content.schemas.judgement import Outcome
from content.schemas.script import ScriptUnit
from content.story.ledger import listener_findings
from content.story.prose import dense_issues

# Asks Jev one question about one piece of state, and returns its outcome. A blocking
# question that comes back unsure is a doubt the critic settles in a real run.
Ask = Callable[[str, Mapping[str, object]], Outcome]


class ExpectedFailure(ImmutableModel):
    pattern: str
    unit_id: str
    note: str


class StoryFixture(ImmutableModel):
    name: str
    kind: Literal["negative", "positive"]
    audience: str
    central_question: str
    units: list[ScriptUnit]
    expected: list[ExpectedFailure] = []

    @property
    def narration(self) -> str:
        return " ".join(unit.text for unit in self.units)


@dataclass(frozen=True, slots=True)
class Flag:
    """One check's objection, on the line it concerns (None: the whole narration)."""

    unit_id: str | None
    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class Score:
    # Each expected failure, and the checks that caught it (empty: missed).
    caught: list[tuple[ExpectedFailure, list[str]]]
    # Flags on lines no expected failure names: false alarms on a positive fixture.
    unexpected: list[Flag]


def load_fixtures(root: Path) -> list[StoryFixture]:
    return [
        StoryFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(root.glob("*/*.json"))
        if path.stem in {"negative", "positive"}
    ]


def flags(fixture: StoryFixture, heard: AudienceReport, ask: Ask) -> list[Flag]:
    """Every objection the checks raise: the listener's stumbles, Jev's comprehension
    questions on each line and join and on the ending, and the free overload check."""
    units = fixture.units
    found = [
        Flag(finding.unit_id, f"listener: {finding.kind}", finding.flag.quote)
        for finding in listener_findings(heard, units)
    ]
    for index, unit in enumerate(units):
        state = {
            "unit": {"unit_id": unit.unit_id, "text": unit.text},
            "earlier_units": [earlier.text for earlier in units[:index]],
            "audience": fixture.audience,
        }
        found += _judged(ask, "unit_clear", state, unit.unit_id, unit.text)
    for previous, unit in zip(units, units[1:], strict=False):
        state = {
            "audience": fixture.audience,
            "previous_unit": previous.text,
            "unit": {"unit_id": unit.unit_id, "text": unit.text},
            "why_next": "",
        }
        found += _judged(ask, "transition_why", state, unit.unit_id, unit.text)
    ending = {
        "central_question": fixture.central_question,
        "opening": units[0].text,
        "ending": units[-1].text,
    }
    found += _judged(ask, "script_payoff", ending, units[-1].unit_id, units[-1].text)
    found += [
        Flag(issue.split(":", 1)[0], "code: overloaded sentence", issue)
        for issue in dense_issues(units)
    ]
    return found


def _judged(
    ask: Ask, question_id: str, state: Mapping[str, object], unit_id: str, text: str
) -> list[Flag]:
    outcome = ask(question_id, state)
    if outcome == "pass":
        return []
    label = f"jev: {question_id}" + (" (unsure: to the critic)" if outcome == "unsure" else "")
    return [Flag(unit_id, label, text)]


def score(fixture: StoryFixture, raised: Iterable[Flag]) -> Score:
    raised = list(raised)
    named = {expected.unit_id for expected in fixture.expected}
    return Score(
        caught=[
            (expected, [flag.check for flag in raised if flag.unit_id == expected.unit_id])
            for expected in fixture.expected
        ],
        unexpected=[flag for flag in raised if flag.unit_id not in named],
    )
