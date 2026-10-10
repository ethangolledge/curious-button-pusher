"""The review page a person answers a sign-off on: one card per piece (a script unit, a
passage, a scene), what the checks noticed, and the buttons. Its script and style are
`page/review.js` and `page/review.css`."""

import html
import re
from pathlib import Path

from content.schemas.review import SIGN_OFF_STAGES, ReviewItem, ReviewRequest, ReviewResponse


def review_title(request: ReviewRequest) -> str:
    return SIGN_OFF_STAGES.get(request.stage) or request.stage.replace("_", " ").capitalize()


# How each kind of narration comment reads on the page.
NOTE_KINDS = {
    "wording": "The words",
    "pronunciation": "Pronunciation (write: word = how to say it)",
    "pause": "A pause or emphasis",
    "voice": "The voice itself (record it again)",
}


# For each sign-off: what is being decided, and what to look for.
GUIDES: dict[str, tuple[str, str]] = {
    "brief": (
        "Whether to start this story.",
        "Check the topic and brief say what you want. A comment is added to the brief.",
    ),
    "plan": (
        "Whether this is the story to write.",
        "Read the story chain and the beats: is it the story you want, in the right order, at "
        "the right length? Comment on a beat (P3: …) or the whole. The words come later; this "
        "is the shape.",
    ),
    "fact_check": (
        "Whether this is the script to record.",
        "Read it through once. Comment on anything wrong, unfair, dull, or not the story you "
        "want: say what and why, and the wording is handled for you. Fact-check notes sit on "
        "the lines they concern.",
    ),
    "listen": (
        "Whether this is the narration the pictures will follow.",
        "Listen once through. Comment on any passage that drags, rushes, stumbles or "
        "mispronounces, and say what kind of problem it is: the words, a pronunciation, a "
        "pause or emphasis, or the voice itself. Only that passage is recorded again. Tap a "
        "passage to hear it again.",
    ),
    "storyboard": (
        "Whether these pictures go on to be morphed together.",
        "Look at each picture with its line. Comment on any that shows the wrong person or "
        "place, feels off-tone, confuses, or doesn't show its line.",
    ),
    "final_cut": (
        "Whether the video is finished.",
        "Watch it through. Comment on any glitch, wrong subtitle, or moment that loses you; "
        "tap a scene to jump to it.",
    ),
}


def _steps(request: ReviewRequest) -> str:
    stages = list(SIGN_OFF_STAGES)
    current = stages.index(request.stage) if request.stage in stages else -1
    steps = "".join(
        f"<li class='{'done' if index < current else 'now' if index == current else ''}'>"
        f"{html.escape(name)}</li>"
        for index, name in enumerate(SIGN_OFF_STAGES.values())
    )
    return f"<ol class='steps'>{steps}</ol>"


def _player(request: ReviewRequest) -> str:
    if request.stage == "listen":
        return "<audio id='player' controls preload='auto' src='2-narration.m4a'></audio>"
    if request.stage == "storyboard":
        return (
            "<video id='player' controls preload='metadata' src='3-scenes/animatic.mp4'></video>"
            "<p class='hint'>The animatic: the pictures timed to the narration, before any "
            "morph. <a href='3-scenes/story-sheet/index.html'>Full story sheet</a></p>"
        )
    if request.stage == "final_cut":
        return "<video id='player' controls preload='metadata' src='4-final.mp4'></video>"
    return ""


def _layout(request: ReviewRequest, body: str) -> str:
    """Pictures and the cut: the video in a sticky column beside the scene cards. Script
    and narration: one reading column, the narration's player pinned above it."""
    player = _player(request)
    if request.stage in {"storyboard", "final_cut"}:
        return (
            f"<div class='split'><div class='media'>{player}</div>"
            f"<section class='cards{' compact' if request.stage == 'final_cut' else ''}'>"
            f"{body}</section></div>"
        )
    pinned = f"<div class='pinned'>{player}</div>" if player else ""
    return f"{pinned}<section class='cards reading'>{body}</section>"


def _card(item: ReviewItem, changed: bool) -> str:
    picture = (
        f"<img src='3-scenes/{html.escape(item.item_id)}{Path(item.media).suffix}' alt=''>"
        if item.media
        else ""
    )
    play = (
        f"<button class='play' data-start='{item.start:.2f}'>▶ Play from here</button>"
        if item.start is not None
        else ""
    )
    flags = "".join(f"<li>{html.escape(flag)}</li>" for flag in item.flags)
    classes = "card changed" if changed else "card"
    edit = "<button class='edit'>Edit</button>" if item.editable else ""
    kinds = (
        "<select class='kind'>"
        + "".join(
            f"<option value='{kind}'>{html.escape(NOTE_KINDS.get(kind, kind))}</option>"
            for kind in item.note_kinds
        )
        + "</select>"
        if item.note_kinds
        else ""
    )
    own_words = (
        f"<textarea class='own' rows='3' hidden data-original='{html.escape(item.text)}'>"
        f"{html.escape(item.text)}</textarea>"
        if item.editable
        else ""
    )
    return f"""<article class="{classes}" data-id="{html.escape(item.item_id)}">
<header><span class="id">{html.escape(item.item_id)}</span>
<span class="title">{html.escape(item.title.split(" · ", 1)[-1])}</span>
{"<span class='badge'>Changed</span>" if changed else ""}</header>
{picture}
{f"<p class='words'>{html.escape(item.text)}</p>" if item.text else ""}
{f"<p class='provenance'>{html.escape(item.provenance)}</p>" if item.provenance else ""}
{f"<ul class='flags'>{flags}</ul>" if flags else ""}
<div class="card-actions">{play}{edit}<button class="comment">Comment</button></div>
{own_words}
<div class="note-box" hidden>{kinds}
<textarea class="note" rows="3" placeholder="What should change, and why?"></textarea></div>
</article>"""


def _handled(findings: list[str]) -> str:
    if not findings:
        return ""
    lines = "".join(f"<li>{html.escape(line)}</li>" for line in findings)
    return (
        f"<details><summary>Handled for you ({len(findings)})</summary><ul>{lines}</ul></details>"
    )


def _overall(decided: ReviewResponse | None) -> str:
    if decided is not None:
        return ""
    return (
        "<section class='overall'><label for='overall'>Anything else?</label>"
        "<textarea id='overall' rows='3' placeholder='A note on the whole thing "
        "(optional)'></textarea></section>"
    )


def _bar(request: ReviewRequest) -> str:
    blocked = "" if request.approvable else " data-blocked='1'"
    # On a script, comments on lines change only those lines unless asked otherwise.
    whole = (
        "<label class='quiet' id='whole-label' hidden><input type='checkbox' id='whole'> "
        "Rewrite the whole script around my notes</label>"
        if any(item.editable for item in request.items)
        else ""
    )
    return (
        f"<div class='bar'{blocked}><span id='count'>No comments</span>{whole}"
        "<button id='stop' class='quiet'>Save and stop</button>"
        "<button id='submit' class='primary'>Approve</button></div>"
    )


def _markdown(text: str) -> str:
    """Just enough Markdown for snapshots: headings, bullets, bold, paragraphs."""
    out: list[str] = []
    in_list = False
    for raw in text.splitlines():
        line = html.escape(raw.strip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        is_item = line.startswith("- ")
        if in_list and not is_item:
            out.append("</ul>")
            in_list = False
        if heading := re.match(r"(#{1,4}) (.*)", line):
            level = min(len(heading.group(1)) + 1, 5)
            out.append(f"<h{level}>{heading.group(2)}</h{level}>")
        elif is_item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line[2:]}</li>")
        elif line:
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


# The page's script and style, inlined so the page is one self-contained file.
ASSETS = Path(__file__).with_name("assets")
_SCRIPT = (ASSETS / "review.js").read_text(encoding="utf-8")


_STYLE = (ASSETS / "review.css").read_text(encoding="utf-8")


def review_page(
    root: Path,
    request: ReviewRequest,
    decided: ReviewResponse | None,
    changed: set[str] | None = None,
    number: int = 0,
) -> str:
    title = review_title(request)
    topic = (root / "brief.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
    deciding, look_for = GUIDES.get(
        request.stage, ("A check the assistant is handling.", "You may answer it too.")
    )
    cards = "".join(_card(item, item.item_id in (changed or set())) for item in request.items)
    if decided is None:
        status, bar = "", _bar(request)
    else:
        status = (
            f"<p class='answered'>Answered: {html.escape(decided.action)} "
            f"({html.escape(decided.decided_by)}). You can close this window; the next sign-off "
            "opens on its own.</p>"
        )
        bar = ""
    body = cards or f"<section class='card text'>{_markdown(request.snapshot)}</section>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · {html.escape(topic)}</title>
<style>
{_STYLE}</style></head>
<body data-review="{number}"><main>
<p class="topic">{html.escape(topic)}</p>
{_steps(request)}
<h1>{html.escape(title)}</h1>
{status}
<section class="brief-box">
<p><span class="label">You're deciding</span>{html.escape(deciding)}</p>
<p><span class="label">Why it matters</span>{html.escape(request.unlocks or request.reason)}</p>
<p><span class="label">Look for</span>{html.escape(look_for)}</p>
</section>
{_layout(request, body)}
{_overall(decided)}
{_handled(request.findings)}
<p class="links"><a href="decisions.md">Decisions so far</a> · <a href="cost.csv">Cost</a> ·
<a href="brief.md">Brief</a></p>
</main>
{bar}
<div id="sent" hidden><p>Sent. The run carries on; this window closes now.</p></div>
<div id="unsent" hidden><p>Not sent: nothing is listening for this review. Your comments are
kept. Start the page with <code>content review {html.escape(str(root))}</code>, or paste
this into chat:</p><textarea readonly rows="6"></textarea>
<button class="primary" id="copy">Copy</button></div>
<script>
{_SCRIPT}</script>
</body></html>
"""
