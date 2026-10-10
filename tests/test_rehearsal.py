"""Before a paid run: what a run would send to paid models is proven well formed, for every
configuration and channel present, without spending anything.

- Every structured output a model is asked for converts to the strict JSON schema the API
  requires (the same conversion the OpenAI SDK does before it sends a request).
- No model call asks for an output this file does not check.
- Every configuration builds its whole graph, loading every prompt it would send.
- Every configuration's theme and prompts carry a story from research to the final package,
  each agent called with valid JSON input and its own instructions.
"""

import ast
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel

from content.config import ContentConfig, load_config
from content.learning.train import TeacherLabel
from content.production.media import FakeMediaProvider
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.schemas.audience import AudienceReport, StoryDecisions
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Critique
from content.schemas.perception import Perception
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.review import ReviewRequest, ReviewResponse
from content.schemas.script import LineEditPackage, ScriptPackage
from content.schemas.visuals import VisualPackage
from content.theme import theme_guidance
from content.workflow.checkpoint import create_checkpointer
from content.workflow.demo import demo_answer, demo_response
from content.workflow.graph import build_graph
from content.workflow.run import create_initial_state

PROJECT_ROOT = Path(__file__).parents[1]
CONFIGS = sorted(PROJECT_ROOT.glob("config/*.json")) + sorted(
    PROJECT_ROOT.glob("themes/*/config.json")
)
STRUCTURED_OUTPUTS: tuple[type[BaseModel], ...] = (
    ResearchPack,
    EditorialBrief,
    Critique,
    AudienceReport,
    StoryDecisions,
    ScriptPackage,
    LineEditPackage,
    FactCheckReport,
    VisualPackage,
    Perception,
    TeacherLabel,
)
THEMED_AGENTS = ("editorial_director", "script_writer", "visual_director")


@pytest.mark.parametrize("output_type", STRUCTURED_OUTPUTS, ids=lambda t: t.__name__)
def test_every_structured_output_is_a_strict_schema_the_api_accepts(
    output_type: type[BaseModel],
) -> None:
    sdk = pytest.importorskip("openai.lib._parsing._completions")

    schema = sdk.type_to_response_format_param(output_type)

    assert schema["type"] == "json_schema"
    assert schema["json_schema"]["strict"] is True


def test_no_model_call_asks_for_an_output_that_is_not_checked_here() -> None:
    checked = {output.__name__ for output in STRUCTURED_OUTPUTS}
    asked: set[str] = set()
    for path in (PROJECT_ROOT / "src/content").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "generate" and len(node.args) >= 2:
                asked |= _names(node.args[1])
            if node.func.attr in {"generate_structured", "parse"}:
                for keyword in node.keywords:
                    if keyword.arg in {"output_type", "response_format"}:
                        asked |= _names(keyword.value)

    # `output_type` itself is the generic pass-through in the agents' base class.
    assert asked - {"output_type"} <= checked


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_every_configuration_builds_its_graph_with_every_prompt_it_sends(path: Path) -> None:
    config = load_config(path)

    build_graph(
        config=_without_local_models(config),
        providers=_fakes(config),
        decision_provider=FakeDecisionProvider(demo_answer),
        media_provider=FakeMediaProvider() if config.production is not None else None,
    )


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_every_configuration_carries_a_story_to_its_final_package(path: Path) -> None:
    # Text stages only: the media stages rehearse in the video tests (`pytest -m video`).
    config = replace(_without_local_models(load_config(path)), production=None)
    provider = FakeModelProvider(default_factory=demo_response)
    graph = build_graph(
        config=config,
        providers=dict.fromkeys(_provider_names(config), provider),
        decision_provider=FakeDecisionProvider(demo_answer),
        checkpointer=create_checkpointer(),
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": f"rehearsal-{path.stem}"}}
    initial = create_initial_state(
        "The Great Stink", source_material=None, user_instructions=None, config=config
    )

    result = cast(dict[str, Any], graph.invoke(initial, runtime))
    for _ in range(20):
        if not result.get("__interrupt__"):
            break
        # Every sign-off the person would see is a well-formed review request.
        ReviewRequest.model_validate(result["__interrupt__"][0].value)
        approval = ReviewResponse(action="approve", decided_by="person")
        result = cast(
            dict[str, Any], graph.invoke(Command[Any](resume=approval.model_dump()), runtime)
        )

    assert result["status"] == "approved"
    assert result["final_package"] is not None
    asked = [call.output_type for call in provider.calls]
    for output in (ResearchPack, EditorialBrief, ScriptPackage, FactCheckReport, VisualPackage):
        assert output in asked, f"{output.__name__} was never generated"
    guidance = theme_guidance(config.theme)
    for call in provider.calls:
        json.loads(call.input_text)
        assert call.instructions.strip()
    themed = [call for call in provider.calls if call.output_type is ScriptPackage]
    assert all(guidance in call.instructions for call in themed)
    research = [call for call in provider.calls if call.output_type is ResearchPack]
    assert all(guidance not in call.instructions for call in research)


def _names(node: ast.expr) -> set[str]:
    return {node.id} if isinstance(node, ast.Name) else set()


def _provider_names(config: ContentConfig) -> set[str]:
    return {model.provider for model in config.models.models.values()}


def _fakes(config: ContentConfig) -> dict[str, FakeModelProvider]:
    return dict.fromkeys(_provider_names(config), FakeModelProvider(default_factory=demo_response))


def _without_local_models(config: ContentConfig) -> ContentConfig:
    """The local NLI model is downloaded on first use; a rehearsal never downloads."""
    if config.learning is None:
        return config
    return replace(config, learning=replace(config.learning, nli_model=None))
