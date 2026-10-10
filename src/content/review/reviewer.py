"""How a paused run gets its answer: the reviewer interface, and the file reviewer that writes
each review as `request-N.json` and waits for `response-N.json`. Only the person can answer
a sign-off."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from content.schemas.review import ReviewRequest, ReviewResponse, ReviewStage


class HumanReviewer(Protocol):
    """Replaceable boundary between the workflow and a human interface."""

    def review(self, request: ReviewRequest) -> ReviewResponse:
        """Collect one human decision for a paused workflow."""
        ...


class ReviewDetached(Exception):
    """The run stops at a review rather than wait for it; its state is saved, and the
    next `--resume` takes the answer from the review's response file."""

    def __init__(self, request: ReviewRequest, number: int) -> None:
        super().__init__(f"Review {number} ({request.stage}) is waiting for an answer")
        self.request = request
        self.number = number


class FileReviewer:
    """Reviews through files, so another person or an assistant can answer them.

    Each review is written as `request-N.json`; the run waits until `response-N.json`
    appears beside it, containing a `ReviewResponse`. A response that does not say
    `"decided_by": "person"` is taken as the assistant's, so it never trains anything, and
    it cannot answer a sign-off: it is set aside as `response-N.refused.json` and the run
    keeps waiting for the person.

    A review still open when its run stopped (unanswered, or answered while nothing was
    running) is the same review when the run carries on: it keeps its number, and an
    answer already given is used. With `detach`, the run stops at an unanswered review
    instead of waiting (`ReviewDetached`)."""

    def __init__(
        self,
        directory: Path,
        *,
        poll_seconds: float = 3.0,
        write: Callable[[str], None] = print,
        detach: bool = False,
    ) -> None:
        self.directory = directory
        self.poll_seconds = poll_seconds
        self.detach = detach
        self._write = write

    def review(self, request: ReviewRequest) -> ReviewResponse:
        return self.wait(request, self.post(request))

    def post(self, request: ReviewRequest) -> int:
        """Write the request, or find it still open from before; returns its number."""
        self.directory.mkdir(parents=True, exist_ok=True)
        numbers = sorted(review_number(path) for path in self.directory.glob("request-*.json"))
        latest = numbers[-1] if numbers else 0
        if latest and self._open(latest, request.stage):
            return latest
        number = latest + 1
        (self.directory / f"request-{number}.json").write_text(
            json.dumps({**request.model_dump(mode="json"), "sign_off": request.sign_off}, indent=2),
            encoding="utf-8",
        )
        self._write(f"Review waiting: {self.directory / f'request-{number}.json'}")
        if request.attachments:
            self._write(f"Read first: {request.attachments[0]}")
        return number

    def wait(self, request: ReviewRequest, number: int) -> ReviewResponse:
        answer = self.directory / f"response-{number}.json"
        detached = self.directory / f"detached-{number}"
        while True:
            while not answer.is_file():
                if self.detach:
                    detached.touch()
                    raise ReviewDetached(request, number)
                time.sleep(self.poll_seconds)
            try:
                raw = json.loads(answer.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # Caught mid-write (the page and the assistant write it in one go): read again.
                time.sleep(self.poll_seconds)
                continue
            response = ReviewResponse.model_validate({"decided_by": "assistant", **raw})
            if not request.sign_off or response.decided_by == "person":
                break
            answer.rename(answer.with_suffix(".refused.json"))
            self._write(f"Review {number} is a sign-off: only the person can answer it.")
        detached.unlink(missing_ok=True)
        self._write(f"Review {number} answered: {response.action} ({response.decided_by})")
        return response

    def _open(self, number: int, stage: ReviewStage) -> bool:
        saved = json.loads((self.directory / f"request-{number}.json").read_text(encoding="utf-8"))
        answered = (self.directory / f"response-{number}.json").is_file()
        waiting = not answered or (self.directory / f"detached-{number}").is_file()
        return bool(saved["stage"] == stage and waiting)


def review_number(path: Path) -> int:
    """N, from request-N.json or response-N.json."""
    return int(path.stem.split("-")[1])
