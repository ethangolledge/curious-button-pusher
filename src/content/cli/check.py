"""`content check`: is this machine ready to make videos? Each requirement in turn, and what to
do in plain words when one is missing. The assistant runs it at every stage of setting someone
up. It spends nothing: checking the OpenRouter key reads its balance, which is free."""

import argparse
import importlib.util
import os
import shutil
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from content.config import ContentConfig, load_config
from content.errors import ConfigurationError
from content.workflow.providers import MIN_RUN_USD

Status = Literal["ready", "missing", "optional"]
MARKS = {"ready": "✓", "missing": "✗", "optional": "○"}
GOOGLE_SIGN_IN = Path.home() / ".config/gcloud/application_default_credentials.json"
# How long reaching the bucket may take before the network is suspected (docs/google-cloud.md).
BUCKET_SECONDS = 30.0


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""


def checks(config_path: Path | None) -> list[Check]:
    """Everything a run needs, in the order to set it up; the optional extras last."""
    found = [
        _python(),
        _program("ffmpeg"),
        _program("ffprobe"),
        _extra("live", "openai", "talking to the models through OpenRouter", required=True),
        _key(),
        *_channel(config_path),
        _extra("learn", "fastembed", "local taste models that learn from your labels"),
        _extra("music", "beat_this", "cutting stories to a locked music bed's beats"),
        _extra("vision", "transformers", "aiming the camera at each picture's focal point"),
    ]
    return found


def _python() -> Check:
    # The package installs only on 3.11 or newer, so running at all means it is new enough.
    return Check("Python", "ready", ".".join(map(str, sys.version_info[:3])))


def _program(name: str) -> Check:
    if shutil.which(name):
        return Check(name, "ready", "installed")
    return Check(
        name,
        "missing",
        "not found",
        "Install ffmpeg: on macOS `brew install ffmpeg`; on Ubuntu, Debian or Windows (WSL) "
        "`sudo apt install -y ffmpeg`. Then open a new terminal.",
    )


def _extra(name: str, module: str, purpose: str, *, required: bool = False) -> Check:
    if importlib.util.find_spec(module) is not None:
        return Check(f"`{name}` extra", "ready", purpose)
    return Check(
        f"`{name}` extra",
        "missing" if required else "optional",
        f"not installed: {purpose}",
        f"`.venv/bin/pip install -e '.[{name}]'`",
    )


def _key() -> Check:
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return Check(
            "OpenRouter key",
            "missing",
            "no key in .env",
            "Create a key at openrouter.ai (Settings → Keys, with a spending limit), add some "
            "credit, then `cp .env.example .env` and paste the key after OPENROUTER_API_KEY=.",
        )
    if importlib.util.find_spec("httpx") is None:
        return Check("OpenRouter key", "ready", "in .env (install the `live` extra to check it)")
    from content.providers.openrouter import key_credit_remaining

    try:
        remaining = key_credit_remaining()
    except Exception as exc:
        return Check(
            "OpenRouter key",
            "missing",
            f"rejected ({type(exc).__name__})",
            "Check the key in .env is the whole key, and that it is enabled at openrouter.ai.",
        )
    if remaining is None:
        return Check(
            "OpenRouter key",
            "ready",
            "works; no spending limit (a limit at openrouter.ai caps what any run can spend)",
        )
    if remaining < MIN_RUN_USD:
        return Check(
            "OpenRouter key",
            "missing",
            f"works, but only ${remaining:.2f} left",
            "Add credit, or raise the key's limit, at openrouter.ai.",
        )
    return Check("OpenRouter key", "ready", f"works; ${remaining:.2f} left")


def _channel(config_path: Path | None) -> list[Check]:
    if config_path is None:
        channels = sorted(Path("themes").glob("*/config.json"))
        if not channels:
            return [
                Check(
                    "Channel",
                    "missing",
                    "none yet",
                    "Make one: `content new-channel <name>` (the assistant's `new-channel` "
                    "skill walks through it).",
                )
            ]
        names = ", ".join(path.parent.name for path in channels)
        return [
            Check(
                "Channel",
                "ready",
                f"{names} (check one in full with --config themes/<name>/config.json)",
            )
        ]
    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        return [
            Check("Channel", "missing", str(exc), "Fix the file named above, then check again.")
        ]
    return [
        Check("Channel", "ready", f"{config.theme.spec.name}: settings, prompts and files load"),
        *_bucket(config),
    ]


def _bucket(config: ContentConfig) -> list[Check]:
    if config.storage is None:
        return [
            Check(
                "Bucket",
                "optional",
                "none: the channel and its videos stay on this machine",
                "To keep them safe with every version, see docs/google-cloud.md.",
            )
        ]
    bucket = config.storage.bucket
    if importlib.util.find_spec("google.cloud.storage") is None:
        return [Check("Bucket", "missing", bucket, "`.venv/bin/pip install -e '.[cloud]'`")]
    if not (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or GOOGLE_SIGN_IN.is_file()):
        return [
            Check(
                "Bucket",
                "missing",
                f"{bucket}: not signed in to Google",
                "In a terminal of your own (not inside Claude Code): "
                "`gcloud auth application-default login` (docs/google-cloud.md).",
            )
        ]
    reached = _within(BUCKET_SECONDS, lambda: _list_bucket(bucket))
    if reached is None:
        return [
            Check(
                "Bucket",
                "missing",
                f"{bucket}: no answer in {BUCKET_SECONDS:.0f} s",
                "Your network may block Google's metadata lookup: see the quirk at the end of "
                "docs/google-cloud.md.",
            )
        ]
    if isinstance(reached, Exception):
        return [
            Check(
                "Bucket",
                "missing",
                f"{bucket}: {type(reached).__name__}: {reached}",
                "Check the bucket's name in the channel's config.json, and that your Google "
                "account owns it (docs/google-cloud.md).",
            )
        ]
    return [Check("Bucket", "ready", f"{bucket}: reachable, {reached} kept")]


def _list_bucket(bucket: str) -> int:
    from content.storage import GcsStore, kept

    return len(kept(GcsStore(bucket)))


def _within(seconds: float, work: Callable[[], int]) -> int | Exception | None:
    """`work`'s result, its error, or None if it took longer than `seconds`."""
    outcome: list[int | Exception] = []

    def run() -> None:
        try:
            outcome.append(work())
        except Exception as exc:
            outcome.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    return outcome[0] if outcome else None


def _check(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content check",
        description="Check this machine is ready to make videos, and say what to do if not.",
    )
    parser.add_argument("--config", type=Path, help="A channel's config.json, to check it in full")
    args = parser.parse_args(arguments)
    found = checks(args.config)
    for check in found:
        print(f"{MARKS[check.status]} {check.name}: {check.detail}")
        if check.fix and check.status != "ready":
            print(f"    {check.fix}")
    missing = [check.name for check in found if check.status == "missing"]
    print("Ready to make videos." if not missing else f"To do: {', '.join(missing)}.")
    return 1 if missing else 0


COMMANDS = {"check": _check}
