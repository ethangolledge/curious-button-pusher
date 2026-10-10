import threading
import time
from pathlib import Path

from content.review.reviewer import FileReviewer
from content.schemas.review import ReviewRequest


def test_file_reviewer_waits_for_a_response_file(tmp_path: Path) -> None:
    (tmp_path / "response-1.json").write_text(
        '{"action": "revise", "feedback": "U2: shorter.", "decided_by": "person"}'
    )
    request = ReviewRequest(
        stage="storyboard",
        reason="Read the story sheet.",
        findings=[],
        required_changes=[],
        attachments=["/tmp/story/index.html"],
    )
    lines: list[str] = []

    response = FileReviewer(tmp_path, poll_seconds=0.01, write=lines.append).review(request)

    assert response.feedback == "U2: shorter."
    assert (tmp_path / "request-1.json").is_file()
    assert "Read first: /tmp/story/index.html" in lines


def test_only_the_person_can_answer_a_sign_off(tmp_path: Path) -> None:
    request = ReviewRequest(stage="fact_check", reason="Read the script.")
    (tmp_path / "response-1.json").write_text('{"action": "approve", "decided_by": "assistant"}')

    def person_answers() -> None:
        while not (tmp_path / "response-1.refused.json").is_file():
            time.sleep(0.01)
        (tmp_path / "response-1.json").write_text(
            '{"action": "revise", "feedback": "U3: say what the route is.", "decided_by": "person"}'
        )

    threading.Thread(target=person_answers).start()
    lines: list[str] = []

    response = FileReviewer(tmp_path, poll_seconds=0.01, write=lines.append).review(request)

    assert response.decided_by == "person"
    assert response.feedback == "U3: say what the route is."
    assert "Review 1 is a sign-off: only the person can answer it." in lines
