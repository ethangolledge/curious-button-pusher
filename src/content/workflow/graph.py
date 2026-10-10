"""The graph: every node (agents, Jev, code checks, people, production) and every edge between
them, in one place. Routing decisions are in `routing.py`."""

from collections.abc import Mapping, Sequence
from functools import partial
from typing import TypeVar

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from content.agents.base import Agent
from content.agents.editorial_director.agent import EditorialDirector
from content.agents.editorial_director.critic import Critic
from content.agents.editorial_director.listener import Listener
from content.agents.fact_checker.agent import FactChecker
from content.agents.fact_researcher.agent import FactResearcher
from content.agents.script_writer.agent import ScriptWriter
from content.agents.visual_director.agent import StagedVisualDirector, VisualDirector
from content.config import ContentConfig, WorkflowConfig
from content.judging.judge import Judge, JudgementTask
from content.production.media import MediaProvider
from content.production.music_map import map_for
from content.production.producer import Producer
from content.production.studio import NarrationTask, RenderTask
from content.providers.base import DecisionProvider, ModelProvider
from content.providers.blender import Renderer
from content.providers.cache import AssetCache
from content.providers.images import ImageSource
from content.staging.catalogue import describe, load_catalogue
from content.state import ContentInput, ContentOutput, ContentState
from content.story.faithfulness import OnnxInference
from content.theme import theme_guidance
from content.workflow.director_notes import apply_director_notes
from content.workflow.final_package import assemble_final_package
from content.workflow.gates import (
    audience_verdict,
    check_script,
    check_visuals,
    plan_verdict,
    script_verdict,
    visual_verdict,
)
from content.workflow.providers import build_renderer
from content.workflow.review_requests import mark_review_stopped, request_human_review
from content.workflow.routing import (
    fan_out_audience,
    fan_out_plan,
    route_audience_verdict,
    route_director_notes,
    route_fact_check,
    route_human_review,
    route_keyframe_verdict,
    route_plan_verdict,
    route_research,
    route_script_critique,
    route_script_gate,
    route_script_verdict,
    route_segment_verdict,
    route_start,
    route_timing,
    route_visual_critique,
    route_visual_gate,
    route_visual_verdict,
)

AgentNode = TypeVar("AgentNode", bound=Agent)


def _provider_for(
    agent_name: str,
    *,
    config: ContentConfig,
    providers: Mapping[str, ModelProvider],
) -> ModelProvider:
    agent = config.agents[agent_name]
    provider_name = config.models.get(agent.model_alias).provider
    try:
        return providers[provider_name]
    except KeyError as exc:
        raise ValueError(f"No provider instance was supplied for '{provider_name}'") from exc


def build_graph(
    *,
    config: ContentConfig,
    providers: Mapping[str, ModelProvider],
    decision_provider: DecisionProvider,
    media_provider: MediaProvider | None = None,
    image_sources: Sequence[ImageSource] = (),
    checkpointer: InMemorySaver | None = None,
    fresh_research: bool = False,
    renderer: Renderer | None = None,
) -> CompiledStateGraph[ContentState, None, ContentInput, ContentOutput]:
    theme = config.theme
    guidance = theme_guidance(theme)
    # A channel that stages scenes in 3D: Blender, and what its shots can be made of.
    staged = config.production is not None and config.production.pictures == "staged"
    catalogue = load_catalogue(theme.root) if staged else None
    renderer = renderer or build_renderer(config)
    # A run that makes video keeps every paid answer in its asset cache, text included.
    cache = AssetCache(config.production.cache_directory) if config.production else None

    def agent(
        node_type: type[AgentNode], name: str, *, themed: bool, cached: bool = True
    ) -> AgentNode:
        return node_type(
            name=name,
            config=config.agents[name],
            models=config.models,
            provider=_provider_for(name, config=config, providers=providers),
            guidance=guidance if themed else None,
            cache=cache if cached else None,
        )

    # Fresh research asks the researcher again even for a request it has answered before.
    researcher = agent(FactResearcher, "fact_researcher", themed=False, cached=not fresh_research)
    script_writer = agent(ScriptWriter, "script_writer", themed=True)
    fact_checker = agent(FactChecker, "fact_checker", themed=False)
    visual_director = (
        StagedVisualDirector(
            catalogue=describe(catalogue, presets=theme.spec.staging.moves),
            name="visual_director",
            config=config.agents["visual_director"],
            models=config.models,
            provider=_provider_for("visual_director", config=config, providers=providers),
            guidance=guidance,
            cache=cache,
        )
        if catalogue is not None
        else agent(VisualDirector, "visual_director", themed=True)
    )
    # The Editorial Director's three jobs: the plan, the critic (who holds the work to the
    # theme), and the listener test (a cold viewer who knows nothing, the theme included).
    editorial = agent(EditorialDirector, "editorial_director", themed=True)
    critic = agent(Critic, "editorial_director", themed=True)
    listener = agent(Listener, "editorial_director", themed=False)
    judge = Judge(decision_provider, config.decisions)
    producer = None
    if config.production is not None:
        if media_provider is None:
            raise ValueError("Production is configured, so a media provider is required")
        producer = Producer(
            config=config.production,
            theme=theme,
            media=media_provider,
            judge=judge,
            image_sources=image_sources,
            renderer=renderer,
            catalogue=catalogue,
        )
    limits = config.workflow
    # The locked bed's map, when the run makes video: the plan is sized to its edits.
    scored_music = map_for(theme.music_track) if config.production is not None else None
    produce = producer is not None

    workflow = StateGraph(
        ContentState,
        input_schema=ContentInput,
        output_schema=ContentOutput,
    )
    # System 2 generation (one model call each).
    workflow.add_node("fact_researcher", researcher)
    workflow.add_node("editorial_plan", editorial.create_plan)
    workflow.add_node("script_writer", script_writer)
    workflow.add_node("fact_checker", fact_checker)
    workflow.add_node("visual_director", visual_director)
    # The audience: a first-time listener hears only the narration; the Story Architect
    # decides what happens to a required claim the listener stumbled on.
    workflow.add_node("cold_viewer", listener.listen)
    workflow.add_node("story_decisions", editorial.decide_story)
    # System 1 judgement (one parallel Jev call per story node or connection).
    workflow.add_node("judge_plan", judge.judge, input_schema=JudgementTask)
    workflow.add_node("judge_script", judge.judge, input_schema=JudgementTask)
    workflow.add_node("judge_audience", judge.judge, input_schema=JudgementTask)
    workflow.add_node("judge_visuals", judge.judge, input_schema=JudgementTask)
    # Code: structural gates and verdicts.
    workflow.add_node(
        "plan_verdict", partial(plan_verdict, workflow=limits, theme=theme, music=scored_music)
    )
    learning = config.learning
    faithfulness = (
        OnnxInference(learning.nli_model, learning.directory / "embedder")
        if learning is not None and learning.nli_model
        else None
    )
    workflow.add_node("check_script", partial(check_script, theme=theme, faithfulness=faithfulness))
    workflow.add_node("script_verdict", partial(script_verdict, theme=theme))
    workflow.add_node("audience_verdict", audience_verdict)
    workflow.add_node(
        "check_visuals",
        partial(
            check_visuals,
            theme=theme,
            catalogue=catalogue,
            most_revisions=limits.max_revisions.visuals,
        ),
    )
    workflow.add_node("visual_verdict", visual_verdict)
    # System 2 settles System 1's doubts: the critic reads the whole piece.
    workflow.add_node("critique_script", critic.critique_script)
    workflow.add_node("critique_visuals", critic.critique_visuals)
    # Outcomes and people.
    workflow.add_node(
        "human_review", partial(request_human_review, workflow=limits, voice=theme.spec.voice)
    )
    workflow.add_node(
        "final_package", partial(assemble_final_package, theme=theme, produced=produce)
    )
    workflow.add_node("review_stopped", mark_review_stopped)

    workflow.add_conditional_edges(
        START, route_start, ["fact_researcher", "editorial_plan", "human_review"]
    )
    workflow.add_conditional_edges(
        "fact_researcher",
        partial(route_research, workflow=limits),
        {
            "sufficient": "editorial_plan",
            "revise": "fact_researcher",
            "review": "human_review",
        },
    )

    workflow.add_conditional_edges("editorial_plan", fan_out_plan, ["judge_plan"])
    workflow.add_edge("judge_plan", "plan_verdict")
    workflow.add_conditional_edges(
        "plan_verdict", route_plan_verdict, ["script_writer", "human_review"]
    )

    workflow.add_edge("script_writer", "check_script")
    workflow.add_conditional_edges(
        "check_script",
        partial(route_script_gate, workflow=limits, intended_voice=theme.spec.writing.voice),
        ["judge_script", "script_writer", "human_review"],
    )
    workflow.add_edge("judge_script", "script_verdict")
    workflow.add_conditional_edges(
        "script_verdict",
        partial(route_script_verdict, workflow=limits),
        ["critique_script", "script_writer", "human_review"],
    )
    workflow.add_conditional_edges(
        "critique_script",
        partial(route_script_critique, workflow=limits),
        ["fact_checker", "script_writer", "human_review"],
    )
    # With video to make, the budget first sets how many scenes the pictures can afford.
    storyboard = "price_pictures" if producer is not None else "visual_director"
    if producer is not None:
        workflow.add_node("price_pictures", producer.keyframes.price_pictures)
        workflow.add_edge("price_pictures", "visual_director")
    workflow.add_conditional_edges(
        "fact_checker",
        partial(route_fact_check, workflow=limits),
        ["cold_viewer", "script_writer", "human_review"],
    )
    workflow.add_conditional_edges("cold_viewer", fan_out_audience, ["judge_audience"])
    workflow.add_edge("judge_audience", "audience_verdict")
    workflow.add_conditional_edges(
        "audience_verdict",
        partial(route_audience_verdict, workflow=limits),
        {
            "human_review": "human_review",
            "visual_director": storyboard,
            "script_writer": "script_writer",
            "story_decisions": "story_decisions",
        },
    )
    workflow.add_edge("story_decisions", "script_writer")

    workflow.add_edge("visual_director", "check_visuals")
    workflow.add_conditional_edges(
        "check_visuals",
        partial(route_visual_gate, workflow=limits),
        ["judge_visuals", "visual_director", "human_review"],
    )
    workflow.add_edge("judge_visuals", "visual_verdict")
    workflow.add_conditional_edges(
        "visual_verdict",
        partial(route_visual_verdict, workflow=limits),
        ["critique_visuals", "visual_director", "human_review"],
    )
    workflow.add_conditional_edges(
        "critique_visuals",
        partial(route_visual_critique, workflow=limits, produce=produce),
        ["start_production" if produce else "final_package", "visual_director", "human_review"],
    )

    review_targets = [
        "fact_researcher",
        "editorial_plan",
        "script_writer",
        "fact_checker",
        "visual_director",
        "final_package",
    ]
    if producer is not None:
        _add_production(workflow, producer, limits)
        workflow.add_node(
            "apply_director_notes", partial(apply_director_notes, sort_notes=critic.sort_notes)
        )
        workflow.add_conditional_edges(
            "apply_director_notes",
            route_director_notes,
            ["script_writer", "visual_director", "find_references"],
        )
        review_targets += [
            "price_pictures",
            "start_production",
            "start_keyframes",
            "start_segments",
            "apply_director_notes",
        ]
    workflow.add_conditional_edges(
        "human_review",
        partial(route_human_review, produce=produce),
        {"stop": "review_stopped", **{target: target for target in review_targets}},
    )
    workflow.add_edge("final_package", END)
    workflow.add_edge("review_stopped", END)
    return workflow.compile(checkpointer=checkpointer)


def _add_production(
    workflow: StateGraph[ContentState, None, ContentInput, ContentOutput],
    producer: Producer,
    limits: WorkflowConfig,
) -> None:
    """References ground the scenes in real people, places, and objects; narration sets
    the clock; keyframes anchor each scene; a person reads the story sheet; segments morph
    from anchor to anchor; code assembles the cut."""
    workflow.add_node("start_production", partial(mark_stage, stage="production"))
    workflow.add_node("find_references", producer.references.find_references)
    workflow.add_node(
        "narrate_passage", producer.narration.narrate_passage, input_schema=NarrationTask
    )
    workflow.add_node("time_scenes", producer.narration.time_scenes)
    workflow.add_node("start_keyframes", producer.keyframes.start_keyframes)
    workflow.add_node(
        "produce_keyframe", producer.keyframes.produce_keyframe, input_schema=RenderTask
    )
    workflow.add_node("keyframe_verdict", producer.keyframes.keyframe_verdict)
    workflow.add_node("start_segments", partial(mark_stage, stage="segments"))
    workflow.add_node("produce_segment", producer.segments.produce_segment, input_schema=RenderTask)
    workflow.add_node("segment_verdict", producer.segments.segment_verdict)
    workflow.add_node("assemble", producer.assembly.assemble)

    workflow.add_edge("start_production", "find_references")
    workflow.add_conditional_edges(
        "find_references", producer.narration.narration_tasks, ["narrate_passage", "time_scenes"]
    )
    workflow.add_edge("narrate_passage", "time_scenes")
    workflow.add_conditional_edges(
        "time_scenes",
        partial(route_timing, workflow=limits, keyframe_tasks=producer.keyframes.keyframe_tasks),
        [
            "produce_keyframe",
            "keyframe_verdict",
            "script_writer",
            "visual_director",
            "human_review",
        ],
    )
    workflow.add_conditional_edges(
        "start_keyframes",
        producer.keyframes.keyframe_tasks,
        ["produce_keyframe", "keyframe_verdict"],
    )
    workflow.add_edge("produce_keyframe", "keyframe_verdict")
    workflow.add_conditional_edges(
        "keyframe_verdict",
        partial(route_keyframe_verdict, keyframe_tasks=producer.keyframes.keyframe_tasks),
        ["produce_keyframe", "keyframe_verdict", "human_review"],
    )
    workflow.add_conditional_edges(
        "start_segments", producer.segments.segment_tasks, ["produce_segment", "segment_verdict"]
    )
    workflow.add_edge("produce_segment", "segment_verdict")
    workflow.add_conditional_edges(
        "segment_verdict",
        partial(route_segment_verdict, segment_tasks=producer.segments.segment_tasks),
        ["produce_segment", "segment_verdict", "assemble", "human_review"],
    )
    workflow.add_edge("assemble", "human_review")


def mark_stage(state: ContentState, *, stage: str) -> ContentState:
    return {"current_stage": stage, "events": [{"stage": stage, "message": f"Starting {stage}"}]}
