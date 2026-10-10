"""OpenRouter adapters: every text model and Jev behind one OPENROUTER_API_KEY."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from content.errors import ConfigurationError
from content.models import ModelConfig
from content.providers.base import Decisions, Usage
from content.schemas.judgement import Answer

T = TypeVar("T", bound=BaseModel)

API_ROOT = "https://openrouter.ai/api"


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ConfigurationError("Set OPENROUTER_API_KEY in .env to use the OpenRouter provider")
    return key


def key_credit_remaining(client: Any | None = None) -> float | None:
    """What this API key may still spend, in dollars; None when the key has no limit."""
    if client is None:
        import httpx

        client = httpx.Client(
            base_url=API_ROOT, headers={"Authorization": f"Bearer {_api_key()}"}, timeout=30.0
        )
    response = client.get("/v1/key")
    response.raise_for_status()
    remaining = response.json()["data"].get("limit_remaining")
    return None if remaining is None else float(remaining)


@dataclass(frozen=True)
class Account:
    """OpenRouter's own figures: the credit ever added and used on the account, and the
    key's limit, what it may still spend, and when it stops working."""

    credits_usd: float
    used_usd: float
    key_limit_usd: float | None
    key_remaining_usd: float | None
    key_expires: str | None

    @property
    def remaining_usd(self) -> float:
        """What can still be spent: the account's balance, or less if the key's limit is lower."""
        balance = self.credits_usd - self.used_usd
        if self.key_remaining_usd is None:
            return round(balance, 4)
        return round(min(balance, self.key_remaining_usd), 4)


def account_balance(client: Any | None = None) -> Account:
    """Read the account's credit and the key's limit (both free to read)."""
    if client is None:
        import httpx

        client = httpx.Client(
            base_url=API_ROOT, headers={"Authorization": f"Bearer {_api_key()}"}, timeout=30.0
        )
    credits = client.get("/v1/credits")
    credits.raise_for_status()
    key = client.get("/v1/key")
    key.raise_for_status()
    account, limits = credits.json()["data"], key.json()["data"]
    return Account(
        credits_usd=float(account["total_credits"]),
        used_usd=float(account["total_usage"]),
        key_limit_usd=None if limits.get("limit") is None else float(limits["limit"]),
        key_remaining_usd=(
            None if limits.get("limit_remaining") is None else float(limits["limit_remaining"])
        ),
        key_expires=limits.get("expires_at"),
    )


class OpenRouterModelProvider:
    """Structured generation through OpenRouter's OpenAI-compatible chat API."""

    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The OpenRouter provider requires: pip install -e '.[live]'"
            ) from exc
        self._client = OpenAI(base_url=f"{API_ROOT}/v1", api_key=_api_key())

    def generate_structured(
        self,
        *,
        instructions: str,
        input_text: str,
        output_type: type[T],
        model: ModelConfig,
        web_search: bool = False,
    ) -> tuple[T, Usage]:
        # Only route to endpoints that honour every parameter, including the schema.
        extra_body: dict[str, Any] = {"provider": {"require_parameters": True}}
        if model.effort is not None:
            extra_body["reasoning"] = {"effort": model.effort}
        if web_search:
            extra_body["plugins"] = [{"id": "web", "engine": "native"}]
        completion = self._client.chat.completions.parse(
            model=model.model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            response_format=output_type,
            max_tokens=model.max_output_tokens,
            extra_body=extra_body,
        )
        message = completion.choices[0].message
        if message.refusal:
            raise RuntimeError(f"{model.model} refused the request: {message.refusal}")
        if message.parsed is None:
            raise RuntimeError(f"{model.model} returned no parsed structured output")
        usage = completion.usage
        return output_type.model_validate(message.parsed), Usage(
            model=completion.model or model.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            cost_usd=getattr(usage, "cost", None),
            reasoning=getattr(message, "reasoning", None) or None,
        )


class OpenRouterDecisionProvider:
    """Jev through OpenRouter's Decisions API (an alpha endpoint, so kept deliberately small)."""

    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "The OpenRouter provider requires: pip install -e '.[live]'"
            ) from exc
        self._client = httpx.Client(
            base_url=API_ROOT,
            headers={"Authorization": f"Bearer {_api_key()}"},
            timeout=60.0,
            # Retry dropped connections, as the OpenAI SDK does for chat calls.
            transport=httpx.HTTPTransport(retries=2),
        )

    def decide(
        self,
        *,
        model: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
    ) -> Decisions:
        response = self._client.post(
            "/alpha/decisions",
            json={"model": model, "state": dict(state), "questions": dict(questions)},
        )
        response.raise_for_status()
        data = response.json()
        answers = {
            question_id: Answer(
                kind=raw["type"],
                noul=raw.get("noul"),
                choice=raw.get("choice"),
                score=raw.get("score"),
                confidence=raw.get("confidence"),
                probabilities={
                    str(key): value for key, value in raw.get("probabilities", {}).items()
                },
            )
            for question_id, raw in data["answers"].items()
        }
        usage = data.get("usage", {})
        return Decisions(
            answers=answers,
            usage=Usage(
                model=data.get("model", model),
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                cost_usd=usage.get("cost"),
            ),
        )
