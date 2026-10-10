"""Starting, resuming and driving a run: its initial state, reopening a saved review, and
stepping the graph from sign-off to sign-off."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from content.choices import RunChoices, configure_run
from content.config import ContentConfig, load_config
from content.errors import InputError
from content.production.media import MediaProvider
from content.production.music_map import map_for
from content.production.score import choose
from content.providers.base import DecisionProvider, ModelProvider
from content.review.reviewer import HumanReviewer, ReviewDetached
from content.schemas.media import Arrangement
from content.schemas.package import FinalContentPackage, ReviewHandoff
from content.schemas.research import SourceMaterial
from content.schemas.review import ReviewRequest
from content.state import ContentInput, ContentOutput
from content.story.field import unit_feelings
from content.story.pace import estimate, passages, word_budget
from content.story.weights import evidence, stance
from content.workflow.checkpoint import create_checkpointer
from content.workflow.gates import size_story
from content.workflow.graph import build_graph
from content.workflow.providers import (
    build_decision_provider,
    build_image_sources,
    build_media_provider,
    build_providers,
    fit_cap_to_openrouter_credit,
)


class WorkflowIncompleteError(RuntimeError):
    def __init__(self, *, status: str, stage: str) -> None:
        super().__init__(f"Workflow stopped with status '{status}' at stage '{stage}'")
        self.status = status
        self.stage = stage


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    config: ContentConfig
    state: ContentOutput
    pending_review: ReviewRequest | None = None
    # Set when the run failed part-way; `state` is then the last saved step.
    error: str | None = None
    # Where this session's calls start in the state's call log: a run carried on from its
    # saved steps also holds the calls of the sessions before.
    first_call: int = 0

    def require_final_package(self) -> FinalContentPackage:
        package = self.state.get("final_package")
        if package is None:
            raise WorkflowIncompleteError(
                status=(
                    "human_review"
                    if self.pending_review is not None
                    else self.state.get("status", "human_review")
                ),
                stage=(
                    self.pending_review.stage
                    if self.pending_review is not None
                    else self.state.get("current_stage", "unknown")
                ),
            )
        return package


def create_initial_state(
    topic: str,
    *,
    source_material: list[SourceMaterial] | None,
    user_instructions: str | None,
    config: ContentConfig,
    duration_seconds: int | None = None,
    scenes: int | None = None,
) -> ContentInput:
    if not topic.strip():
        raise InputError("Topic must not be empty")
    limits = config.theme.spec.format
    # Unchosen, the configured default, within what the format allows.
    duration = duration_seconds or int(
        min(max(config.content.default_duration_seconds, limits.min_seconds), limits.max_seconds)
    )
    if not limits.min_seconds <= duration <= limits.max_seconds:
        raise InputError(
            f"The theme allows videos of {limits.min_seconds:g}–{limits.max_seconds:g} seconds, "
            f"not {duration}"
        )
    voice = config.theme.spec.voice
    arrangement = music_arrangement(config, duration)
    # With a mapped bed, the narration aims to end mid-way through the music's outro.
    target = (
        arrangement.seconds - sum(config.theme.spec.music.outro_seconds) / 2
        if arrangement is not None
        else float(duration)
    )
    return {
        "topic": topic.strip(),
        "user_instructions": user_instructions,
        "source_material": list(source_material or []),
        "duration_seconds": duration,
        "word_budget": word_budget(target, voice),
        "target_seconds": round(target, 1),
        "arrangement": arrangement,
        "aspect_ratio": config.theme.spec.format.aspect_ratio,
        "scenes_wanted": scenes,
    }


def music_arrangement(config: ContentConfig, duration: int) -> Arrangement | None:
    """The producer's edit of the locked bed nearest the requested length, when the bed
    has been mapped and the run makes video."""
    music = map_for(config.theme.music_track) if config.production is not None else None
    if music is None:
        return None
    spec = config.theme.spec
    return choose(music, duration, spec.music.outro_seconds, spec.format.max_seconds)


RESUMABLE_STAGES = ("research", "plan", "script", "fact_check", "visuals")
_STAGE_NEEDS = {
    "research": "research_pack",
    "plan": "editorial_brief",
    "script": "script_package",
    "fact_check": "fact_check_report",
    "visuals": "visual_package",
}


def resume_state(
    handoff: ReviewHandoff,
    config: ContentConfig,
    stage: str | None,
    user_instructions: str | None = None,
    scenes: int | None = None,
) -> ContentInput:
    """Reopen a saved review, with every artifact the stopped run had paid for, and the
    author's brief when it is given again (a review file does not keep it).

    `stage` reopens an earlier review instead, for example "script" to have a revised
    script audited again rather than approving the saved fact check."""
    stage = stage or handoff.review_request.stage
    if stage not in RESUMABLE_STAGES or getattr(handoff, _STAGE_NEEDS[stage]) is None:
        raise InputError(f"This saved run cannot reopen the {stage} review")
    state = create_initial_state(
        handoff.topic,
        source_material=None,
        user_instructions=user_instructions,
        config=config,
        duration_seconds=handoff.duration_seconds,
        scenes=scenes,
    )
    # Keep the artifacts up to the reopened stage; later ones will be made again.
    kept = RESUMABLE_STAGES[: RESUMABLE_STAGES.index(stage) + 1]
    state["research_pack"] = handoff.research_pack
    state["editorial_brief"] = handoff.editorial_brief if "plan" in kept else None
    state["script_package"] = handoff.script_package if "script" in kept else None
    state["fact_check_report"] = handoff.fact_check_report if "fact_check" in kept else None
    # Every boundary the saved fact check drew stays in force for the next rewrite.
    state["fact_constraints"] = [
        finding
        for finding in (
            state["fact_check_report"].claim_findings if state["fact_check_report"] else []
        )
        if finding.status != "passed"
    ]
    state["visual_package"] = handoff.visual_package if "visuals" in kept else None
    # Chosen reference photographs belong to the storyboard: reused, never searched again.
    state["references"] = handoff.references if "visuals" in kept else {}
    _rederive(state, handoff, config)
    # The story's judgements travel with it: the next save keeps them, so the scenes'
    # emotional fields (from the script's reactions) and the learning data survive every
    # resume. Picture and morph judgements are made again with the pictures.
    state["judgements"] = [
        judgement for judgement in handoff.judgements if judgement.stage in {"plan", "script"}
    ]
    state["line_edits"] = list(handoff.line_edits) if "script" in kept else []
    state["current_stage"] = stage
    state["revision_notes"] = (
        list(handoff.review_request.required_changes)
        if stage == handoff.review_request.stage
        else []
    )
    state["warnings"] = list(handoff.warnings)
    return state


def _rederive(state: ContentInput, handoff: ReviewHandoff, config: ContentConfig) -> None:
    """What the stopped run's code worked out from the kept artifacts, worked out again:
    the plan's size (and so the target and music edit), each line's seconds, and how each
    line lands. Without them a resumed storyboard would be sized blind."""
    brief, script = state.get("editorial_brief"), state.get("script_package")
    if brief is not None and all(phase.words > 0 for phase in brief.arc):
        music = map_for(config.theme.music_track) if config.production is not None else None
        size, arrangement = size_story(brief, config.theme, music)
        state["story_size"] = size
        state["target_seconds"] = size.target_seconds
        state["word_budget"] = word_budget(
            size.target_seconds, config.theme.spec.voice, passage_count=len(brief.arc)
        )
        state["arrangement"] = arrangement
    research = state.get("research_pack")
    if research is not None:
        weights = config.theme.spec.writing.weights
        state["claim_stances"] = {
            claim_id: stance(value, weights)
            for claim_id, value in evidence(research, weights).items()
        }
    if script is not None:
        spoken = passages(script.script_units, config.theme.speaker(script.voice_direction))
        state["unit_seconds"] = {
            unit_id: round(seconds, 1)
            for unit_id, seconds in estimate(spoken, config.theme.spec.voice).unit_seconds.items()
        }
        scripted = [j for j in handoff.judgements if j.stage == "script"]
        latest = max((j.revision for j in scripted), default=0)
        state["unit_feelings"] = unit_feelings([j for j in scripted if j.revision == latest])


# Called with the state at every review before it is asked, so it can be saved first.
OnReview = Callable[[ContentOutput, ReviewRequest], None]
# One run per graph, so one thread; the step file holds no other.
_RUNTIME: RunnableConfig = {"configurable": {"thread_id": "run"}}


def run_workflow(
    topic: str,
    *,
    source_material: list[SourceMaterial] | None = None,
    user_instructions: str | None = None,
    duration_seconds: int | None = None,
    resume: ReviewHandoff | None = None,
    resume_stage: str | None = None,
    config_path: Path | None = None,
    providers: Mapping[str, ModelProvider] | None = None,
    decision_provider: DecisionProvider | None = None,
    media_provider: MediaProvider | None = None,
    reviewer: HumanReviewer | None = None,
    steps: Path | None = None,
    on_review: OnReview | None = None,
    choices: RunChoices | None = None,
) -> WorkflowResult:
    """Run from a topic, or reopen a saved review (`resume`). With `steps`, every step is
    also written to that file (started afresh), so `continue_workflow` can carry on after
    the process ends. `choices` shape this video: format, length, scenes, cap."""
    choices = choices or RunChoices()
    config = configure_run(load_config(config_path), choices)
    logging.getLogger("content").setLevel(config.application.logging_level)
    initial_state = (
        resume_state(resume, config, resume_stage, user_instructions, choices.scenes)
        if resume is not None
        else create_initial_state(
            topic,
            source_material=source_material,
            user_instructions=user_instructions,
            duration_seconds=duration_seconds or choices.seconds,
            config=config,
            scenes=choices.scenes,
        )
    )
    if steps is not None:
        steps.unlink(missing_ok=True)
    config, graph = _graph(config, providers, decision_provider, media_provider, steps)
    return _drive(config, graph, initial_state, reviewer, on_review)


def continue_workflow(
    steps: Path,
    *,
    config_path: Path | None = None,
    providers: Mapping[str, ModelProvider] | None = None,
    decision_provider: DecisionProvider | None = None,
    media_provider: MediaProvider | None = None,
    reviewer: HumanReviewer | None = None,
    on_review: OnReview | None = None,
    choices: RunChoices | None = None,
) -> WorkflowResult:
    """Carry on a run from its step file: answer the review it stopped at, or redo the
    step it failed in. Nothing it already finished is made again. `choices` must be the
    ones the run started with: the graph is rebuilt from them."""
    config = configure_run(load_config(config_path), choices or RunChoices())
    logging.getLogger("content").setLevel(config.application.logging_level)
    if not steps.is_file():
        raise InputError(f"No saved steps to carry on from: {steps}")
    config, graph = _graph(config, providers, decision_provider, media_provider, steps)
    if not graph.get_state(_RUNTIME).next:
        raise InputError("This run has finished: nothing to carry on")
    return _drive(config, graph, None, reviewer, on_review)


def _graph(
    config: ContentConfig,
    providers: Mapping[str, ModelProvider] | None,
    decision_provider: DecisionProvider | None,
    media_provider: MediaProvider | None,
    steps: Path | None,
) -> tuple[ContentConfig, CompiledStateGraph[Any, Any, Any, Any]]:
    if providers is None:
        config = fit_cap_to_openrouter_credit(config)
    graph = build_graph(
        config=config,
        providers=providers if providers is not None else build_providers(config),
        decision_provider=(
            decision_provider if decision_provider is not None else build_decision_provider(config)
        ),
        media_provider=(
            media_provider if media_provider is not None else build_media_provider(config)
        ),
        image_sources=build_image_sources(config),
        checkpointer=create_checkpointer(steps),
    )
    return config, graph


def _drive(
    config: ContentConfig,
    graph: CompiledStateGraph[Any, Any, Any, Any],
    first: ContentInput | None,
    reviewer: HumanReviewer | None,
    on_review: OnReview | None,
) -> WorkflowResult:
    """Run the graph from `first`, or from its saved step when `first` is None, answering
    each review until the run finishes, stops, or leaves a review for later."""

    def values() -> ContentOutput:
        return cast(ContentOutput, graph.get_state(_RUNTIME).values)

    first_call = 0 if first is not None else len(values().get("call_log", []))
    try:
        if first is not None:
            pending_review = _pending_review(cast(dict[str, Any], graph.invoke(first, _RUNTIME)))
        else:
            pending_review = _saved_review(graph)
            if pending_review is None:
                # The process ended inside a step: do that step again.
                pending_review = _pending_review(cast(dict[str, Any], graph.invoke(None, _RUNTIME)))
        while pending_review is not None and reviewer is not None:
            if on_review is not None:
                on_review(values(), pending_review)
            response = reviewer.review(pending_review)
            pending_review = _pending_review(
                cast(
                    dict[str, Any],
                    graph.invoke(Command[Any](resume=response.model_dump()), _RUNTIME),
                )
            )
    except ReviewDetached as detached:
        return WorkflowResult(
            config=config,
            state=values(),
            pending_review=detached.request,
            first_call=first_call,
        )
    except Exception as exc:
        # A provider failure part-way must not lose what the run already paid for: return
        # the last saved step, so its reviews and trace can be written and resumed.
        return WorkflowResult(
            config=config,
            state=values(),
            error=f"{type(exc).__name__}: {exc}",
            first_call=first_call,
        )
    return WorkflowResult(
        config=config, state=values(), pending_review=pending_review, first_call=first_call
    )


def _saved_review(graph: CompiledStateGraph[Any, Any, Any, Any]) -> ReviewRequest | None:
    for task in graph.get_state(_RUNTIME).tasks:
        for waiting in task.interrupts:
            return ReviewRequest.model_validate(waiting.value)
    return None


def _pending_review(result: Mapping[str, Any]) -> ReviewRequest | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return ReviewRequest.model_validate(interrupts[0].value)
