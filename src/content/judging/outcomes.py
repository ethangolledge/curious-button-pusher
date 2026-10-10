"""Judging: Jev's answers to the fixed questions become outcomes (pass, fail, unsure), and
a stage's outcomes become one verdict. Thresholds come from configuration. Used by the
agents, production and the graph; depends on nothing above the schemas."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from content.judging.questions import QUESTIONS, Question
from content.schemas.judgement import Answer, JudgedStage, Judgement, Outcome
from content.state import ContentState


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    """System 1 settings: which Jev model answers, and how answers become routes."""

    provider: str
    model: str
    yes_min: float
    no_max: float
    act_min: float
    blocking: frozenset[str]


VerdictRoute = Literal["accept", "revise", "human_review"]


def answer_outcome(
    question: Question,
    answer: Answer,
    expected: str | None,
    decisions: DecisionConfig,
) -> Outcome:
    """Turn one Jev answer into pass, fail, or unsure. Thresholds come from config.
    A measurement is never a verdict: code reads its answer, nothing routes on it."""
    if question.measure:
        return "pass"
    if question.kind == "noul":
        if answer.noul is None:
            return "unsure"
        if answer.noul >= decisions.yes_min:
            return "pass"
        return "fail" if answer.noul <= decisions.no_max else "unsure"
    if answer.confidence is None or answer.confidence < decisions.act_min:
        return "unsure"
    if question.kind == "choice":
        if expected is not None:
            return "pass" if answer.choice == expected else "fail"
        return "fail" if answer.choice in question.failing_choices else "pass"
    return "pass" if _score_level(answer) >= question.pass_level else "fail"


def _score_level(answer: Answer) -> int:
    if answer.probabilities:
        return int(max(answer.probabilities, key=lambda level: answer.probabilities[level]))
    return round(answer.score or 0)


def answer_label(answer: Answer) -> str:
    if answer.kind == "noul":
        return "no answer" if answer.noul is None else f"yes {answer.noul:.0%}"
    confidence = "" if answer.confidence is None else f" ({answer.confidence:.0%} confident)"
    if answer.kind == "choice":
        return f"{answer.choice}{confidence}"
    return f"level {_score_level(answer)}{confidence}"


@dataclass(frozen=True, slots=True)
class Verdict:
    route: VerdictRoute
    corrections: list[str]


def stage_verdict(judgements: Sequence[Judgement]) -> Verdict:
    """Any confident blocking failure revises; otherwise blocking doubt goes to a person."""
    failures = [j for j in judgements if j.blocking and j.outcome == "fail"]
    if failures:
        return Verdict(route="revise", corrections=[correction_line(j) for j in failures])
    if any(j.blocking and j.outcome == "unsure" for j in judgements):
        return Verdict(route="human_review", corrections=[])
    return Verdict(route="accept", corrections=[])


def correction_line(judgement: Judgement) -> str:
    answer = judgement.answer
    return QUESTIONS[judgement.question_id].correction.format(
        target=judgement.target_id,
        answer=(answer.choice or answer_label(answer)).replace("_", " "),
        expected=judgement.expected or "",
    )


def judgement_line(judgement: Judgement) -> str:
    role = "blocking" if judgement.blocking else "advisory"
    return (
        f"{judgement.target_id} · {judgement.question_id} ({role}): "
        f"{judgement.outcome}, {answer_label(judgement.answer)}"
    )


def current_revision(state: ContentState, stage: JudgedStage) -> int:
    counts = {
        "plan": state.get("plan_revision_count", 0),
        "script": state.get("script_revision_count", 0),
        # A listener hears one revision of the script.
        "audience": state.get("script_revision_count", 0),
        "visuals": state.get("visual_revision_count", 0),
    }
    return counts[stage]


def current_judgements(state: ContentState, stage: JudgedStage) -> list[Judgement]:
    """Judgements of the current artifact revision only; earlier ones are stale."""
    revision = current_revision(state, stage)
    return [
        judgement
        for judgement in state.get("judgements", [])
        if judgement.stage == stage and judgement.revision == revision
    ]
