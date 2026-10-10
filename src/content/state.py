"""The run's state as it moves through the graph, how parallel branches merge into it, and the
records it keeps: every model call, every revision, every event."""

from typing import Annotated, Any, Literal, Required, TypedDict, TypeVar

from content.providers.base import Usage
from content.schemas.audience import AudienceReport
from content.schemas.fact_check import ClaimFinding, FactCheckReport, UnitAudit
from content.schemas.judgement import Judgement
from content.schemas.media import (
    Arrangement,
    Budget,
    NarrationClip,
    ProductionResult,
    RenderedAsset,
    Timeline,
)
from content.schemas.package import FinalContentPackage
from content.schemas.plan import EditorialBrief, StorySize
from content.schemas.references import ReferenceSet
from content.schemas.research import ResearchPack, SourceMaterial
from content.schemas.review import HumanDecision, ReviewRequest, ReviewResponse
from content.schemas.script import LineEdit, ScriptPackage
from content.schemas.story import Feeling
from content.schemas.visuals import VisualPackage

WorkflowStatus = Literal["running", "human_review", "approved"]


class RevisionRecord(TypedDict):
    stage: Literal["research", "plan", "script", "visuals"]
    revision_number: int
    reason: str


class WorkflowEvent(TypedDict):
    stage: str
    message: str


class CallRecord(TypedDict):
    """One model call: a generative System 2 operation or a System 1 judgement batch."""

    operation: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    seconds: float
    # Kept for the run trace only: what the model returned, and its reasoning summary.
    output: dict[str, Any] | None
    reasoning: str | None


T = TypeVar("T")


def append_items(left: list[T], right: list[T]) -> list[T]:
    return [*left, *right]


def merge_by_key(left: dict[str, T], right: dict[str, T]) -> dict[str, T]:
    """Per-scene or per-unit assets written by parallel branches; newer entries win."""
    return {**left, **right}


def add_new(left: list[T], right: list[T]) -> list[T]:
    """Append what is not already there: each item is recorded once, however often it
    is reported."""
    return [*left, *(item for item in right if item not in left)]


def merge_warnings(current: list[str], new: list[str]) -> list[str]:
    return list(dict.fromkeys([*current, *new]))


class ContentInput(TypedDict, total=False):
    topic: Required[str]
    user_instructions: str | None
    source_material: list[SourceMaterial]
    duration_seconds: int
    # Roughly how many narration words fill the planned length at the voice's pace.
    word_budget: int
    # The planned narration length in seconds: a target, not a limit. The spoken
    # narration may miss it by the voice's `length_tolerance`; the music then fits it.
    target_seconds: float
    # The music as a producer would edit it for this length; None without a mapped bed.
    arrangement: Arrangement | None
    aspect_ratio: str
    # How many scenes the person chose for this video; None leaves it to the story.
    scenes_wanted: int | None
    # Resuming a saved run: its artifacts, and the review stage to reopen.
    research_pack: ResearchPack | None
    editorial_brief: EditorialBrief | None
    script_package: ScriptPackage | None
    fact_check_report: FactCheckReport | None
    # The evidence boundaries the saved fact check drew, still in force after a resume.
    fact_constraints: list[ClaimFinding]
    visual_package: VisualPackage | None
    references: dict[str, ReferenceSet]
    # The plan's and script's judgements a resumed run starts from (they append).
    judgements: list[Judgement]
    # Who changed which line, so a person's edits stay in force after a resume.
    line_edits: list[LineEdit]
    # What code derived from those artifacts: the story's size, each line's seconds, and
    # how each line lands.
    story_size: StorySize | None
    claim_stances: dict[str, str]
    unit_seconds: dict[str, float]
    unit_feelings: dict[str, Feeling]
    current_stage: str
    revision_notes: list[str]
    warnings: list[str]


class ContentState(TypedDict, total=False):
    topic: str
    user_instructions: str | None
    source_material: list[SourceMaterial]
    duration_seconds: int
    word_budget: int
    target_seconds: float
    arrangement: Arrangement | None
    aspect_ratio: str

    research_pack: ResearchPack | None
    editorial_brief: EditorialBrief | None
    # How long the plan's story is, sized by code from its beats; shown at the plan review.
    story_size: StorySize | None
    # How firmly each claim may be stated, from its evidence: assert, attribute, or ask.
    claim_stances: dict[str, str]
    script_package: ScriptPackage | None
    fact_check_report: FactCheckReport | None
    # Every evidence boundary a line has crossed in this run, kept in force for every
    # later rewrite so a revision cannot cross it again.
    fact_constraints: Annotated[list[ClaimFinding], add_new]
    # What a first-time listener took from the narration alone, after the fact check.
    audience_report: AudienceReport | None
    # Every line changed after the first draft: by whom, from what, and why.
    line_edits: Annotated[list[LineEdit], append_items]
    # The revision at which the small edit model last tried each line: a line it tried in
    # the last revision that comes back again goes to the writer's own model.
    small_edit_tries: dict[str, int]
    visual_package: VisualPackage | None
    final_package: FinalContentPackage | None
    human_review_request: ReviewRequest | None
    human_review_response: ReviewResponse | None
    human_review_feedback: str | None

    # Production. Assets are keyed by unit or scene ID; each records what it was made
    # from, so stale entries are recognised and replaced rather than deleted.
    narration: Annotated[dict[str, NarrationClip], merge_by_key]
    timeline: Timeline | None
    keyframes: Annotated[dict[str, RenderedAsset], merge_by_key]
    contact_sheet: str | None
    # The keyframes as a timed preview with narration, music, and subtitles.
    animatic: str | None
    # Each narration unit's measured reaction: the source of every scene's emotional field.
    unit_feelings: dict[str, Feeling]
    # The narration scored with its music, for the listen review, and the narration track
    # a person last approved there.
    listen_mix: str | None
    listened_narration: str | None
    # What the run has spent and is projected to spend, against its cap.
    budget: Budget | None
    # How many scenes the pictures can afford (a keyframe and a morph each), set before
    # the storyboard is drawn, and how many the person chose (never more than affordable).
    scene_allowance: int | None
    scenes_wanted: int | None
    # The story sheet page a person reads before the video is paid for.
    story_sheet: str | None
    # A person's narration notes, by passage ID: pause or emphasis added to its direction,
    # and how many fresh takes they asked for after hearing its voice.
    passage_directions: dict[str, str]
    retakes_asked: dict[str, int]
    # A person's targeted notes still waiting for their owner (scene and reference notes
    # wait while the writer revises the narration).
    director_notes: list[str]
    # Reference images found for the storyboard's requests, by reference ID.
    references: dict[str, ReferenceSet]
    segments: Annotated[dict[str, RenderedAsset], merge_by_key]
    production: ProductionResult | None

    # Targeted corrections for the next revision of the current stage's artifact.
    # Written by code gates and verdicts; consumed by the writer or visual director.
    revision_notes: list[str]
    # Clean fact-check audits keyed by a unit's words and citations, reused while unchanged.
    unit_audits: Annotated[dict[str, UnitAudit], merge_by_key]
    # Predicted seconds of narration per unit, from the voice's fitted pace.
    unit_seconds: dict[str, float]
    # True when the current revision_notes come from structural blockers.
    structural_blockers: bool

    current_stage: str
    routing_decision: str
    status: WorkflowStatus
    # Advice about the current script version only (its length, its context notes): replaced
    # when the writer produces a new version, so a review never shows an old version's.
    script_warnings: list[str]

    research_revision_count: int
    plan_revision_count: int
    script_revision_count: int
    visual_revision_count: int

    judgements: Annotated[list[Judgement], append_items]
    human_decisions: Annotated[list[HumanDecision], append_items]
    call_log: Annotated[list[CallRecord], append_items]
    events: Annotated[list[WorkflowEvent], append_items]
    warnings: list[str]
    revision_history: Annotated[list[RevisionRecord], append_items]


class ContentOutput(TypedDict, total=False):
    topic: str
    duration_seconds: int
    aspect_ratio: str
    research_pack: ResearchPack | None
    editorial_brief: EditorialBrief | None
    script_package: ScriptPackage | None
    fact_check_report: FactCheckReport | None
    visual_package: VisualPackage | None
    final_package: FinalContentPackage | None
    human_review_request: ReviewRequest | None
    human_review_response: ReviewResponse | None
    timeline: Timeline | None
    budget: Budget | None
    keyframes: dict[str, RenderedAsset]
    segments: dict[str, RenderedAsset]
    references: dict[str, ReferenceSet]
    production: ProductionResult | None
    current_stage: str
    routing_decision: str
    status: WorkflowStatus
    research_revision_count: int
    plan_revision_count: int
    script_revision_count: int
    visual_revision_count: int
    judgements: list[Judgement]
    human_decisions: list[HumanDecision]
    line_edits: list[LineEdit]
    call_log: list[CallRecord]
    events: list[WorkflowEvent]
    warnings: list[str]
    script_warnings: list[str]
    revision_history: list[RevisionRecord]


def call_record(
    operation: str,
    usage: Usage,
    seconds: float,
    *,
    output: dict[str, Any] | None = None,
) -> CallRecord:
    return {
        "operation": operation,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": usage.cost_usd,
        "seconds": round(seconds, 3),
        "output": output,
        "reasoning": usage.reasoning,
    }
