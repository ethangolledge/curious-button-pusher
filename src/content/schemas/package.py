"""What a run hands over: the final package, and the saved state a review or resume starts from."""

from typing import Literal

from content.schemas.base import ImmutableModel
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Judgement
from content.schemas.media import ProductionResult
from content.schemas.plan import EditorialBrief
from content.schemas.references import ReferenceSet
from content.schemas.research import ResearchPack
from content.schemas.review import HumanDecision, ReviewRequest, ReviewResponse
from content.schemas.script import LineEdit, ScriptPackage
from content.schemas.visuals import VisualPackage


class ScenePrompts(ImmutableModel):
    """The exact prompts code built for a scene, for manual use in any generator."""

    scene_id: str
    keyframe_prompt: str
    segment_prompt: str


class FinalContentPackage(ImmutableModel):
    topic: str
    duration_seconds: int
    aspect_ratio: str
    research_pack: ResearchPack
    editorial_brief: EditorialBrief
    approved_script: ScriptPackage
    narration_prompt: str
    # The fact check as the auditor returned it. A human approval never rewrites it;
    # any override appears in `human_decisions`.
    fact_check_report: FactCheckReport
    visual_plan: VisualPackage
    scene_prompts: list[ScenePrompts]
    # The finished video and its parts; None when the run stops at the prompt package.
    production: ProductionResult | None
    human_decisions: list[HumanDecision]
    warnings: list[str]
    approval_status: Literal["approved"]


class ReviewHandoff(ImmutableModel):
    topic: str
    duration_seconds: int
    aspect_ratio: str
    current_stage: str
    review_request: ReviewRequest
    # None while the review is still waiting for its answer.
    review_response: ReviewResponse | None = None
    research_pack: ResearchPack | None
    editorial_brief: EditorialBrief | None
    script_package: ScriptPackage | None
    fact_check_report: FactCheckReport | None
    visual_package: VisualPackage | None
    # The reference photographs chosen for the storyboard. Keyframes are drawn from them,
    # so a resume that searched again could choose others and pay to redraw every scene
    # they appear in.
    references: dict[str, ReferenceSet] = {}
    judgements: list[Judgement]
    human_decisions: list[HumanDecision]
    line_edits: list[LineEdit] = []
    warnings: list[str]
    status: Literal["human_review"]
