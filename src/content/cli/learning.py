"""The taste models: harvesting examples from runs, a person's labels and verdicts, training,
and the story regression (`eval`)."""

import argparse
import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from content.agents.base import load_prompt
from content.cli.storage import keep_theme
from content.config import (
    ContentConfig,
    LearningConfig,
    load_config,
)
from content.errors import ConfigurationError
from content.judging.questions import QUESTIONS
from content.learning.examples import (
    LearningStore,
    TrainingRun,
    harvest_directory,
    verdict_labels,
)
from content.learning.labelling import label_interactively
from content.schemas.audience import AudienceReport
from content.schemas.judgement import Outcome
from content.workflow.providers import (
    build_decision_provider,
    build_providers,
)


def _learning(
    parser: argparse.ArgumentParser, config_path: Path | None
) -> tuple[ContentConfig, LearningConfig]:
    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        parser.error(str(exc))
    if config.learning is None:
        parser.error("This needs a configuration with a learning section")
    return config, config.learning


def _harvest(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content harvest",
        description="Collect every past decision from the run traces as training examples.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    args = parser.parse_args(arguments)
    config, learning = _learning(parser, args.config)
    new = harvest_directory(config.application.output_directory, LearningStore(learning.directory))
    print(
        f"New examples: {len(new.examples)}; new labels: {len(new.labels)}; "
        f"flagged for labelling: {len(new.flags)}; keyframe records: {len(new.keyframes)}"
    )
    keep_theme(config)
    return 0


def _eval(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content eval",
        description=(
            "Story-quality regression: run the listener test, Jev's comprehension questions "
            "and the free checks on the fixtures beside each worked example, and report what "
            "they catch. Paid: one listener call and a few dozen Jev calls per fixture."
        ),
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument(
        "--fixtures", type=Path, help="Folder of worked examples (default: the theme's examples/)"
    )
    args = parser.parse_args(arguments)
    from content.judging.outcomes import answer_outcome
    from content.story.regression import flags, load_fixtures, score

    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    director = config.agents["editorial_director"]
    model = config.models.get(director.listener_model_alias or director.model_alias)
    provider = build_providers(config)[model.provider]
    decider = build_decision_provider(config)
    instructions = load_prompt(director.prompt.with_name("listener_prompt.md"))
    spent = 0.0

    def ask(question_id: str, state: Mapping[str, object]) -> Outcome:
        nonlocal spent
        question = QUESTIONS[question_id]
        result = decider.decide(
            model=config.decisions.model,
            state=dict(state),
            questions={question_id: question.request()},
        )
        spent += result.usage.cost_usd or 0.0
        answer = result.answers[question_id]
        return answer_outcome(question, answer, None, config.decisions)

    for fixture in load_fixtures(args.fixtures or config.theme.root / "examples"):
        heard, usage = provider.generate_structured(
            instructions=instructions,
            input_text=json.dumps({"narration": fixture.narration}),
            output_type=AudienceReport,
            model=model,
        )
        spent += usage.cost_usd or 0.0
        result = score(fixture, flags(fixture, heard, ask))
        print(f"\n{fixture.name} ({fixture.kind})")
        for expected, checks in result.caught:
            mark = "caught" if checks else "MISSED"
            print(f"  {mark:6} {expected.unit_id} {expected.pattern}: {', '.join(checks) or '-'}")
        label = "false alarms" if fixture.kind == "positive" else "also flagged"
        for flag in result.unexpected:
            print(f"  {label}: {flag.unit_id or 'narration'} {flag.check}: {flag.detail[:80]}")
    print(f"\nSpent about ${spent:.2f}.")
    return 0


def _verdict(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content verdict",
        description="Record your judgement of a finished run as labels the models learn from.",
    )
    parser.add_argument("trace", type=Path, help="The run's .trace.json")
    parser.add_argument(
        "--story", choices=["story", "list"], required=True,
        help="Does the narration sound like one person telling a story, or a list of facts?",
    )  # fmt: skip
    parser.add_argument(
        "--voice", choices=list(QUESTIONS["script_voice"].criteria), required=True,
        help="How the narration's voice comes across",
    )  # fmt: skip
    parser.add_argument("--note", default="", help="What you heard, in your words")
    parser.add_argument(
        "--exclude", action="store_true",
        help="Learn nothing else from this run: its approvals stop counting as good work",
    )  # fmt: skip
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    args = parser.parse_args(arguments)
    config, learning = _learning(parser, args.config)
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    labels = verdict_labels(trace, args.story, args.voice, args.note)
    if not labels:
        parser.error("This trace has no judged script to label")
    saved = LearningStore(learning.directory).add_labels(labels)
    trace["verdict"] = {"story": args.story, "voice": args.voice, "note": args.note}
    if args.exclude:
        trace["training"] = "exclude"
    args.trace.write_text(json.dumps(trace, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        f"Saved {len(saved)} of your labels"
        + ("; the run is excluded from anything else" if args.exclude else "")
        + "."
    )
    keep_theme(config)
    return 0


def _label(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content label",
        description="Answer taste questions yourself: the benchmark every trained model must beat.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument("--count", type=int, default=20, help="How many to label this sitting")
    args = parser.parse_args(arguments)
    config, learning = _learning(parser, args.config)
    store = LearningStore(learning.directory)
    saved = label_interactively(store, learning.local_questions, count=args.count)
    print(f"Saved {saved} labels to {store.labels_path}")
    keep_theme(config)
    return 0


def _train(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content train",
        description="Teacher-label, train and compare the local taste models against Jev.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument(
        "--budget", type=float, default=0.0, help="Most to spend on teacher labels, in USD"
    )
    parser.add_argument(
        "--max-labels", type=int, default=100, help="Most teacher labels to request"
    )
    args = parser.parse_args(arguments)
    config, learning = _learning(parser, args.config)
    from content.learning.model import FastEmbedder
    from content.learning.provider import ModelRegistry
    from content.learning.train import Teacher, train
    from content.theme import theme_guidance

    teacher = None
    if args.budget > 0:
        model = config.models.get(learning.teacher)
        instructions = load_prompt(Path(__file__).parent / "learning/teacher_prompt.md")
        teacher = Teacher(
            build_providers(config)[model.provider],
            model,
            f"{instructions}\n\n# Theme guidance\n\n{theme_guidance(config.theme)}",
        )
    report = train(
        LearningStore(learning.directory),
        ModelRegistry(learning.directory),
        FastEmbedder(learning.embedder, learning.directory / "embedder"),
        learning.local_questions,
        teacher=teacher,
        budget_usd=args.budget,
        max_teacher_labels=args.max_labels if teacher else 0,
        min_labels=learning.min_labels,
        min_gold=learning.min_gold,
    )
    store = LearningStore(learning.directory)
    store.add_training_run(
        TrainingRun(
            finished_at=datetime.now(UTC).isoformat(timespec="seconds"),
            teacher_model=teacher.model.model if teacher else None,
            teacher_labels=len(report.teacher_calls),
            cost_usd=round(report.cost_usd, 4),
            questions=[asdict(entry) for entry in report.questions],
        )
    )
    spent = sum(run.cost_usd for run in store.training_runs())
    print(
        f"Teacher labels: {len(report.teacher_calls)} for ${report.cost_usd:.4f} "
        f"(all teacher spend so far: ${spent:.2f})"
    )
    for entry in report.questions:
        scores = (
            f"local {entry.local_accuracy:.2f} vs Jev {entry.jev_accuracy:.2f}"
            if entry.local_accuracy is not None and entry.jev_accuracy is not None
            else ""
        )
        status = "PROMOTED" if entry.promoted else entry.note
        counts = f"{entry.labels} labels, {entry.gold} yours"
        print(f"  {entry.question_id}: {counts}; {scores} {status}")
    keep_theme(config)
    return 0


COMMANDS = {
    "harvest": _harvest,
    "verdict": _verdict,
    "label": _label,
    "train": _train,
    "eval": _eval,
}
