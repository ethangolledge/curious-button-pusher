"""`content review` (a run's review page) and `content estimate` (what a video costs, before
anything is spent)."""

import argparse
from pathlib import Path

from content.choices import RunChoices, configure_run
from content.config import (
    load_config,
)
from content.review.run_folder import RunFolder
from content.review.server import serve
from content.workflow.estimate import estimate_table


def _estimate(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content estimate",
        description="What a video would cost, by scene count, before anything is spent.",
    )
    parser.add_argument("--seconds", type=int, required=True, help="Planned length")
    parser.add_argument("--format", help="A format from the theme (default: the theme's)")
    parser.add_argument("--scenes", type=int, help="Also show this scene count")
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    args = parser.parse_args(arguments)
    config = configure_run(
        load_config(args.config), RunChoices(format=args.format, seconds=args.seconds)
    )
    if config.production is None:
        parser.error("This configuration makes no video")
    print(estimate_table(config, args.seconds, args.scenes))
    return 0


def _review(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content review",
        description="Serve a run's waiting review page until it is answered.",
    )
    parser.add_argument("run", type=Path, help="The run folder (runs/<topic>)")
    parser.add_argument("--no-open", action="store_true", help="Print the address only")
    args = parser.parse_args(arguments)
    return serve(RunFolder(args.run), open_page=not args.no_open)


COMMANDS = {"review": _review, "estimate": _estimate}
