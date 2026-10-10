"""The self-training loop: label cheaply, train locally, promote only what beats Jev.

Each round:
1. A teacher model labels the examples the current models are least sure about
   (active learning), within a spending budget.
2. One small model per taste question is trained on every label (person > outcome >
   teacher).
3. Each model is scored on people's labels by cross-validation. It replaces Jev for that
   question only when it agrees with the person at least as often as Jev did.

A person's labels are the benchmark. Without them nothing is promoted, because a model
trained only by the teacher would learn the teacher's taste rather than yours.
"""

import json
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from content.judging.questions import QUESTIONS
from content.learning.examples import Example, Label, LearningStore, jev_label
from content.learning.labelling import meaning, options, uncertainty
from content.learning.model import Embedder, TasteModel, Vectors, example_text, fit
from content.learning.provider import ModelRegistry, Promotion
from content.models import ModelConfig
from content.providers.base import ModelProvider
from content.schemas.base import ImmutableModel
from content.state import CallRecord, call_record


class TeacherLabel(ImmutableModel):
    answer: str
    reason: str


class Teacher:
    """A capable model labelling examples against the question and the channel's taste."""

    def __init__(self, provider: ModelProvider, model: ModelConfig, instructions: str) -> None:
        self.provider = provider
        self.model = model
        self.instructions = instructions

    def label(self, example: Example) -> tuple[Label | None, CallRecord]:
        question = QUESTIONS[example.question_id]
        allowed = {value: meaning(question, value) for value in options(question).values()}
        started = time.perf_counter()
        result, usage = self.provider.generate_structured(
            instructions=self.instructions,
            input_text=json.dumps(
                {
                    "question": question.instructions,
                    "options": allowed,
                    "state": example.state,
                },
                ensure_ascii=False,
            ),
            output_type=TeacherLabel,
            model=self.model,
        )
        call = call_record("teacher_label", usage, time.perf_counter() - started)
        if result.answer not in allowed:
            return None, call
        return (
            Label(
                example_id=example.example_id,
                question_id=example.question_id,
                answer=result.answer,
                source="teacher",
                reason=result.reason,
            ),
            call,
        )


@dataclass
class QuestionReport:
    question_id: str
    labels: int
    gold: int
    local_accuracy: float | None = None
    jev_accuracy: float | None = None
    promoted: bool = False
    note: str = ""


@dataclass
class TrainingReport:
    questions: list[QuestionReport] = field(default_factory=list)
    teacher_calls: list[CallRecord] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(call["cost_usd"] or 0.0 for call in self.teacher_calls)


def train(
    store: LearningStore,
    registry: ModelRegistry,
    embedder: Embedder,
    questions: Collection[str],
    *,
    teacher: Teacher | None = None,
    budget_usd: float = 0.0,
    max_teacher_labels: int = 0,
    rounds: int = 3,
    min_labels: int = 12,
    min_gold: int = 8,
) -> TrainingReport:
    report = TrainingReport()
    examples = [e for e in store.examples().values() if e.question_id in questions]
    vectors = _embed(embedder, examples)
    models: dict[str, TasteModel] = {}
    per_round = max(max_teacher_labels // max(rounds, 1), 1)
    for _ in range(rounds):
        models = _fit_all(store, embedder, examples, vectors, questions, min_labels)
        if teacher is None or len(report.teacher_calls) >= max_teacher_labels:
            break
        labelled = set(store.best_labels())
        pool = [e for e in examples if e.example_id not in labelled]
        pool.sort(key=lambda e: _uncertainty(e, models, vectors), reverse=True)
        for example in pool[:per_round]:
            if report.cost_usd >= budget_usd or len(report.teacher_calls) >= max_teacher_labels:
                break
            label, call = teacher.label(example)
            report.teacher_calls.append(call)
            if label is not None:
                store.add_labels([label])
    report.questions = _evaluate_and_promote(
        store, registry, embedder, examples, vectors, questions, min_labels, min_gold
    )
    return report


def _embed(embedder: Embedder, examples: Sequence[Example]) -> dict[str, Vectors]:
    if not examples:
        return {}
    texts = [example_text(QUESTIONS[e.question_id], e.state) for e in examples]
    return {e.example_id: vector for e, vector in zip(examples, embedder.embed(texts), strict=True)}


def _labelled(
    store: LearningStore,
    examples: Sequence[Example],
    question_id: str,
) -> list[tuple[Example, Label]]:
    best = store.best_labels()
    return [
        (e, best[e.example_id])
        for e in examples
        if e.question_id == question_id and e.example_id in best
    ]


def _fit_all(
    store: LearningStore,
    embedder: Embedder,
    examples: Sequence[Example],
    vectors: dict[str, Vectors],
    questions: Collection[str],
    min_labels: int,
) -> dict[str, TasteModel]:
    models = {}
    for question_id in questions:
        items = _labelled(store, examples, question_id)
        if len(items) >= min_labels and len({label.answer for _, label in items}) >= 2:
            models[question_id] = _fit(question_id, embedder, items, vectors)
    return models


def _fit(
    question_id: str,
    embedder: Embedder,
    items: Sequence[tuple[Example, Label]],
    vectors: dict[str, Vectors],
) -> TasteModel:
    matrix = np.array([vectors[e.example_id] for e, _ in items])
    return fit(question_id, embedder.name, matrix, [label.answer for _, label in items])


def _uncertainty(example: Example, models: dict[str, TasteModel], vectors: dict[str, Any]) -> float:
    model = models.get(example.question_id)
    if model is None:
        return uncertainty(example)
    probabilities = model.probabilities(vectors[example.example_id])
    options_count = len(QUESTIONS[example.question_id].criteria)
    top = max(probabilities.values())
    return 1 - (options_count * top - 1) / (options_count - 1)


def _evaluate_and_promote(
    store: LearningStore,
    registry: ModelRegistry,
    embedder: Embedder,
    examples: Sequence[Example],
    vectors: dict[str, Vectors],
    questions: Collection[str],
    min_labels: int,
    min_gold: int,
) -> list[QuestionReport]:
    reports = []
    for question_id in sorted(questions):
        items = _labelled(store, examples, question_id)
        gold = [(e, label) for e, label in items if label.source == "human"]
        entry = QuestionReport(question_id=question_id, labels=len(items), gold=len(gold))
        reports.append(entry)
        if len(items) < min_labels or len({label.answer for _, label in items}) < 2:
            entry.note = f"needs at least {min_labels} labels of two kinds"
            continue
        if len(gold) < min_gold:
            entry.note = f"needs {min_gold - len(gold)} more of your labels to be judged"
            continue
        entry.jev_accuracy = sum(jev_label(e.jev) == label.answer for e, label in gold) / len(gold)
        entry.local_accuracy = _cross_validated_accuracy(
            question_id, embedder, items, gold, vectors
        )
        if entry.local_accuracy >= entry.jev_accuracy:
            registry.promote(
                _fit(question_id, embedder, items, vectors),
                Promotion(
                    question_id=question_id,
                    trained_on=len(items),
                    gold_examples=len(gold),
                    local_accuracy=round(entry.local_accuracy, 3),
                    jev_accuracy=round(entry.jev_accuracy, 3),
                ),
            )
            entry.promoted = True
        else:
            demoted = registry.demote(question_id)
            entry.note = "Jev agrees with you more often" + (
                ": handed back to Jev" if demoted else ""
            )
    return reports


def _cross_validated_accuracy(
    question_id: str,
    embedder: Embedder,
    items: Sequence[tuple[Example, Label]],
    gold: Sequence[tuple[Example, Label]],
    vectors: dict[str, Vectors],
    folds: int = 5,
) -> float:
    """Each person-labelled example is predicted by a model that never saw it."""
    correct = total = 0
    gold_ids = [e.example_id for e, _ in gold]
    for fold in range(min(folds, len(gold_ids))):
        held_out = set(gold_ids[fold::folds])
        training = [(e, label) for e, label in items if e.example_id not in held_out]
        if len({label.answer for _, label in training}) < 2:
            continue
        model = _fit(question_id, embedder, training, vectors)
        for e, label in gold:
            if e.example_id in held_out:
                probabilities = model.probabilities(vectors[e.example_id])
                correct += max(probabilities, key=lambda k: probabilities[k]) == label.answer
                total += 1
    return correct / total if total else 0.0
