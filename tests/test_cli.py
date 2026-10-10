from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

import content.cli.run as cli
import content.learning.after_run as after_run
from content.config import ContentConfig, LearningConfig
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.schemas.fact_check import FactCheckReport
from content.schemas.package import ReviewHandoff
from content.schemas.review import ReviewRequest, ReviewResponse
from content.schemas.script import ScriptPackage
from content.workflow.demo import demo_answer, demo_response
from content.workflow.run import WorkflowResult, run_workflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class OutOfCredit(Exception):
    """Stands in for OpenRouter's 402 when the key's limit runs out."""


class ReviseOnce:
    def review(self, request: ReviewRequest) -> ReviewResponse:
        return ReviewResponse(action="revise", feedback="Tighten the ending.")


def _writer_runs_out_of_credit() -> FakeModelProvider:
    """The script is reviewed, then the paid rewrite fails for want of credit."""
    scripts = 0

    def respond(input_text: str, output_type: type[BaseModel]) -> Any:
        nonlocal scripts
        if output_type is ScriptPackage:
            scripts += 1
            if scripts > 1:
                raise OutOfCredit("This request requires more credits")
        return demo_response(input_text, output_type)

    return FakeModelProvider(
        {FactCheckReport: [_fact_check("human_review")]}, default_factory=respond
    )


def _fact_check(route: str) -> dict[str, Any]:
    return {
        "claim_findings": [],
        "non_factual_unit_ids": [],
        "routing_result": route,
    }


def _run_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, learning: Any) -> tuple[int, Path]:
    def failing_run(topic: str, **kwargs: Any) -> WorkflowResult:
        result = run_workflow(
            topic,
            config_path=PROJECT_ROOT / "config/config.json",
            providers={"fake": _writer_runs_out_of_credit()},
            decision_provider=FakeDecisionProvider(demo_answer),
            reviewer=ReviseOnce(),
        )
        assert result.error is not None
        config: ContentConfig = replace(
            result.config,
            learning=LearningConfig(
                directory=tmp_path / "learning",
                embedder="unused",
                local_questions=frozenset(),
                teacher="unused",
                min_labels=1,
                min_gold=1,
            ),
        )
        return replace(result, config=config)

    monkeypatch.setattr(cli, "run_workflow", failing_run)
    monkeypatch.setattr(after_run, "learn_from_run", learning)
    # The Start sign-off is answered here, as the person would on the review page.
    monkeypatch.setattr(
        cli,
        "confirm_start",
        lambda topic, brief, config, reviewer, save, choices: (
            ReviewResponse(action="approve"),
            brief,
        ),
    )
    return cli.main(["A topic", "--runs", str(tmp_path)]), tmp_path / "a-topic/.work/resume.json"


def test_a_failed_run_saves_its_review_before_learning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[bool] = []

    def learning_that_dies(*args: Any) -> Any:
        # The terminal closing here must not cost the run its resume file.
        seen.append(review.exists())
        raise RuntimeError("terminal closed")

    review = tmp_path / "a-topic" / ".work" / "resume.json"
    status, review = _run_cli(monkeypatch, tmp_path, learning_that_dies)

    assert status == 2
    assert seen == [True]
    handoff = ReviewHandoff.model_validate_json(review.read_text(encoding="utf-8"))
    assert handoff.script_package is not None
    out = capsys.readouterr().out
    assert "Run failed: OutOfCredit" in out
    assert f"--resume {tmp_path / 'a-topic'} --at fact_check" in out
    assert (tmp_path / "a-topic" / "cost.csv").is_file()
    assert "Learning skipped (RuntimeError: terminal closed)." in out
