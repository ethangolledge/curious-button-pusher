"""Making a video: `content "<topic>"`, or `--resume` a run folder, from the Start sign-off to
the finished cut."""

import argparse
import json
import shutil
from pathlib import Path

from pydantic import ValidationError

from content.choices import RunChoices, configure_run
from content.cli.spend import ledger_for, read_openrouter, record_spend
from content.cli.storage import keep, keep_theme
from content.config import (
    ContentConfig,
    LearningConfig,
    load_config,
)
from content.errors import ConfigurationError, InputError
from content.review.reviewer import ReviewDetached
from content.review.run_folder import RunFolder, slug
from content.review.server import RunFolderReviewer
from content.schemas.package import ReviewHandoff
from content.schemas.research import ResearchPack, SourceMaterial
from content.schemas.review import ReviewRequest
from content.state import ContentOutput
from content.storage import (
    archive_run,
    open_store,
)
from content.workflow.records import (
    build_review_handoff,
    review_handoff_to_json,
    run_summary,
    write_outputs,
    write_review_outputs,
    write_run_summary,
    write_trace,
)
from content.workflow.review_requests import confirm_start
from content.workflow.run import continue_workflow, run_workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content",
        description="Make a short video, from a topic to the finished cut, in runs/<topic>/.",
    )
    parser.add_argument(
        "topic",
        nargs="?",
        help="The topic, or your whole idea written out in plain words, in quotes",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="A run folder (runs/<topic>): carry on from its last review",
    )
    parser.add_argument(
        "--at",
        choices=["research", "plan", "script", "fact_check", "visuals"],
        help="With --resume, reopen this earlier review instead",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Stop at each review instead of waiting; answer it, then --resume",
    )
    parser.add_argument("--sources", type=Path, help="JSON file containing supplied sources")
    parser.add_argument(
        "--seconds",
        type=int,
        help="Planned length in seconds; the story may run up to 30%% over",
    )
    parser.add_argument(
        "--format",
        help="A format from the theme, such as short or long (default: the theme's)",
    )
    parser.add_argument(
        "--scenes", type=int, help="How many scenes (pictures); default: as the story needs"
    )
    parser.add_argument(
        "--max-usd", type=float, help="The most this video may spend (default: the config's)"
    )
    parser.add_argument(
        "--brief",
        type=Path,
        help="Text or Markdown file with your story points and direction",
    )
    parser.add_argument(
        "--research",
        type=Path,
        help="Start from research already paid for: a run's building-blocks/research.json",
    )
    parser.add_argument(
        "--fresh-research",
        action="store_true",
        help="Research again even if the same research request is in the cache",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument(
        "--runs",
        type=Path,
        help="Folder that holds run folders (default from the configuration: runs/)",
    )
    return parser


def _load_sources(path: Path | None) -> list[SourceMaterial]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_sources = data.get("sources", []) if isinstance(data, dict) else data
    if not isinstance(raw_sources, list):
        raise ValueError("Source input must be a list or an object containing a 'sources' list")
    return [SourceMaterial.model_validate(source) for source in raw_sources]


def _saved_brief(folder: RunFolder) -> str | None:
    """The brief a run started with: brief.md after its title line."""
    path = folder.root / "brief.md"
    if not path.is_file():
        return None
    body = "\n".join(path.read_text(encoding="utf-8").splitlines()[2:]).strip()
    return None if body.startswith("No brief given") else body or None


def _saved_topic(folder: RunFolder) -> str:
    """The topic a run started with: brief.md's title line."""
    return (folder.root / "brief.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ")


def _write_results(
    state: ContentOutput, error: str | None, session: Path, folder: RunFolder
) -> int:
    """The package, or the review to resume from; 0 only for a finished package."""
    package = state.get("final_package")
    if package is None:
        reviewed = (
            state.get("human_review_request") is not None
            and state.get("human_review_response") is not None
        )
        if reviewed and (state.get("status") == "human_review" or error):
            paths = write_review_outputs(state, session)
            shutil.copyfile(paths.json, folder.resume_file)
            folder.write_building_blocks(
                ReviewHandoff.model_validate_json(paths.json.read_text(encoding="utf-8"))
            )
            last = state.get("human_review_request")
            if error and folder.steps.is_file():
                print(f"Carry on from the failed step: --resume {folder.root}")
            elif error and last is not None:
                print(f"Resume from the last review: --resume {folder.root} --at {last.stage}")
            else:
                print(f"Resume with: --resume {folder.root}")
            return 2
        print("Nothing to resume from yet.")
        return 2
    write_outputs(package, session)
    folder.write_building_blocks(package)
    if package.production is not None:
        shutil.copyfile(package.production.video_path, folder.root / "4-final.mp4")
        print(f"Video: {folder.root / '4-final.mp4'}")
    return 0


def _learn_after_run(config: ContentConfig, learning: LearningConfig, trace: Path) -> None:
    """Learning never fails a run: the trace is saved, so `harvest` can learn from it later."""
    from content.learning.after_run import learn_from_run

    try:
        print(learn_from_run(config, learning, trace).summary())
    except Exception as exc:
        print(f"Learning skipped ({type(exc).__name__}: {exc}).")
        print("Run `harvest` and then `train` to learn from this run later.")


def main(arguments: list[str]) -> int:
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.topic is None and args.resume is None:
        parser.error("Give a topic, or --resume a run folder")
    try:
        config = load_config(args.config)
        sources = _load_sources(args.sources)
        asked = RunChoices(
            format=args.format, seconds=args.seconds, scenes=args.scenes, max_usd=args.max_usd
        )
        brief = args.brief.read_text(encoding="utf-8").strip() if args.brief else None
        research = (
            ResearchPack.model_validate_json(args.research.read_text(encoding="utf-8"))
            if args.research
            else None
        )
        if args.resume:
            folder = RunFolder(args.resume)
            brief = brief or _saved_brief(folder)
            resume = (
                ReviewHandoff.model_validate_json(folder.resume_file.read_text(encoding="utf-8"))
                if folder.resume_file.is_file()
                else None
            )
            # Saved steps carry on exactly where the run stopped, unless --at reopens an
            # earlier review from the saved state.
            carry_on = folder.steps.is_file() and args.at is None
            topic = resume.topic if resume else _saved_topic(folder)
            if carry_on and asked.model_dump(exclude_none=True, exclude={"max_usd"}):
                parser.error(
                    "A run carries on in the format, length and scenes it started with; "
                    "reopen an earlier review with --at to change them"
                )
            choices = folder.load_choices().merged(asked)
        else:
            folder = RunFolder(
                (args.runs or config.application.output_directory) / slug(args.topic)
            )
            if folder.resume_file.exists() or folder.steps.exists():
                parser.error(f"{folder.root} already has a run: --resume {folder.root}")
            folder.create(args.topic, brief)
            resume, carry_on, topic = None, False, args.topic
            choices = asked
        folder.save_choices(choices)
        config = configure_run(config, choices)
    except (
        ConfigurationError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        parser.error(str(exc))
    reviewer = RunFolderReviewer(folder, detach=args.detach)

    def save(state: ContentOutput, waiting: ReviewRequest) -> None:
        # Saved before every review is asked, so a review is never the place a run is lost.
        handoff = build_review_handoff(state, waiting)
        folder.resume_file.write_text(review_handoff_to_json(handoff) + "\n", encoding="utf-8")
        folder.write_building_blocks(handoff)
        if config.storage is not None:
            storage = config.storage
            # The run so far is kept at every stop (in its bucket or folder): building blocks,
            # its saved state, and what has been signed off (never the working cache).
            keep(
                lambda: archive_run(open_store(storage), folder.root),
                f"content storage archive {folder.root}",
            )

    if resume is None and not carry_on:
        try:
            start, brief = confirm_start(
                topic,
                brief,
                config,
                reviewer,
                lambda revised: folder.create(topic, revised),
                choices,
            )
        except ReviewDetached:
            return 2
        if start.action == "stop":
            print(f"Stopped before anything was spent: {folder.root}")
            return 2
        folder.create(topic, brief)
    ledger = ledger_for(config)
    if ledger is not None:
        # OpenRouter's own figures before anything is spent: the ledger calibrates against them.
        reading = read_openrouter(ledger)
        if not isinstance(reading, str) and reading.remaining_usd is not None:
            print(f"OpenRouter: ${reading.remaining_usd:.2f} left to spend.")
    try:
        if carry_on:
            result = continue_workflow(
                folder.steps,
                config_path=args.config,
                reviewer=reviewer,
                on_review=save,
                choices=choices,
            )
        else:
            result = run_workflow(
                topic,
                source_material=sources,
                user_instructions=brief,
                resume=resume,
                resume_stage=args.at,
                config_path=args.config,
                reviewer=reviewer,
                steps=folder.steps,
                on_review=save,
                choices=choices,
                research=research,
                fresh_research=args.fresh_research,
            )
    except (ConfigurationError, InputError) as exc:
        parser.error(str(exc))

    state = result.state
    if result.error:
        print(f"Run failed: {result.error}")
    print(f"Stopped at: {state.get('current_stage', 'unknown')} ({state.get('status', 'unknown')})")
    session = folder.work / f"session-{len(list(folder.work.glob('session-*.trace.json'))) + 1}"
    calls = state.get("call_log", [])[result.first_call :]
    summary = run_summary(calls)
    folder.record_cost(summary, state.get("current_stage", "unknown"))
    record_spend(result.config, calls, source=folder.root.name, session=session.name)
    cost = summary["total"]["cost_usd"]
    print(f"Model calls: {len(calls)}; cost: {'unknown' if cost is None else f'${cost:.4f}'}")
    write_run_summary(calls, session)
    trace = write_trace(state, session)
    # What the run paid for is written before learning, which is slow and optional.
    status = (
        2
        if result.pending_review is not None
        else _write_results(state, result.error, session, folder)
    )
    if status == 0 and result.config.storage is not None:
        finished_in = result.config.storage
        keep(
            lambda: archive_run(open_store(finished_in), folder.root),
            f"content storage archive {folder.root}",
        )
    if result.config.learning is not None:
        _learn_after_run(result.config, result.config.learning, trace)
        keep_theme(result.config)
    print(f"Run folder: {folder.root}")
    return status
