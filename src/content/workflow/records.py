"""The files a run leaves: the final package, the review handoff a resume starts from, the
trace and the cost summary."""

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.review.render import package_to_markdown, review_handoff_to_markdown
from content.schemas.package import FinalContentPackage, ReviewHandoff
from content.schemas.review import ReviewRequest
from content.state import CallRecord, ContentOutput


@dataclass(frozen=True, slots=True)
class OutputPaths:
    json: Path
    markdown: Path


def package_to_json(package: FinalContentPackage) -> str:
    return package.model_dump_json(indent=2)


def build_review_handoff(
    state: ContentOutput, waiting: ReviewRequest | None = None
) -> ReviewHandoff:
    """The saved run at its last answered review, or at the review `waiting` for an answer."""
    request = waiting or state.get("human_review_request")
    response = None if waiting else state.get("human_review_response")
    if request is None or (waiting is None and response is None):
        raise ValueError("Review handoff requires a completed human-review decision")
    return ReviewHandoff(
        topic=state["topic"],
        duration_seconds=state["duration_seconds"],
        aspect_ratio=state["aspect_ratio"],
        current_stage=state.get("current_stage", request.stage),
        review_request=request,
        review_response=response,
        research_pack=state.get("research_pack"),
        editorial_brief=state.get("editorial_brief"),
        script_package=state.get("script_package"),
        fact_check_report=state.get("fact_check_report"),
        visual_package=state.get("visual_package"),
        references=state.get("references", {}),
        judgements=state.get("judgements", []),
        human_decisions=state.get("human_decisions", []),
        line_edits=state.get("line_edits", []),
        warnings=[*state.get("warnings", []), *state.get("script_warnings", [])],
        status="human_review",
    )


def review_handoff_to_json(handoff: ReviewHandoff) -> str:
    return handoff.model_dump_json(indent=2)


def _known_sum(values: list[int | None] | list[float | None]) -> float | None:
    """A total is only reported when every part of it is known."""
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _totals(calls: list[CallRecord]) -> dict[str, Any]:
    return {
        "calls": len(calls),
        "input_tokens": _known_sum([call["input_tokens"] for call in calls]),
        "output_tokens": _known_sum([call["output_tokens"] for call in calls]),
        "cost_usd": _known_sum([call["cost_usd"] for call in calls]),
        "seconds": round(sum(call["seconds"] for call in calls), 3),
    }


def run_summary(calls: list[CallRecord]) -> dict[str, Any]:
    """Totals per operation and model. Unknown token or cost values stay unknown."""
    by_operation: dict[str, list[CallRecord]] = defaultdict(list)
    by_model: dict[str, list[CallRecord]] = defaultdict(list)
    for call in calls:
        by_operation[call["operation"]].append(call)
        by_model[call["model"]].append(call)
    return {
        "total": _totals(calls),
        "by_operation": {name: _totals(group) for name, group in by_operation.items()},
        "by_model": {name: _totals(group) for name, group in by_model.items()},
        "calls": [
            {key: value for key, value in call.items() if key not in {"output", "reasoning"}}
            for call in calls
        ],
    }


def _base(output_base: Path) -> Path:
    return output_base.with_suffix("") if output_base.suffix in {".json", ".md"} else output_base


def write_outputs(package: FinalContentPackage, output_base: Path) -> OutputPaths:
    base = _base(output_base)
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(package_to_json(package) + "\n", encoding="utf-8")
    markdown_path.write_text(package_to_markdown(package), encoding="utf-8")
    return OutputPaths(json=json_path, markdown=markdown_path)


def write_review_outputs(state: ContentOutput, output_base: Path) -> OutputPaths:
    base = _base(output_base)
    json_path = base.parent / f"{base.name}.review.json"
    markdown_path = base.parent / f"{base.name}.review.md"
    handoff = build_review_handoff(state)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(review_handoff_to_json(handoff) + "\n", encoding="utf-8")
    markdown_path.write_text(review_handoff_to_markdown(handoff), encoding="utf-8")
    return OutputPaths(json=json_path, markdown=markdown_path)


def write_trace(state: ContentOutput, output_base: Path) -> Path:
    """Everything the run decided and why, in order: each model's output and reasoning
    summary, every Jev answer, and every event. Written locally; costs no tokens."""
    base = _base(output_base)
    path = base.parent / f"{base.name}.trace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    trace = {
        "topic": state.get("topic"),
        "status": state.get("status"),
        "events": state.get("events", []),
        "calls": state.get("call_log", []),
        "judgements": [j.model_dump(mode="json") for j in state.get("judgements", [])],
        "revisions": state.get("revision_history", []),
        # Every line changed after the first draft, by whom and why.
        "line_edits": [edit.model_dump(mode="json") for edit in state.get("line_edits", [])],
        "human_decisions": [
            decision.model_dump(mode="json") for decision in state.get("human_decisions", [])
        ],
        "revision_counts": {
            "plan": state.get("plan_revision_count", 0),
            "script": state.get("script_revision_count", 0),
            "visuals": state.get("visual_revision_count", 0),
        },
        # What a resumed run started from, so its judgements can be rebuilt for learning.
        "research_and_plan": {
            key: artifact.model_dump(mode="json")
            for key, artifact in (
                ("research_pack", state.get("research_pack")),
                ("editorial_brief", state.get("editorial_brief")),
            )
            if artifact is not None
        },
        "keyframes": [
            asset.model_dump(
                mode="json", include={"scene_id", "attempt", "signature", "issues", "colour"}
            )
            for asset in state.get("keyframes", {}).values()
        ],
    }
    path.write_text(json.dumps(trace, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def write_run_summary(calls: list[CallRecord], output_base: Path) -> Path:
    base = _base(output_base)
    path = base.parent / f"{base.name}.run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run_summary(calls), indent=2) + "\n", encoding="utf-8")
    return path
