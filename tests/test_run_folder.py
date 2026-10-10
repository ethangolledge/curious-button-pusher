import csv
import json
import threading
import time
import urllib.request
from pathlib import Path

from content.config import ContentConfig
from content.review.items import sign_off_items
from content.review.run_folder import RunFolder, slug
from content.review.server import RunFolderReviewer
from content.schemas.fact_check import ClaimFinding, FactCheckReport
from content.schemas.review import ReviewItem, ReviewRequest, ReviewResponse
from content.schemas.script import ScriptPackage
from content.workflow.demo import demo_response
from content.workflow.review_requests import confirm_start, start_request


def _folder(tmp_path: Path) -> RunFolder:
    folder = RunFolder(tmp_path / slug("The engineer and the dam"))
    folder.create("The engineer and the dam", "Keep it fair.")
    return folder


def test_a_run_folder_has_plain_names_for_what_the_person_opens(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    mix = tmp_path / "mix.m4a"
    mix.write_bytes(b"audio")
    cache = tmp_path / "cache"
    (cache / "keyframe").mkdir(parents=True)
    pictures = []
    for name in ("b", "a"):
        picture = cache / "keyframe" / f"{name}.png"
        picture.write_bytes(name.encode())
        pictures.append(str(picture))

    folder.publish(ReviewRequest(stage="fact_check", reason="", snapshot="## Script\n\nU1"))
    folder.publish(ReviewRequest(stage="listen", reason="", attachments=[str(mix)]))
    folder.publish(ReviewRequest(stage="storyboard", reason="", attachments=pictures))

    assert folder.root.name == "the-engineer-and-the-dam"
    assert (folder.root / "1-script.md").read_text(encoding="utf-8").startswith("## Script")
    assert (folder.root / "2-narration.m4a").read_bytes() == b"audio"
    # Scenes keep the storyboard's order, not the cache's names.
    assert (folder.scenes / "S1.png").read_bytes() == b"b"
    assert (folder.scenes / "S2.png").read_bytes() == b"a"


def test_every_decision_is_logged_with_who_made_it(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    script = ReviewRequest(stage="fact_check", reason="")
    folder.record(
        script, ReviewResponse(action="revise", feedback="Less dry.", decided_by="person")
    )
    folder.record(ReviewRequest(stage="visuals", reason=""), ReviewResponse(action="approve"))

    log = (folder.root / "decisions.md").read_text(encoding="utf-8")
    assert "Script · revise (person)" in log
    assert "Less dry." in log
    assert "Visuals · approve (unknown)" in log


def test_cost_is_a_table_with_a_row_per_session_split_by_stage(tmp_path: Path) -> None:
    folder = _folder(tmp_path)

    def call(operation: str, cost: float | None) -> dict[str, object]:
        return {"operation": operation, "cost_usd": cost}

    first = [call("research", 0.5), call("judge_unit", 0.01), call("narration", None)]
    second = [call("keyframe", 0.05), call("segment", 0.12), call("perception", 0.002)]
    folder.record_cost({"calls": first}, "fact_check")
    folder.record_cost({"calls": second}, "final_cut")

    with (folder.root / "cost.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["session"] for row in rows] == ["1", "2", "total"]
    assert [row["stopped at"] for row in rows] == ["fact_check", "final_cut", ""]
    assert rows[0]["writing usd"] == "0.5"
    assert rows[0]["checks usd"] == "0.01"
    assert rows[0]["unpriced calls"] == "1"
    assert rows[0]["unpriced narration estimate usd"] == "0.09"
    assert (rows[1]["pictures usd"], rows[1]["morphs usd"]) == ("0.05", "0.12")
    assert rows[2]["total priced usd"] == "0.68"
    assert rows[2]["calls"] == "6"
    # And every call on its own row, with the stage it counts under.
    with (folder.root / "calls.csv").open(encoding="utf-8", newline="") as handle:
        calls = list(csv.DictReader(handle))
    assert [(c["session"], c["made"], c["stage"]) for c in calls][:2] == [
        ("1", "research", "writing"),
        ("1", "judge_unit", "checks"),
    ]
    assert len(calls) == 6 and calls[-1]["cost usd"] == "0.002"


def test_the_review_page_is_one_targeted_decision(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    scene = ReviewItem(item_id="S3", title="S3 · The engineer at the desk", flags=["Too bright."])
    request = ReviewRequest(
        stage="final_cut",
        reason="Watch it.",
        findings=["Jev was unsure about S2's framing."],
        items=[scene],
        unlocks="Approving finishes the package.",
    )

    folder.write_page(request)
    page = folder.page.read_text(encoding="utf-8")
    assert "Whether the video is finished." in page
    assert "Approving finishes the package." in page
    assert "<video id='player'" in page and "4-final.mp4" in page
    assert 'data-id="S3"' in page and "Too bright." in page
    assert "Handled for you (1)" in page
    assert "class='now'>Final cut" in page

    folder.write_page(request, decided=ReviewResponse(action="approve", decided_by="person"))
    assert "Answered: approve (person)" in folder.page.read_text(encoding="utf-8")


def test_a_second_look_marks_what_changed(tmp_path: Path) -> None:
    folder = _folder(tmp_path)

    def script(u2: str) -> ReviewRequest:
        units = [
            ReviewItem(item_id="U1", title="U1", text="Same."),
            ReviewItem(item_id="U2", title="U2", text=u2),
        ]
        return ReviewRequest(stage="fact_check", reason="", items=units)

    folder.write_page(script("Before."))
    assert "Changed" not in folder.page.read_text(encoding="utf-8")
    folder.write_page(script("After."))
    page = folder.page.read_text(encoding="utf-8")
    assert 'class="card changed" data-id="U2"' in page
    assert 'class="card" data-id="U1"' in page


def test_the_page_buttons_answer_the_waiting_review_as_the_person(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    reviewer = RunFolderReviewer(folder, poll_seconds=0.01, open_page=False)
    answers: list[ReviewResponse] = []
    request = ReviewRequest(stage="listen", reason="Listen.")
    thread = threading.Thread(target=lambda: answers.append(reviewer.review(request)))
    thread.start()
    while not list(folder.reviews.glob("request-*.json")):
        time.sleep(0.01)
    assert reviewer._server is not None
    host, port = reviewer._server.server_address[:2]
    body = json.dumps(
        {"action": "revise", "feedback": "Slower in P4.", "edits": {"U2": "My words."}}
    ).encode()
    urllib.request.urlopen(
        urllib.request.Request(
            f"http://{host!s}:{port}/respond",
            data=body,
            headers={"Content-Type": "application/json"},
        )
    )
    thread.join(timeout=5)
    reviewer._server.shutdown()

    assert answers == [
        ReviewResponse(
            action="revise",
            feedback="Slower in P4.",
            edits={"U2": "My words."},
            decided_by="person",
        )
    ]
    assert "Narration · revise (person)" in (folder.root / "decisions.md").read_text()


def test_nothing_is_spent_before_the_start_sign_off(app_config: ContentConfig) -> None:
    class Reviewer:
        def __init__(self) -> None:
            self.requests: list[ReviewRequest] = []

        def review(self, request: ReviewRequest) -> ReviewResponse:
            self.requests.append(request)
            if len(self.requests) == 1:
                return ReviewResponse(action="revise", feedback="Focus on the fund.")
            return ReviewResponse(action="approve", decided_by="person")

    reviewer = Reviewer()
    response, brief = confirm_start("A topic", "Keep it fair.", app_config, reviewer)

    assert response.action == "approve"
    assert brief == "Keep it fair.\n\nFocus on the fund."
    assert [request.stage for request in reviewer.requests] == ["brief", "brief"]
    assert reviewer.requests[0].sign_off
    assert (
        "Research to a fact-checked script" in start_request("A topic", None, app_config).snapshot
    )


def test_script_cards_carry_their_own_fact_check_notes(app_config: ContentConfig) -> None:
    script = ScriptPackage.model_validate(demo_response(json.dumps({"topic": "x"}), ScriptPackage))
    finding = ClaimFinding(
        claim="The fund approved it.",
        claim_id="C6",
        script_unit_ids=["U2"],
        source_ids=[],
        status="exaggerated",
        issue="Stronger than the source.",
        severity="minor",
    )
    report = FactCheckReport(
        claim_findings=[finding],
        non_factual_unit_ids=[],
        routing_result="verified",
    )

    items, unlocks = sign_off_items(
        {"script_package": script, "fact_check_report": report},
        "fact_check",
        app_config.theme.spec.voice,
    )

    flagged = {item.item_id: item.flags for item in items if item.flags}
    assert flagged == {"U2": ["Fact check, exaggerated: Stronger than the source."]}
    assert unlocks.startswith("Approving records the narration:")
