"""Quick human labelling: one story node and one question at a time, in the terminal.

People's labels are the gold standard every trained model is measured against, so the
queue shows the examples Jev was least sure about first: that is where a person's
judgement teaches the most.
"""

import json
from collections.abc import Callable, Collection

from content.judging.questions import QUESTIONS, Question
from content.learning.examples import Example, Label, LearningStore


def uncertainty(example: Example) -> float:
    """0 when Jev was certain, 1 when it was split evenly."""
    answer = example.jev
    if answer.kind == "noul":
        return 1 - abs((answer.noul or 0.5) - 0.5) * 2
    return 1 - (answer.confidence or 0)


def labelling_queue(store: LearningStore, questions: Collection[str]) -> list[Example]:
    """What is most worth your time first: examples your own reviews flagged, then those
    Jev was least sure about."""
    labelled_by_person = {label.example_id for label in store.labels() if label.source == "human"}
    flagged = {flag.example_id for flag in store.flags()}
    queue = [
        example
        for example in store.examples().values()
        if example.question_id in questions and example.example_id not in labelled_by_person
    ]
    return sorted(queue, key=lambda e: (e.example_id in flagged, uncertainty(e)), reverse=True)


def options(question: Question) -> dict[str, str]:
    """Keys a person types, mapped to the label they record."""
    if question.kind == "noul":
        return {"y": "yes", "n": "no"}
    if question.kind == "choice":
        return {str(index): key for index, key in enumerate(question.criteria, start=1)}
    return {str(level): str(level) for level in range(len(question.criteria))}


def meaning(question: Question, answer: str) -> str:
    """The criterion text behind an answer, shown next to its key."""
    criteria = question.criteria
    if isinstance(criteria, tuple):
        return criteria[int(answer)]
    if question.kind == "noul":
        return criteria["true" if answer == "yes" else "false"]
    return criteria[answer]


def label_interactively(
    store: LearningStore,
    questions: Collection[str],
    *,
    count: int,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> int:
    saved = 0
    notes: dict[str, list[str]] = {}
    for flag in store.flags():
        notes.setdefault(flag.example_id, []).append(flag.note)
    for example in labelling_queue(store, questions)[:count]:
        question = QUESTIONS[example.question_id]
        choices = options(question)
        write("")
        write(f"[{example.question_id}] {question.instructions}")
        write(json.dumps(example.state, indent=2, ensure_ascii=False))
        for note in notes.get(example.example_id, []):
            write(f"  Your review: {note}")
        for key, value in choices.items():
            write(f"  [{key}] {value}: {meaning(question, value)}")
        write("  [s] skip   [q] quit")
        while True:
            try:
                typed = read("> ").strip().lower()
            except EOFError:
                return saved
            if typed == "q":
                return saved
            if typed == "s":
                break
            if typed in choices:
                store.add_labels(
                    [
                        Label(
                            example_id=example.example_id,
                            question_id=example.question_id,
                            answer=choices[typed],
                            source="human",
                        )
                    ]
                )
                saved += 1
                break
            write(f"Type one of: {', '.join(choices)}, s or q")
    return saved
