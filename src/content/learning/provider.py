"""Decisions routed per question: our own trained models where they have earned it, Jev
for everything else."""

import json
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from content.judging.questions import QUESTIONS
from content.learning.model import Embedder, TasteModel, example_text, to_answer
from content.providers.base import DecisionProvider, Decisions, Usage
from content.schemas.base import ImmutableModel
from content.schemas.judgement import Answer

# Marks a judgement answered by one of our models rather than Jev.
LOCAL_PREFIX = "local:"


class Promotion(ImmutableModel):
    """Why a local model replaced Jev for a question, measured on people's labels."""

    question_id: str
    trained_on: int
    gold_examples: int
    local_accuracy: float
    jev_accuracy: float


class ModelRegistry:
    """Promoted models live in `models/<question>.json`; `registry.json` lists them."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory / "models"
        self.index = self.directory / "registry.json"

    def promotions(self) -> dict[str, Promotion]:
        if not self.index.is_file():
            return {}
        raw = json.loads(self.index.read_text(encoding="utf-8"))
        return {question: Promotion.model_validate(entry) for question, entry in raw.items()}

    def load(self, question_id: str) -> TasteModel:
        path = self.directory / f"{question_id}.json"
        return TasteModel.model_validate_json(path.read_text(encoding="utf-8"))

    def promote(self, model: TasteModel, promotion: Promotion) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{model.question_id}.json").write_text(model.model_dump_json())
        promotions = {q: p.model_dump() for q, p in self.promotions().items()}
        promotions[model.question_id] = promotion.model_dump()
        self.index.write_text(json.dumps(promotions, indent=2) + "\n", encoding="utf-8")

    def demote(self, question_id: str) -> bool:
        """Hand a question back to Jev; True if it had been promoted."""
        promotions = {q: p.model_dump() for q, p in self.promotions().items()}
        if promotions.pop(question_id, None) is None:
            return False
        (self.directory / f"{question_id}.json").unlink(missing_ok=True)
        self.index.write_text(json.dumps(promotions, indent=2) + "\n", encoding="utf-8")
        return True


class RoutedDecisionProvider:
    """Answers questions with promoted local models when allowed; asks Jev for the rest."""

    def __init__(
        self,
        api: DecisionProvider,
        registry: ModelRegistry,
        embedder: Embedder,
        local_questions: Collection[str],
    ) -> None:
        self.api = api
        self.embedder = embedder
        promoted = registry.promotions()
        self.models = {
            question: registry.load(question)
            for question in local_questions
            if question in promoted
        }

    def decide(
        self,
        *,
        model: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> Decisions:
        local = [question for question in questions if question in self.models]
        remote = {q: body for q, body in questions.items() if q not in self.models}
        answers: dict[str, Answer] = {}
        local_model = f"{LOCAL_PREFIX}{self.embedder.name}"
        usage = Usage(model=local_model, cost_usd=0.0)
        if local:
            texts = [example_text(QUESTIONS[q], dict(state)) for q in local]
            for question_id, vector in zip(local, self.embedder.embed(texts), strict=True):
                probabilities = self.models[question_id].probabilities(vector)
                answers[question_id] = to_answer(QUESTIONS[question_id], probabilities)
        if remote:
            result = self.api.decide(model=model, state=state, questions=remote)
            answers.update(result.answers)
            usage = result.usage
        return Decisions(
            answers=answers, usage=usage, answered_by=dict.fromkeys(local, local_model)
        )
