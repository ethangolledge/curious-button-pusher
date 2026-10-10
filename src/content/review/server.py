"""Showing a review and waiting for its answer: a small server on this machine keeps the page
answerable, in the run's process or apart from it (`--detach`), and the desktop is told when
a sign-off is waiting."""

import json
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from content.review.page import review_title
from content.review.reviewer import FileReviewer, ReviewDetached, review_number
from content.review.run_folder import RunFolder
from content.schemas.review import ReviewRequest, ReviewResponse

FIRST_PORT = 8765


def _serve_apart(folder: RunFolder) -> None:
    """Start `content review` for this folder in its own session, so the page stays
    answerable after this run has stopped."""
    subprocess.Popen(
        [sys.executable, "-m", "content", "review", str(folder.root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _show(address: str, message: str) -> None:
    """Open the review page in its own app window (so it can close itself once answered)
    and post a desktop notification; fall back to the default browser."""
    if notify := shutil.which("notify-send"):
        subprocess.Popen([notify, "-a", "content", message, address])
    for browser in ("chromium", "google-chrome-stable", "google-chrome", "brave", "microsoft-edge"):
        if executable := shutil.which(browser):
            subprocess.Popen(
                [executable, f"--app={address}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    webbrowser.open(address)


def _waiting_request(folder: RunFolder) -> Path | None:
    for request in sorted(folder.reviews.glob("request-*.json"), key=review_number, reverse=True):
        if not request.with_name(request.name.replace("request-", "response-")).exists():
            return request
    return None


def _server(folder: RunFolder) -> ThreadingHTTPServer:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(folder.root), **kwargs)

        def do_POST(self) -> None:  # the standard library names it
            if self.path not in {"/respond", "/draft"}:
                self.send_error(404)
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            waiting = _waiting_request(folder)
            if self.path == "/draft":
                # Comments as they are typed, so a closed window or a stopped run loses none.
                number = int(body.get("review") or 0)
                if number < 1:
                    self.send_error(400, "No review number")
                    return
                (folder.reviews / f"draft-{number}.json").write_text(
                    json.dumps(body.get("draft", {}), indent=2), encoding="utf-8"
                )
                self.send_response(204)
                self.end_headers()
                return
            if waiting is None:
                self.send_error(409, "No review is waiting")
                return
            response = ReviewResponse(
                action=body["action"],
                feedback=(body.get("feedback") or "").strip() or None,
                edits=body.get("edits") or {},
                scope=body.get("scope") or None,
                decided_by="person",
            )
            waiting.with_name(waiting.name.replace("request-", "response-")).write_text(
                response.model_dump_json(), encoding="utf-8"
            )
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    for port in range(FIRST_PORT, FIRST_PORT + 20):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError:
            continue
    raise OSError(f"No free port from {FIRST_PORT} for the review page")


class RunFolderReviewer:
    """Reviews through the run folder: publish what is being decided on, show it on the
    review page, and wait for an answer from the page's buttons or a response file.

    With `detach`, the run stops at an unanswered review instead (its state is saved),
    and a separate review server keeps the page answerable until the person answers."""

    def __init__(
        self,
        folder: RunFolder,
        *,
        poll_seconds: float = 3.0,
        open_page: bool = True,
        detach: bool = False,
    ) -> None:
        self.folder = folder
        self.open_page = open_page
        self._files = FileReviewer(folder.reviews, poll_seconds=poll_seconds, detach=detach)
        self._server: ThreadingHTTPServer | None = None

    def review(self, request: ReviewRequest) -> ReviewResponse:
        # The page's server is up before the review is posted, so it can answer at once.
        address = "" if self._files.detach else self._serve()
        number = self._files.post(request)
        self.folder.publish(request)
        self.folder.write_page(request, number=number)
        who = "your sign-off" if request.sign_off else "the assistant"
        if self._files.detach:
            try:
                response = self._files.wait(request, number)
            except ReviewDetached:
                print(f"{review_title(request)}: saved, waiting for {who}.")
                print(f"Answer on the page (content review {self.folder.root}) or in chat,")
                print(f"then carry on: content --resume {self.folder.root} --detach")
                if request.sign_off and self.open_page:
                    _serve_apart(self.folder)
                raise
        else:
            print(f"{review_title(request)}: waiting for {who} at {address}")
            if request.sign_off and self.open_page:
                _show(address, f"Your video needs you: {review_title(request)}")
            response = self._files.wait(request, number)
        self.folder.record(request, response)
        self.folder.write_page(request, number=number, decided=response)
        return response

    def _serve(self) -> str:
        if self._server is None:
            self._server = _server(self.folder)
            threading.Thread(target=self._server.serve_forever, daemon=True).start()
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}/review.html"


def serve(folder: RunFolder, *, open_page: bool = True, poll_seconds: float = 1.0) -> int:
    """Serve the folder's waiting review until it is answered: the review page for a run
    that stopped at it. Returns 1 when nothing is waiting."""
    if _waiting_request(folder) is None:
        print(f"No review is waiting in {folder.root}.")
        return 1
    server = _server(folder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    address = f"http://{host!s}:{port}/review.html"
    print(f"Review page: {address}")
    if open_page:
        _show(address, "Your video needs you")
    while _waiting_request(folder) is not None:
        time.sleep(poll_seconds)
    server.shutdown()
    print(f"Answered. Carry on with: content --resume {folder.root}")
    return 0
