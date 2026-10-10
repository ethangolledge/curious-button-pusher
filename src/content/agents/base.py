"""What every agent shares: its prompt, its model, and one structured call that is timed
and recorded.

An agent's folder holds `agent.py` (the code), `prompt.md` (what its model is told) and, for
an agent with more than one job, one `<job>_prompt.md` per job (`critic_prompt.md`)."""

import json
import logging
import time
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from content.config import AgentConfig
from content.models import ModelRegistry
from content.providers.base import ModelProvider, Usage
from content.providers.cache import AssetCache
from content.state import CallRecord, call_record

T = TypeVar("T", bound=BaseModel)


def load_prompt(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Prompt does not exist: {path}")
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt is empty: {path}")
    return prompt


class Agent:
    """One role: its prompt, with the theme's guidance when the role shapes how the video
    looks and sounds, and its model."""

    # The job this class does, when it is not the agent's main one: its prompt is
    # `<job>_prompt.md` beside the agent's `prompt.md`.
    job: str | None = None

    def __init__(
        self,
        *,
        name: str,
        config: AgentConfig,
        models: ModelRegistry,
        provider: ModelProvider,
        guidance: str | None = None,
        cache: AssetCache | None = None,
    ) -> None:
        self.name = name
        self.config = config
        self.models = models
        self.provider = provider
        self.guidance = guidance
        # Every paid answer is kept by its full request: asking the same thing again (a
        # resumed run, the same research for another video) costs nothing.
        self.cache = cache
        self.instructions = self.prompt(self.job)
        self.logger = logging.getLogger(f"content.agents.{name}")

    @property
    def model_alias(self) -> str:
        return self.config.model_alias

    def prompt(self, job: str | None = None) -> str:
        """The agent's own prompt, or one of its jobs' (`critic` reads `critic_prompt.md`),
        followed by the theme's guidance when the agent has it."""
        path = (
            self.config.prompt if job is None else self.config.prompt.with_name(f"{job}_prompt.md")
        )
        return "\n\n".join(part for part in (load_prompt(path), self.guidance) if part)

    def generate(
        self,
        payload: dict[str, Any],
        output_type: type[T],
        *,
        operation: str,
        web_search: bool = False,
        model_alias: str | None = None,
        instructions: str | None = None,
        indent: int | None = 2,
    ) -> tuple[T, CallRecord]:
        """One structured call: this class's model and instructions unless a narrower job
        names its own."""
        model = self.models.get(model_alias or self.model_alias)
        instructions = instructions or self.instructions
        input_text = json.dumps(payload, indent=indent, default=_json_default)
        started = time.perf_counter()

        def ask() -> tuple[bytes, Usage]:
            self.logger.info("Running %s with %s", operation, model.model)
            result, usage = self.provider.generate_structured(
                instructions=instructions,
                input_text=input_text,
                output_type=output_type,
                model=model,
                web_search=web_search,
            )
            answer = output_type.model_validate(result)
            return answer.model_dump_json(exclude_computed_fields=True).encode(), usage

        if self.cache is None:
            content, usage = ask()
        else:
            request = {
                "model": model.model,
                "effort": model.effort,
                "max_output_tokens": model.max_output_tokens,
                "output": output_type.__name__,
                "web_search": web_search,
                "instructions": instructions,
                "input": input_text,
            }
            path, paid = self.cache.fetch(
                f"text/{operation}", request, ".json", ask, about=f"{self.name}: {operation}"
            )
            content = path.read_bytes()
            # Served from the cache: nothing was spent.
            usage = paid or Usage(model=model.model, cost_usd=0.0)
        output = output_type.model_validate_json(content)
        return output, call_record(
            operation,
            usage,
            time.perf_counter() - started,
            output=output.model_dump(mode="json", exclude_computed_fields=True),
        )


def _json_default(value: object) -> object:
    # Computed fields (a script's hook and master script) only repeat the units.
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_computed_fields=True)
    raise TypeError(f"Cannot serialize {type(value).__name__} for model input")
