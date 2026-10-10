"""What the pipeline asks of a model provider: one structured generation (System 2) or a batch
of typed answers from Jev (System 1), and what each call consumed."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from content.models import ModelConfig
from content.schemas.judgement import Answer

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class Usage:
    """What one provider call consumed. Unknown values stay None rather than guessed."""

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    # The model's reasoning summary, when the provider returns one. Already paid for.
    reasoning: str | None = None


class ModelProvider(Protocol):
    """System 2: generates one structured artifact."""

    def generate_structured(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[T],
        model: ModelConfig,
        web_search: bool = False,
    ) -> tuple[T, Usage]: ...


@dataclass(frozen=True, slots=True)
class Decisions:
    answers: Mapping[str, Answer]
    usage: Usage
    # Who answered each question, when not the model in `usage` (a local trained model).
    answered_by: Mapping[str, str] = field(default_factory=dict)


class DecisionProvider(Protocol):
    """System 1: answers independent typed questions about one piece of state."""

    def decide(
        self,
        *,
        model: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> Decisions: ...
