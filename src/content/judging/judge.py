"""Jev at work: every fixed question about one story node or connection, asked in one
batch, each answer turned into an outcome by the thresholds in configuration."""

import time
from typing import Any, TypedDict

from content.judging.outcomes import DecisionConfig, answer_outcome
from content.judging.questions import Target, questions_for
from content.providers.base import DecisionProvider
from content.schemas.judgement import JudgedStage, Judgement
from content.state import CallRecord, ContentState, call_record


class JudgementTask(TypedDict):
    stage: JudgedStage
    revision: int
    target: Target
    target_id: str
    # Only the fields the target's questions name; unrelated state distracts Jev.
    state: dict[str, Any]
    # The plan's answer for questions that compare against it (transition tension).
    expected: str | None


class Judge:
    def __init__(self, decision_provider: DecisionProvider, decisions: DecisionConfig) -> None:
        self.decision_provider = decision_provider
        self.decisions = decisions

    def judge(self, state: JudgementTask) -> ContentState:
        """Ask Jev every question about one story node or connection, in one batch.

        Each run receives one task from the fan-out in `routing.py` as its input state.
        """
        judgements, call = self.evaluate(state)
        return {"judgements": judgements, "call_log": [call]}

    def evaluate(self, task: JudgementTask) -> tuple[list[Judgement], CallRecord]:
        """One Jev batch: every question for the task's target, over the task's state."""
        questions = questions_for(task["target"])
        started = time.perf_counter()
        result = self.decision_provider.decide(
            model=self.decisions.model,
            state=task["state"],
            questions={question.question_id: question.request() for question in questions},
        )
        judgements = [
            Judgement(
                stage=task["stage"],
                revision=task["revision"],
                target_id=task["target_id"],
                question_id=question.question_id,
                answer=result.answers[question.question_id],
                expected=task["expected"],
                outcome=answer_outcome(
                    question,
                    result.answers[question.question_id],
                    task["expected"],
                    self.decisions,
                ),
                blocking=question.question_id in self.decisions.blocking,
                model=result.answered_by.get(question.question_id, result.usage.model),
            )
            for question in questions
        ]
        seconds = time.perf_counter() - started
        return judgements, call_record(f"judge_{task['target']}", result.usage, seconds)
