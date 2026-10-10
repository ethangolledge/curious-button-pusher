"""Our own small decision models: one calibrated classifier per taste question.

Each is multinomial logistic regression over sentence embeddings of the same state Jev
would see. It trains in well under a second on a laptop CPU and returns probabilities,
so its answers slot into the same pass/fail/unsure thresholds as Jev's.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from content.judging.questions import Question
from content.schemas.base import ImmutableModel
from content.schemas.judgement import Answer

Vectors = NDArray[np.float64]


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> Vectors: ...


class FastEmbedder:
    """A small sentence-embedding model run locally on ONNX (no GPU, no PyTorch)."""

    def __init__(self, model_name: str, cache_directory: Path) -> None:
        self.name = model_name
        self._cache_directory = cache_directory
        self._model: Any = None

    def embed(self, texts: Sequence[str]) -> Vectors:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError("Local models require: pip install -e '.[learn]'") from exc
            self._model = TextEmbedding(self.name, cache_dir=str(self._cache_directory))
        return np.array(list(self._model.embed(list(texts))), dtype=np.float64)


def example_text(question: Question, state: dict[str, Any]) -> str:
    """What the model reads: the question, then the state it is asked about."""
    return f"{question.instructions}\n{json.dumps(state, ensure_ascii=False, sort_keys=True)}"


class TasteModel(ImmutableModel):
    question_id: str
    embedder: str
    classes: list[str]
    weights: list[list[float]]
    bias: list[float]

    def probabilities(self, vector: Vectors) -> dict[str, float]:
        scores = np.array(self.weights) @ vector + np.array(self.bias)
        return dict(zip(self.classes, _softmax(scores).tolist(), strict=True))


def fit(
    question_id: str,
    embedder: str,
    vectors: Vectors,
    labels: Sequence[str],
    *,
    regularisation: float = 1.0,
    steps: int = 400,
    learning_rate: float = 0.5,
) -> TasteModel:
    """Multinomial logistic regression by gradient descent, with L2 regularisation."""
    classes = sorted(set(labels))
    if len(classes) < 2:
        raise ValueError(f"{question_id} needs labels of at least two kinds to learn from")
    targets = np.zeros((len(labels), len(classes)))
    for row, label in enumerate(labels):
        targets[row, classes.index(label)] = 1.0
    weights = np.zeros((len(classes), vectors.shape[1]))
    bias = np.zeros(len(classes))
    count = len(labels)
    for _ in range(steps):
        predicted = _softmax(vectors @ weights.T + bias)
        error = predicted - targets
        weights -= learning_rate * (error.T @ vectors / count + regularisation * weights / count)
        bias -= learning_rate * error.mean(axis=0)
    return TasteModel(
        question_id=question_id,
        embedder=embedder,
        classes=classes,
        weights=weights.round(6).tolist(),
        bias=bias.round(6).tolist(),
    )


def to_answer(question: Question, probabilities: dict[str, float]) -> Answer:
    """Our probabilities in Jev's answer shape, with Jev's definition of confidence."""
    if question.kind == "noul":
        return Answer(kind="noul", noul=round(probabilities.get("yes", 0.0), 4))
    options = (
        list(question.criteria)
        if isinstance(question.criteria, dict)
        else [str(level) for level in range(len(question.criteria))]
    )
    full = {option: round(probabilities.get(option, 0.0), 4) for option in options}
    top = max(full, key=lambda option: full[option])
    # TypeSafe's confidence: how concentrated the distribution is, 0 (even) to 1 (certain).
    confidence = (len(full) * full[top] - 1) / (len(full) - 1)
    if question.kind == "choice":
        return Answer(kind="choice", choice=top, confidence=confidence, probabilities=full)
    score = sum(int(level) * p for level, p in full.items())
    return Answer(kind="score", score=score, confidence=confidence, probabilities=full)


def _softmax(scores: NDArray[np.float64]) -> NDArray[np.float64]:
    shifted = np.exp(scores - scores.max(axis=-1, keepdims=True))
    result: NDArray[np.float64] = shifted / shifted.sum(axis=-1, keepdims=True)
    return result
