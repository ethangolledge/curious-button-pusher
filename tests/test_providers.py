from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from content.config import load_config
from content.errors import ConfigurationError, InputError
from content.judging.questions import QUESTIONS
from content.models import ModelConfig
from content.providers.openrouter import (
    OpenRouterDecisionProvider,
    OpenRouterModelProvider,
    key_credit_remaining,
)
from content.workflow.providers import fit_cap_to_credit


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class StubCompletions:
    def __init__(self, message: SimpleNamespace, usage: SimpleNamespace | None) -> None:
        self.message = message
        self.usage = usage
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            model="anthropic/claude-sonnet-5-20260801",
            choices=[SimpleNamespace(message=self.message)],
            usage=self.usage,
        )


class StubChatClient:
    def __init__(
        self,
        parsed: ExampleOutput | None,
        *,
        refusal: str | None = None,
        usage: SimpleNamespace | None = None,
    ) -> None:
        message = SimpleNamespace(parsed=parsed, refusal=refusal)
        self.completions = StubCompletions(message, usage)
        self.chat = SimpleNamespace(completions=self.completions)


MODEL = ModelConfig(
    provider="openrouter",
    model="anthropic/claude-sonnet-5",
    max_output_tokens=321,
    effort="medium",
)


def test_chat_request_carries_schema_effort_and_capable_routing() -> None:
    usage = SimpleNamespace(prompt_tokens=1200, completion_tokens=300, cost=0.0054)
    client = StubChatClient(ExampleOutput(value="validated"), usage=usage)

    result, recorded = OpenRouterModelProvider(client=client).generate_structured(
        instructions="Return a value.",
        input_text='{"topic": "example"}',
        output_type=ExampleOutput,
        model=MODEL,
    )

    request = client.completions.calls[0]
    assert result == ExampleOutput(value="validated")
    assert request["model"] == "anthropic/claude-sonnet-5"
    assert request["response_format"] is ExampleOutput
    assert request["max_tokens"] == 321
    assert request["messages"][0] == {"role": "system", "content": "Return a value."}
    assert request["extra_body"] == {
        "provider": {"require_parameters": True},
        "reasoning": {"effort": "medium"},
    }
    assert recorded.model == "anthropic/claude-sonnet-5-20260801"
    assert (recorded.input_tokens, recorded.output_tokens, recorded.cost_usd) == (1200, 300, 0.0054)


def test_web_search_is_added_only_when_requested() -> None:
    client = StubChatClient(ExampleOutput(value="found"))

    OpenRouterModelProvider(client=client).generate_structured(
        instructions="Research.",
        input_text="{}",
        output_type=ExampleOutput,
        model=MODEL,
        web_search=True,
    )

    assert client.completions.calls[0]["extra_body"]["plugins"] == [
        {"id": "web", "engine": "native"}
    ]


def test_refusal_and_missing_output_fail_clearly() -> None:
    provider = OpenRouterModelProvider(client=StubChatClient(None, refusal="Not permitted."))
    with pytest.raises(RuntimeError, match="refused the request: Not permitted."):
        provider.generate_structured(
            instructions="x", input_text="{}", output_type=ExampleOutput, model=MODEL
        )

    provider = OpenRouterModelProvider(client=StubChatClient(None))
    with pytest.raises(RuntimeError, match="no parsed structured output"):
        provider.generate_structured(
            instructions="x", input_text="{}", output_type=ExampleOutput, model=MODEL
        )


class StubHttpClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, path: str, *, json: dict[str, Any]) -> SimpleNamespace:
        self.calls.append((path, json))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: self.payload)


def test_decisions_request_and_answers_map_all_three_question_types() -> None:
    client = StubHttpClient(
        {
            "model": "typesafe/jev-1.13-20260917",
            "answers": {
                "script_payoff": {"type": "noul", "noul": 0.91},
                "scene_duplication": {
                    "type": "choice",
                    "choice": "adds",
                    "confidence": 0.75,
                    "probabilities": {"adds": 0.84, "reinforces": 0.16, "duplicates": 0},
                },
                "opening_hook": {
                    "type": "score",
                    "score": 1.99,
                    "confidence": 0.99,
                    "legend": {"0": "Weak", "1": "Adequate", "2": "Strong"},
                    "probabilities": {"0": 0, "1": 0.01, "2": 0.99},
                },
            },
            "usage": {"input_tokens": 476, "output_tokens": 70, "cost": 0.00002},
        }
    )
    questions = {
        question_id: QUESTIONS[question_id].request()
        for question_id in ("script_payoff", "scene_duplication", "opening_hook")
    }

    result = OpenRouterDecisionProvider(client=client).decide(
        model="typesafe/jev-1.13",
        state={"opening": "Why did the vote fail?"},
        questions=questions,
    )

    path, body = client.calls[0]
    assert path == "/alpha/decisions"
    assert body["model"] == "typesafe/jev-1.13"
    assert body["questions"]["script_payoff"]["type"] == "noul"
    assert set(body["questions"]["script_payoff"]["criteria"]) == {"true", "false"}
    assert isinstance(body["questions"]["opening_hook"]["criteria"], list)
    assert result.answers["script_payoff"].noul == 0.91
    assert result.answers["scene_duplication"].choice == "adds"
    assert result.answers["opening_hook"].probabilities == {"0": 0, "1": 0.01, "2": 0.99}
    assert result.usage.model == "typesafe/jev-1.13-20260917"
    assert result.usage.cost_usd == 0.00002


def test_missing_key_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        OpenRouterDecisionProvider()


class StubKeyClient:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.paths: list[str] = []

    def get(self, path: str) -> SimpleNamespace:
        self.paths.append(path)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": self.data})


def test_key_credit_reads_the_keys_remaining_limit() -> None:
    client = StubKeyClient({"limit": 30.0, "limit_remaining": 1.75, "usage": 28.25})

    assert key_credit_remaining(client) == 1.75
    assert client.paths == ["/v1/key"]
    assert key_credit_remaining(StubKeyClient({"limit": None, "limit_remaining": None})) is None


def test_a_run_is_capped_at_what_the_key_can_pay(project_root: Path) -> None:
    config = load_config(project_root / "config/config.fake-video.json")
    assert config.production is not None
    config = replace(config, production=replace(config.production, max_usd=5.0))

    fitted = fit_cap_to_credit(config, 3.65)
    assert fitted.production is not None and fitted.production.max_usd == 3.40
    assert fit_cap_to_credit(config, 9.0) is config
    assert fit_cap_to_credit(config, None) is config
    with pytest.raises(InputError, match=r"\$0\.26 left, too little for a run"):
        fit_cap_to_credit(config, 0.26)
    no_video = replace(config, production=None)
    assert fit_cap_to_credit(no_video, 0.26) is no_video
