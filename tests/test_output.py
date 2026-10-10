import json
from pathlib import Path

from content.providers.fake import FakeModelProvider
from content.review.render import package_to_markdown, render_plan
from content.schemas.fact_check import FactCheckReport
from content.schemas.plan import EditorialBrief
from content.schemas.review import ReviewRequest, ReviewResponse
from content.state import CallRecord
from content.workflow.demo import demo_response
from content.workflow.records import (
    package_to_json,
    run_summary,
    write_outputs,
    write_review_outputs,
    write_run_summary,
    write_trace,
)
from content.workflow.run import run_workflow


def test_json_output_is_valid_and_markdown_has_expected_sections(tmp_path: Path) -> None:
    package = run_workflow("Serialization topic").require_final_package()

    data = json.loads(package_to_json(package))
    markdown = package_to_markdown(package)
    paths = write_outputs(package, tmp_path / "example")

    assert data["topic"] == "Serialization topic"
    assert data["approved_script"]["master_script"]
    assert data["research_pack"]["verified_facts"][0]["claim_id"] == "C1"
    assert "## Creative Plan" in markdown
    assert "## Master Narration" in markdown
    assert "## Narration Generation Prompt" in markdown
    assert "### Connected Script Units" in markdown
    assert "## Storyboard" in markdown
    assert "## Scene Prompts" in markdown
    assert "## Fact Check" in markdown
    assert "## Research Pack" in markdown
    assert "## Scenes" not in markdown
    assert "On-Screen Text" not in markdown
    assert json.loads(paths.json.read_text(encoding="utf-8"))["approval_status"] == "approved"
    assert paths.markdown.read_text(encoding="utf-8") == markdown


def test_stopped_review_writes_every_completed_artifact(
    tmp_path: Path,
    project_root: Path,
) -> None:
    report = demo_response('{"topic":"Review output topic"}', FactCheckReport)
    assert isinstance(report, dict)
    provider = FakeModelProvider(
        {FactCheckReport: [{**report, "routing_result": "human_review"}]},
        default_factory=demo_response,
    )
    result = run_workflow(
        "Review output topic",
        config_path=project_root / "config/config.json",
        providers={"fake": provider},
        reviewer=StopReviewer(),
    )

    paths = write_review_outputs(result.state, tmp_path / "review-output")
    data = json.loads(paths.json.read_text(encoding="utf-8"))
    markdown = paths.markdown.read_text(encoding="utf-8")

    assert paths.json.name == "review-output.review.json"
    assert paths.markdown.name == "review-output.review.md"
    assert data["research_pack"]["verified_facts"][0]["claim_id"] == "C1"
    assert data["editorial_brief"]["central_question"]
    assert data["review_request"]["stage"] == "fact_check"
    assert data["human_decisions"][0]["action"] == "stop"
    assert data["judgements"]
    headings = ("## Creative Plan", "## Master Narration", "## Fact Check", "## Jev Judgements")
    assert all(heading in markdown for heading in headings)


def test_run_summary_totals_calls_and_keeps_unknown_costs_unknown(tmp_path: Path) -> None:
    calls: list[CallRecord] = [
        _call("script", "writer-model", 1000, 400, 0.006),
        _call("judge_unit", "jev", 300, 0, 0.00001),
        _call("judge_unit", "jev", 320, 0, None),
    ]

    summary = run_summary(calls)
    path = write_run_summary(calls, tmp_path / "package")

    assert summary["total"]["calls"] == 3
    assert summary["total"]["cost_usd"] is None
    assert summary["by_operation"]["script"]["cost_usd"] == 0.006
    assert summary["by_model"]["jev"]["input_tokens"] == 620
    assert path.name == "package.run.json"
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["by_operation"]["judge_unit"]["calls"] == 2
    assert "output" not in written["calls"][0]


def test_trace_keeps_every_output_and_reason(tmp_path: Path) -> None:
    result = run_workflow("Traced topic")

    path = write_trace(result.state, tmp_path / "traced")
    trace = json.loads(path.read_text(encoding="utf-8"))

    research = next(call for call in trace["calls"] if call["operation"] == "research")
    assert research["output"]["research_status"] == "sufficient"
    assert trace["judgements"] and trace["events"]


def _call(
    operation: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float | None,
) -> CallRecord:
    return {
        "operation": operation,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "seconds": 0.5,
        "output": {"large": "model output"},
        "reasoning": "a reasoning summary",
    }


class StopReviewer:
    def review(self, request: ReviewRequest) -> ReviewResponse:
        return ReviewResponse(action="stop")


def test_the_plan_reads_as_a_story_a_person_can_check() -> None:
    brief = EditorialBrief.model_validate(demo_response('{"topic": "x"}', EditorialBrief))

    page = "\n".join(render_plan(brief))

    assert "### The Story, Plainly" in page
    assert f"1. {brief.story_chain[0]}" in page
    assert f"Leaves them knowing: {brief.arc[0].audience_knows_after}" in page
    assert f"Next question: {brief.arc[0].next_question}" in page
    assert f"Next: {brief.arc[0].leads_to_next}" in page
    # The claims ledger: what each claim is for, and what it means.
    plan = brief.claims[0]
    assert f"| {plan.claim_id} | spine | {plan.narrative_job} | {plan.meaning} |" in page
    assert f"**{brief.explain[0].term}**: {brief.explain[0].plain}" in page
