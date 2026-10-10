"""The model registry: each alias in a configuration names a provider, a model, its reasoning
effort and its output limit."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Self

Effort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


@dataclass(frozen=True, slots=True)
class ModelConfig:
    provider: str
    model: str
    max_output_tokens: int = 4000
    effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    models: Mapping[str, ModelConfig]

    @classmethod
    def create(cls, models: Mapping[str, ModelConfig]) -> Self:
        return cls(models=MappingProxyType(dict(models)))

    def get(self, alias: str) -> ModelConfig:
        try:
            return self.models[alias]
        except KeyError as exc:
            raise KeyError(f"Unknown model alias: {alias}") from exc
