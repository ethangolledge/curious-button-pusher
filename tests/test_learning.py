from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from content.judging.questions import QUESTIONS
from content.learning.examples import Example, Label, LearningStore, example_id
from content.learning.labelling import label_interactively
from content.learning.model import Vectors, fit, to_answer
from content.learning.provider import ModelRegistry, RoutedDecisionProvider
from content.learning.train import Teacher, TeacherLabel, train
from content.models import ModelConfig
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.schemas.judgement import Answer

WORDS = ("slow", "right", "crowded")


class WordEmbedder:
    """Counts three marker words: a deterministic stand-in for sentence embeddings."""

    name = "words"

    def embed(self, texts: Sequence[str]) -> Vectors:
        return np.array([[text.count(word) for word in WORDS] for text in texts], dtype=float)


def _example(text: str, jev_choice: str) -> Example:
    state = {"narrative_job": "reveal", "intended_feeling": "unease", "unit": {"text": text}}
    return Example(
        example_id=example_id("unit_pace", state),
        question_id="unit_pace",
        state=state,
        jev=Answer(kind="choice", choice=jev_choice, confidence=0.4),
    )


def _pace_store(tmp_path: Path) -> LearningStore:
    """Twelve examples a person labelled by the marker word; Jev always said "right"."""
    store = LearningStore(tmp_path)
    examples = [
        _example(f"take {index}: {word} {word}", "right")
        for index in range(4)
        for word in ("slow", "right", "crowded")
    ]
    store.add_examples(examples)
    answers = {"slow": "too_slow", "right": "right", "crowded": "overloaded"}
    store.add_labels(
        Label(
            example_id=e.example_id,
            question_id="unit_pace",
            answer=answers[e.state["unit"]["text"].split()[-1]],
            source="human",
        )
        for e in examples
    )
    return store


def test_a_persons_label_outranks_outcomes_and_teachers(tmp_path: Path) -> None:
    store = LearningStore(tmp_path)
    labels = [
        Label(example_id="e1", question_id="unit_pace", answer=answer, source=source)
        for answer, source in (("right", "teacher"), ("too_slow", "human"), ("right", "outcome"))
    ]

    assert len(store.add_labels(labels + labels)) == 3
    assert len(store.labels()) == 3
    assert store.add_labels(labels) == []
    assert store.best_labels()["e1"].answer == "too_slow"


def test_trained_models_answer_in_jevs_shape() -> None:
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]])
    model = fit("script_payoff", "words", vectors, ["yes", "yes", "no", "no"])

    answer = to_answer(QUESTIONS["script_payoff"], model.probabilities(np.array([1.0, 0.0])))

    assert answer.kind == "noul"
    assert answer.noul is not None and answer.noul > 0.6


def test_training_promotes_a_model_only_when_it_beats_jev(tmp_path: Path) -> None:
    store = _pace_store(tmp_path)
    registry = ModelRegistry(tmp_path)

    report = train(store, registry, WordEmbedder(), {"unit_pace"}, min_labels=12, min_gold=8)

    (entry,) = report.questions
    assert entry.promoted
    assert entry.jev_accuracy is not None and round(entry.jev_accuracy, 2) == 0.33
    assert entry.local_accuracy == 1.0
    assert registry.promotions()["unit_pace"].gold_examples == 12


def test_training_without_enough_of_your_labels_promotes_nothing(tmp_path: Path) -> None:
    store = _pace_store(tmp_path)
    registry = ModelRegistry(tmp_path)

    report = train(store, registry, WordEmbedder(), {"unit_pace"}, min_gold=20)

    assert not report.questions[0].promoted
    assert "8 more of your labels" in report.questions[0].note
    assert registry.promotions() == {}


def test_promoted_questions_are_answered_locally_and_the_rest_go_to_jev(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    train(_pace_store(tmp_path), registry, WordEmbedder(), {"unit_pace"})

    def jev(question_id: str, state: Mapping[str, Any]) -> Answer:
        return Answer(kind="noul", noul=0.9)

    api = FakeDecisionProvider(jev)
    router = RoutedDecisionProvider(api, registry, WordEmbedder(), {"unit_pace"})
    questions = {q: QUESTIONS[q].request() for q in ("unit_pace", "unit_supported")}

    decisions = router.decide(
        model="jev", state={"unit": {"text": "crowded crowded"}}, questions=questions
    )

    assert decisions.answers["unit_pace"].choice == "overloaded"
    assert decisions.answers["unit_supported"].noul == 0.9
    assert [call.question_ids for call in api.calls] == [("unit_supported",)]


def test_teacher_labels_the_least_certain_examples_within_the_cap(tmp_path: Path) -> None:
    store = LearningStore(tmp_path)
    store.add_examples(
        [_example("slow slow", "right"), _example("crowded", "right"), _example("x", "right")]
    )
    provider = FakeModelProvider(
        {
            TeacherLabel: [
                TeacherLabel(answer="too_slow", reason="It repeats itself."),
                TeacherLabel(answer="made_up", reason="Not an option."),
            ]
        }
    )
    teacher = Teacher(provider, ModelConfig(provider="fake", model="teacher"), "Label it.")

    report = train(
        store,
        ModelRegistry(tmp_path),
        WordEmbedder(),
        {"unit_pace"},
        teacher=teacher,
        budget_usd=1.0,
        max_teacher_labels=2,
    )

    assert len(report.teacher_calls) == 2
    assert [label.answer for label in store.labels()] == ["too_slow"]
    assert '"too_slow"' in provider.calls[0].input_text


def test_labelling_records_a_persons_answers(tmp_path: Path) -> None:
    store = LearningStore(tmp_path)
    store.add_examples([_example("slow slow", "right"), _example("crowded", "right")])
    typed = iter(["9", "1", "q"])

    saved = label_interactively(
        store, {"unit_pace"}, count=5, read=lambda _: next(typed), write=lambda _: None
    )

    assert saved == 1
    assert [(label.answer, label.source) for label in store.labels()] == [("too_slow", "human")]


def test_a_promoted_model_that_falls_behind_jev_hands_the_question_back(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    train(_pace_store(tmp_path), registry, WordEmbedder(), {"unit_pace"})
    assert "unit_pace" in registry.promotions()
    # New labels the marker words cannot explain, all of which Jev answered correctly.
    store = LearningStore(tmp_path)
    answers = ["too_slow", "right", "overloaded"] * 6
    examples = [_example(f"plain line {index}", answer) for index, answer in enumerate(answers)]
    store.add_examples(examples)
    store.add_labels(
        Label(
            example_id=e.example_id,
            question_id="unit_pace",
            answer=e.jev.choice or "",
            source="human",
        )
        for e in examples
    )

    report = train(store, registry, WordEmbedder(), {"unit_pace"})

    assert "handed back to Jev" in report.questions[0].note
    assert registry.promotions() == {}
