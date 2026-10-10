"""Training data for the decision models, rebuilt from run traces.

Every Jev judgement becomes an example: the exact state Jev saw, the question, and Jev's
answer. A trace records every model output in order, so the states are rebuilt by
replaying those outputs through the same task builders the graph used. Nothing extra has
to be stored during a run.

Labels come from four places, strongest first:
- a person: `python -m content label`, or a `feel` note on the story sheet;
- what happened later (the fact checker's verdict on a unit);
- a person's review: approving a stage confirms Jev's passing answers on what was approved;
- a teacher model (`python -m content train`).

A person's review can also point at an example without giving its answer: a targeted
note, or approving something Jev failed. Those become flags, labelled first.

The store also keeps the raw data other fitted models learn from: every narration clip's
spoken length (the pace fit) and every keyframe's measured colour against its target.
"""

import hashlib
import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar

from content.agents.fact_checker.agent import BLOCKING_STATUSES
from content.judging.judge import JudgementTask
from content.judging.questions import QUESTIONS
from content.learning.provider import LOCAL_PREFIX
from content.schemas.base import ImmutableModel
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Answer, Judgement
from content.schemas.media import ColourCheck
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.review import HumanDecision
from content.schemas.script import ScriptPackage
from content.schemas.visuals import VisualPackage
from content.story.ledger import plan_tasks, script_tasks, visual_tasks
from content.story.notes import FEEL, split_notes

Record = TypeVar("Record", bound=ImmutableModel)
LabelSource = Literal["human", "outcome", "review", "teacher"]
SOURCE_STRENGTH: dict[str, int] = {"human": 4, "outcome": 3, "review": 2, "teacher": 1}
# The judged stage each review stage approves.
REVIEWED_STAGE = {
    "plan": "plan",
    "script": "script",
    "visuals": "visuals",
    "storyboard": "visuals",
    "final_cut": "visuals",
}


class Example(ImmutableModel):
    example_id: str
    question_id: str
    state: dict[str, Any]
    jev: Answer


class Label(ImmutableModel):
    example_id: str
    question_id: str
    # "yes"/"no" for yes-no questions, the option key for choices, the level for scores.
    answer: str
    source: LabelSource
    reason: str = ""


class Flag(ImmutableModel):
    """An example a person's review points at without giving the answer."""

    example_id: str
    question_id: str
    note: str


class NarrationSample(ImmutableModel):
    """One spoken clip: what was said, by which voice and direction, and how long it took
    once its silence was trimmed. The voice's measured pace comes from these
    (`theme.with_measured_voice`), so scripts are sized at what it delivers."""

    clip: str
    model: str
    voice: str | None
    reference: str | None
    direction: str | None
    text: str
    seconds: float


class KeyframeRecord(ImmutableModel):
    """One keyframe's colour, measured against what its scene's field asked for, and
    whether a person approved the storyboard it was on."""

    signature: str
    attempt: int
    scene_id: str
    colour: ColourCheck
    issues: list[str]
    approved: bool


class TrainingRun(ImmutableModel):
    """One `train` run: what it spent on the teacher and where each question stood."""

    finished_at: str
    teacher_model: str | None
    teacher_labels: int
    cost_usd: float
    # Per question: labels, how many were yours, both accuracies, and the outcome.
    questions: list[dict[str, Any]]


@dataclass
class Harvest:
    examples: list[Example] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    keyframes: list[KeyframeRecord] = field(default_factory=list)


def example_id(question_id: str, state: dict[str, Any]) -> str:
    canonical = json.dumps({"q": question_id, "s": state}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:20]


def jev_label(answer: Answer) -> str:
    """Jev's answer in label form, so it can be scored against people's labels."""
    if answer.kind == "noul":
        return "yes" if (answer.noul or 0) >= 0.5 else "no"
    if answer.kind == "choice":
        return answer.choice or ""
    top = max(answer.probabilities, key=lambda level: answer.probabilities[level], default="")
    return top or str(round(answer.score or 0))


@dataclass
class _Replay:
    """A trace's model outputs replayed through the task builders: every Jev judgement
    paired with the exact state it judged, keyed by (stage, revision, target)."""

    outputs: list[dict[str, Any]]
    scripts: list[ScriptPackage]
    storyboards: dict[int, VisualPackage]
    final_script: int
    judged: dict[tuple[str, int, str], list[tuple[Example, Judgement]]]


def _replay(trace: dict[str, Any]) -> _Replay | None:
    outputs = [call for call in trace.get("calls", []) if call.get("output") is not None]
    # A resumed run made neither: the trace carries the ones it started from.
    carried = trace.get("research_and_plan", {})
    research = _latest(outputs, "research", ResearchPack) or _carried(
        carried, "research_pack", ResearchPack
    )
    if research is None:
        return None
    plans = _all(outputs, {"plan"}, EditorialBrief) or [
        brief for brief in [_carried(carried, "editorial_brief", EditorialBrief)] if brief
    ]
    scripts = _all(outputs, {"script", "script_revision"}, ScriptPackage)
    storyboards = _all(outputs, {"storyboard", "storyboard_revision"}, VisualPackage)
    counts = trace.get("revision_counts", {})
    tasks: dict[tuple[str, int, str], JudgementTask] = {}
    for revision, plan in _numbered(plans, counts.get("plan")):
        tasks.update(_indexed(plan_tasks(plan, research, revision)))
    brief = plans[-1] if plans else None
    if brief is not None:
        for revision, script in _numbered(scripts, counts.get("script")):
            tasks.update(_indexed(script_tasks(script, brief, research, revision)))
    if scripts:
        for revision, storyboard in _numbered(storyboards, counts.get("visuals")):
            tasks.update(_indexed(visual_tasks(storyboard, scripts[-1], revision)))
    judged: dict[tuple[str, int, str], list[tuple[Example, Judgement]]] = {}
    for raw in trace.get("judgements", []):
        judgement = Judgement.model_validate(raw)
        key = (judgement.stage, judgement.revision, judgement.target_id)
        task = tasks.get(key)
        # Our own models' answers are not Jev's, so they are never examples of Jev.
        if task is None or judgement.model.startswith(LOCAL_PREFIX):
            continue
        example = Example(
            example_id=example_id(judgement.question_id, task["state"]),
            question_id=judgement.question_id,
            state=task["state"],
            jev=judgement.answer,
        )
        judged.setdefault(key, []).append((example, judgement))
    return _Replay(
        outputs=outputs,
        scripts=scripts,
        storyboards=dict(_numbered(storyboards, counts.get("visuals"))),
        final_script=counts.get("script", len(scripts) - 1),
        judged=judged,
    )


def harvest(trace: dict[str, Any]) -> Harvest:
    """Examples for every text judgement Jev made in one trace, with the labels and flags
    its outcomes and a person's reviews give them, and its keyframes' colour records."""
    decisions = [HumanDecision.model_validate(raw) for raw in trace.get("human_decisions", [])]
    keyframes = _keyframe_records(trace, decisions)
    replay = _replay(trace)
    if replay is None:
        return Harvest(keyframes=keyframes)
    examples = [example for pairs in replay.judged.values() for example, _ in pairs]
    # A run a person marked as not to learn from keeps its examples but teaches nothing.
    if trace.get("training") == "exclude":
        decisions = []
    labels, flags = _review_signals(
        decisions, replay.judged, replay.storyboards, replay.final_script
    )
    return Harvest(
        examples=examples,
        labels=[*_fact_check_outcomes(replay.outputs, examples, replay.scripts), *labels],
        flags=flags,
        keyframes=keyframes,
    )


def verdict_labels(trace: dict[str, Any], story: str, voice: str, note: str) -> list[Label]:
    """A person's judgement of a run's finished script, as labels on the questions Jev
    answered about the whole script: is it a told story, and how does its voice come
    across. Only the last script revision is labelled: it is the one the person heard."""
    replay = _replay(trace)
    if replay is None:
        return []
    answers = {"script_story": "yes" if story == "story" else "no", "script_voice": voice}
    last = max((revision for stage, revision, _ in replay.judged if stage == "script"), default=0)
    return [
        _label(example, answers[example.question_id], "human", note)
        for (stage, revision, _), pairs in replay.judged.items()
        if (stage, revision) == ("script", last)
        for example, _ in pairs
        if example.question_id in answers
    ]


def _review_signals(
    decisions: list[HumanDecision],
    judged: dict[tuple[str, int, str], list[tuple[Example, Judgement]]],
    storyboards: dict[int, VisualPackage],
    final_script: int,
) -> tuple[list[Label], list[Flag]]:
    """What a person's reviews say about Jev's answers.

    - Approving a stage confirms each passing answer on what was approved (a `review`
      label); an approved answer Jev failed is a disagreement, flagged. An unsure answer
      is neither: it already heads the labelling queue by its uncertainty.
    - `S4: feel brace` answers the reaction question for a one-unit scene (a person's
      label); for a scene of several units it flags each unit's reaction instead.
    - Any other targeted note flags every example about its target, with the note.
    Measurements are never confirmed by an approval: nobody reviews them one by one.
    """
    labels: list[Label] = []
    flags: list[Flag] = []
    for decision in decisions:
        stage = REVIEWED_STAGE.get(decision.stage)
        # Only a person's decisions teach: an assistant's, or an unrecorded one, might be
        # approving work the person would not have.
        if decision.decided_by != "person":
            continue
        if stage is None:
            continue
        script_revision = (
            decision.revision
            if stage == "script"
            else decision.script_revision
            if decision.script_revision is not None
            else final_script
        )
        if decision.action == "approve":
            for (judged_stage, revision, _), pairs in judged.items():
                if (judged_stage, revision) != (stage, decision.revision):
                    continue
                for example, judgement in pairs:
                    if QUESTIONS[example.question_id].measure:
                        continue
                    if judgement.outcome == "pass":
                        labels.append(_label(example, jev_label(example.jev), "review"))
                    elif judgement.outcome == "fail":
                        flags.append(
                            Flag(
                                example_id=example.example_id,
                                question_id=example.question_id,
                                note=f"You approved this; Jev answered {jev_label(example.jev)}.",
                            )
                        )
        notes = split_notes(decision.feedback or "")
        for note in [*notes.units, *notes.scenes]:
            target, body = note.split(":", 1)
            # A quoted line is replacement wording handed to the writer, not a critique.
            if body.strip().startswith('"'):
                continue
            if note.startswith("U"):
                about = judged.get(("script", script_revision, target), [])
                flags += [_flag(example, note) for example, _ in about]
                continue
            scene = _scene(storyboards, decision.revision, target) if stage == "visuals" else None
            if (feel := FEEL.match(note)) and scene is not None:
                units = scene.script_unit_ids
                for unit in units:
                    for example, _ in judged.get(("script", script_revision, unit), []):
                        if example.question_id != "unit_reaction":
                            continue
                        if len(units) == 1:
                            labels.append(_label(example, feel.group(2), "human", note))
                        else:
                            flags.append(_flag(example, note))
                continue
            about = judged.get(("visuals", decision.revision, target), [])
            flags += [_flag(example, note) for example, _ in about]
    return labels, flags


def _scene(storyboards: dict[int, VisualPackage], revision: int, scene_id: str) -> Any:
    if revision not in storyboards:
        return None
    return next((s for s in storyboards[revision].scenes if s.scene_id == scene_id), None)


def _numbered(items: list[Any], final: int | None) -> list[tuple[int, Any]]:
    """Each artifact with its revision number: in order, the last one being `final`. A
    resumed run's first artifact is therefore numbered where the run picked up."""
    last = len(items) - 1 if final is None else final
    return [(last - (len(items) - 1 - index), item) for index, item in enumerate(items)]


def _carried(carried: dict[str, Any], key: str, model: Any) -> Any:
    raw = carried.get(key)
    return model.model_validate(raw) if raw is not None else None


def _label(example: Example, answer: str, source: LabelSource, reason: str = "") -> Label:
    return Label(
        example_id=example.example_id,
        question_id=example.question_id,
        answer=answer,
        source=source,
        reason=reason,
    )


def _flag(example: Example, note: str) -> Flag:
    return Flag(example_id=example.example_id, question_id=example.question_id, note=note)


def _keyframe_records(
    trace: dict[str, Any], decisions: list[HumanDecision]
) -> list[KeyframeRecord]:
    approved = any(
        d.action == "approve"
        and d.decided_by == "person"
        and d.stage in {"storyboard", "final_cut"}
        for d in decisions
    )
    return [
        KeyframeRecord(
            signature=raw["signature"],
            attempt=raw["attempt"],
            scene_id=raw["scene_id"],
            colour=ColourCheck.model_validate(raw["colour"]),
            issues=raw["issues"],
            approved=approved,
        )
        for raw in trace.get("keyframes", [])
        if raw.get("colour") is not None
    ]


def _fact_check_outcomes(
    outputs: list[dict[str, Any]],
    examples: list[Example],
    scripts: list[ScriptPackage],
) -> list[Label]:
    """The fact checker's verdict on a unit answers "is it supported?" for that unit."""
    labels = []
    by_unit_text = {
        example.state["unit"]["text"]: example
        for example in examples
        if example.question_id == "unit_supported"
    }
    script_index = -1
    for call in outputs:
        if call["operation"] in {"script", "script_revision"}:
            script_index += 1
        if call["operation"] != "fact_check" or script_index < 0:
            continue
        report = FactCheckReport.model_validate(call["output"])
        for unit in scripts[script_index].script_units:
            example = by_unit_text.get(unit.text)
            statuses = [
                f.status for f in report.claim_findings if unit.unit_id in f.script_unit_ids
            ]
            if example is None or not statuses:
                continue
            blocked = any(status in BLOCKING_STATUSES for status in statuses)
            labels.append(
                Label(
                    example_id=example.example_id,
                    question_id="unit_supported",
                    answer="no" if blocked else "yes",
                    source="outcome",
                    reason="fact check",
                )
            )
    return labels


def _indexed(tasks: Iterable[JudgementTask]) -> dict[tuple[str, int, str], JudgementTask]:
    return {(task["stage"], task["revision"], task["target_id"]): task for task in tasks}


def _all(outputs: list[dict[str, Any]], operations: set[str], model: Any) -> list[Any]:
    return [model.model_validate(c["output"]) for c in outputs if c["operation"] in operations]


def _latest(outputs: list[dict[str, Any]], operation: str, model: Any) -> Any:
    found = _all(outputs, {operation}, model)
    return found[-1] if found else None


class LearningStore:
    """Examples and labels as append-only JSON lines, readable and diffable."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.examples_path = directory / "examples.jsonl"
        self.labels_path = directory / "labels.jsonl"
        self.flags_path = directory / "flags.jsonl"
        self.narration_path = directory / "narration.jsonl"
        self.keyframes_path = directory / "keyframes.jsonl"
        self.training_path = directory / "training.jsonl"

    def examples(self) -> dict[str, Example]:
        return {e.example_id: e for e in _read(self.examples_path, Example)}

    def labels(self) -> list[Label]:
        return list(_read(self.labels_path, Label))

    def best_labels(self) -> dict[str, Label]:
        """One label per example: a person's beats an outcome, which beats a teacher's."""
        best: dict[str, Label] = {}
        for label in self.labels():
            current = best.get(label.example_id)
            if current is None or SOURCE_STRENGTH[label.source] >= SOURCE_STRENGTH[current.source]:
                best[label.example_id] = label
        return best

    def add_examples(self, examples: Iterable[Example]) -> list[Example]:
        return _add_new(self.examples_path, Example, examples, lambda e: e.example_id)

    def add_labels(self, labels: Iterable[Label]) -> list[Label]:
        return _add_new(
            self.labels_path,
            Label,
            labels,
            lambda label: (label.example_id, label.source, label.answer),
        )

    def flags(self) -> list[Flag]:
        return list(_read(self.flags_path, Flag))

    def add_flags(self, flags: Iterable[Flag]) -> list[Flag]:
        return _add_new(self.flags_path, Flag, flags, lambda f: (f.example_id, f.note))

    def narration(self) -> list[NarrationSample]:
        return list(_read(self.narration_path, NarrationSample))

    def add_narration(self, samples: Iterable[NarrationSample]) -> list[NarrationSample]:
        return _add_new(self.narration_path, NarrationSample, samples, lambda s: s.clip)

    def keyframes(self) -> list[KeyframeRecord]:
        return list(_read(self.keyframes_path, KeyframeRecord))

    def add_keyframes(self, records: Iterable[KeyframeRecord]) -> list[KeyframeRecord]:
        return _add_new(
            self.keyframes_path, KeyframeRecord, records, lambda r: (r.signature, r.attempt)
        )

    def training_runs(self) -> list[TrainingRun]:
        return list(_read(self.training_path, TrainingRun))

    def add_training_run(self, run: TrainingRun) -> None:
        _append(self.training_path, [run])

    def add(self, found: Harvest) -> Harvest:
        """Store everything new in a harvest, and return just that."""
        return Harvest(
            examples=self.add_examples(found.examples),
            labels=self.add_labels(found.labels),
            flags=self.add_flags(found.flags),
            keyframes=self.add_keyframes(found.keyframes),
        )


def harvest_directory(output_directory: Path, store: LearningStore) -> Harvest:
    """Add everything new from every session trace in every run folder to the store."""
    found = Harvest()
    for path in sorted(output_directory.glob("*/.work/session-*.trace.json")):
        one = harvest(json.loads(path.read_text(encoding="utf-8")))
        found.examples += one.examples
        found.labels += one.labels
        found.flags += one.flags
        found.keyframes += one.keyframes
    return store.add(found)


def _read(path: Path, model: Any) -> Iterator[Any]:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield model.model_validate_json(line)


def _add_new(
    path: Path, model: type[Record], records: Iterable[Record], key: Callable[[Record], Any]
) -> list[Record]:
    """Append the records not already stored (by `key`); return them."""
    known = {key(record) for record in _read(path, model)}
    new = list({key(record): record for record in records if key(record) not in known}.values())
    _append(path, new)
    return new


def _append(path: Path, records: Iterable[ImmutableModel]) -> None:
    lines = [record.model_dump_json() for record in records]
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
