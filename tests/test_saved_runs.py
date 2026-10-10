"""A run survives its process: every step is saved, a review can be left for later, and
the next session carries on from the saved step without making anything again."""

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.review.reviewer import FileReviewer, ReviewDetached
from content.review.run_folder import RunFolder, slug
from content.review.server import _server
from content.schemas.fact_check import FactCheckReport
from content.schemas.review import ReviewRequest, ReviewResponse
from content.state import ContentOutput
from content.workflow.demo import demo_answer, demo_response
from content.workflow.records import build_review_handoff
from content.workflow.run import continue_workflow, run_workflow

CONFIG = Path(__file__).resolve().parents[1] / "config/config.json"
# The fact check asks for a review, so the run stops at the Script sign-off.
FACT_CHECK = {"claim_findings": [], "non_factual_unit_ids": [], "routing_result": "human_review"}


class Detach:
    def review(self, request: ReviewRequest) -> ReviewResponse:
        raise ReviewDetached(request, 1)


class Answer:
    def __init__(self, response: ReviewResponse) -> None:
        self.response = response
        self.stages: list[str] = []

    def review(self, request: ReviewRequest) -> ReviewResponse:
        self.stages.append(request.stage)
        return self.response


def _no_calls(input_text: str, output_type: type[BaseModel]) -> Any:
    raise AssertionError("a carried-on run must not make again what it already made")


def test_a_run_left_at_a_review_carries_on_without_paying_again(tmp_path: Path) -> None:
    steps = tmp_path / "steps.jsonl"
    saved: list[ContentOutput] = []

    def save(state: ContentOutput, waiting: ReviewRequest) -> None:
        saved.append(state)
        handoff = build_review_handoff(state, waiting)
        assert handoff.review_response is None
        assert handoff.script_package is not None

    first = run_workflow(
        "A topic",
        config_path=CONFIG,
        providers={
            "fake": FakeModelProvider(
                {FactCheckReport: [FACT_CHECK]}, default_factory=demo_response
            )
        },
        decision_provider=FakeDecisionProvider(demo_answer),
        reviewer=Detach(),
        steps=steps,
        on_review=save,
    )
    assert first.error is None
    assert first.pending_review is not None and first.pending_review.stage == "fact_check"
    assert len(saved) == 1
    made = len(first.state.get("call_log", []))

    answer = Answer(ReviewResponse(action="stop", decided_by="person"))
    second = continue_workflow(
        steps,
        config_path=CONFIG,
        providers={"fake": FakeModelProvider({}, default_factory=_no_calls)},
        decision_provider=FakeDecisionProvider(demo_answer),
        reviewer=answer,
    )

    assert second.error is None
    assert answer.stages == ["fact_check"]
    assert second.state.get("status") == "human_review"
    # This session's spend starts after the first session's calls.
    assert second.first_call == made


def test_an_open_review_keeps_its_number_and_takes_the_answer_given_meanwhile(
    tmp_path: Path,
) -> None:
    request = ReviewRequest(stage="fact_check", reason="Read the script.")
    with pytest.raises(ReviewDetached):
        FileReviewer(tmp_path, write=lambda line: None, detach=True).review(request)
    assert (tmp_path / "detached-1").is_file()
    # Answered while nothing was running, as the review page or chat would.
    (tmp_path / "response-1.json").write_text(
        '{"action": "revise", "feedback": "U2: plainer.", "decided_by": "person"}'
    )

    response = FileReviewer(tmp_path, write=lambda line: None, detach=True).review(request)

    assert response.feedback == "U2: plainer."
    assert sorted(path.name for path in tmp_path.iterdir()) == ["request-1.json", "response-1.json"]
    # Answered and taken: the next review is a new one.
    with pytest.raises(ReviewDetached) as later:
        FileReviewer(tmp_path, write=lambda line: None, detach=True).review(request)
    assert later.value.number == 2


def test_comments_are_saved_in_the_run_folder_as_they_are_typed(tmp_path: Path) -> None:
    folder = RunFolder(tmp_path / slug("The engineer and the dam"))
    folder.create("The engineer and the dam", None)
    folder.reviews.mkdir(parents=True)
    (folder.reviews / "request-3.json").write_text('{"stage": "fact_check"}')
    server = _server(folder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    draft = {"notes": {"U2": "Too long"}, "overall": ""}
    urllib.request.urlopen(
        urllib.request.Request(
            f"http://{host!s}:{port}/draft",
            data=json.dumps({"review": 3, "draft": draft}).encode(),
            headers={"Content-Type": "application/json"},
        )
    )
    server.shutdown()

    assert json.loads((folder.reviews / "draft-3.json").read_text()) == draft
    # A draft is not an answer: the review still waits.
    assert not (folder.reviews / "response-3.json").exists()
