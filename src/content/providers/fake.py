"""Deterministic stand-ins for the model providers, for the offline demo and the tests: they
record every call and answer from queued responses or a function."""

from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from content.models import ModelConfig
from content.providers.base import Decisions, Usage
from content.schemas.judgement import Answer

T = TypeVar("T", bound=BaseModel)
ResponseValue = BaseModel | Mapping[str, Any]
ResponseFactory = Callable[[str, type[BaseModel]], ResponseValue]
Responder = Callable[[str, Mapping[str, Any]], Answer | Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class FakeProviderCall:
    output_type: type[BaseModel]
    model: ModelConfig
    instructions: str
    input_text: str
    web_search: bool


class FakeModelProvider:
    """A deterministic, schema-agnostic provider driven by queued responses."""

    def __init__(
        self,
        responses: Mapping[type[BaseModel], Sequence[ResponseValue]] | None = None,
        *,
        default_factory: ResponseFactory | None = None,
    ) -> None:
        self._responses: dict[type[BaseModel], deque[ResponseValue]] = defaultdict(deque)
        for output_type, values in (responses or {}).items():
            self._responses[output_type].extend(values)
        self._default_factory = default_factory
        self.calls: list[FakeProviderCall] = []

    def generate_structured(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[T],
        model: ModelConfig,
        web_search: bool = False,
    ) -> tuple[T, Usage]:
        self.calls.append(
            FakeProviderCall(
                output_type=output_type,
                model=model,
                instructions=instructions,
                input_text=input_text,
                web_search=web_search,
            )
        )
        queued = self._responses[output_type]
        if queued:
            response = queued.popleft()
        elif self._default_factory is not None:
            response = self._default_factory(input_text, output_type)
        else:
            raise LookupError(f"No fake response configured for {output_type.__name__}")
        return output_type.model_validate(response), Usage(model=model.model)


@dataclass(frozen=True, slots=True)
class FakeDecisionCall:
    state: Mapping[str, Any]
    question_ids: tuple[str, ...]


class FakeDecisionProvider:
    """Deterministic System 1 stand-in.

    Judgements run in parallel, so answers come from a responder function of the
    question and its state rather than from a queue whose order would vary.
    """

    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self.calls: list[FakeDecisionCall] = []

    def decide(
        self,
        *,
        model: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> Decisions:
        self.calls.append(FakeDecisionCall(state=state, question_ids=tuple(questions)))
        answers = {
            question_id: Answer.model_validate(self._responder(question_id, state))
            for question_id in questions
        }
        return Decisions(answers=answers, usage=Usage(model=model))
