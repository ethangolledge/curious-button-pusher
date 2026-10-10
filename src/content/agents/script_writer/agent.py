"""The Script Writer: owns every word of the narration. It drafts the script from the plan and
the cited evidence, and revises either the whole script or, for notes on named lines, just
those lines."""

from typing import Any

from content.agents.base import Agent
from content.judging.outcomes import current_judgements
from content.schemas.judgement import Judgement
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.script import LineAuthor, LineEdit, LineEditPackage, ScriptPackage, ScriptUnit
from content.state import CallRecord, ContentState, RevisionRecord
from content.story.notes import split_notes
from content.story.revision_scope import (
    line_targets,
    locked_lines,
    note_units,
    unchanged_judgements,
)


class ScriptWriter(Agent):
    """The Script Writer owns every word of the narration. A first draft and a whole
    rewrite use its own model; a revision that names its lines is a line edit on the
    smaller edit model, and code keeps every other line exactly. A person's own words for
    a line are put in by code, never by a model."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.line_instructions = self.prompt("line_edit")

    def __call__(self, state: ContentState) -> ContentState:
        research_pack = state.get("research_pack")
        editorial_brief = state.get("editorial_brief")
        if research_pack is None or editorial_brief is None:
            raise ValueError("Script writing requires research and a creative plan")

        size = state.get("story_size")
        previous = state.get("script_package")
        revision_count = state.get("script_revision_count", 0)
        revisions: list[RevisionRecord] = []
        notes = state.get("revision_notes", [])
        feedback = state.get("human_review_feedback")
        reason = ""
        if previous is not None:
            revision_count += 1
            reason = "; ".join([*notes, *([feedback] if feedback else [])])
            revisions.append(
                {
                    "stage": "script",
                    "revision_number": revision_count,
                    "reason": reason or "A revision was requested.",
                }
            )
            scoped = self._revise_lines(state, previous, revision_count)
            if scoped is not None:
                return {**scoped, "revision_history": revisions}

        generated_script, call = self.generate(
            {
                "topic": state["topic"],
                # The plan as the writer needs it: what other agents use stays out.
                "creative_plan": editorial_brief.model_dump(
                    mode="json",
                    exclude={"visual_principles", "fact_check_priorities"},
                    exclude_computed_fields=True,
                ),
                "author_brief": state.get("user_instructions"),
                "evidence": _selected_evidence(
                    research_pack, editorial_brief, state.get("claim_stances", {})
                ),
                "duration_seconds": state["duration_seconds"],
                "length": {
                    "target_seconds": state["target_seconds"],
                    "word_budget": state.get("word_budget"),
                    "longest_seconds": size.longest_seconds if size else None,
                    "longest_words": size.longest_words if size else None,
                    "note": (
                        "The target is a guide: tell the story well first. The longest is a "
                        "hard limit: the platforms cut the video there."
                    ),
                },
                "music": _music_landmarks(state),
                "previous_script_package": previous,
                "corrections": notes if previous is not None else [],
                # Every evidence boundary a line has crossed in this run: the limits any
                # rewrite must stay inside. Constraints, never wording.
                "fact_constraints": [
                    constraint.model_dump(
                        include={
                            "claim_id",
                            "script_unit_ids",
                            "issue",
                            "evidence_boundary",
                            "required_qualification",
                            "forbidden_implication",
                        }
                    )
                    for constraint in state.get("fact_constraints", [])
                ],
                # Present for the oral revision: what a first-time listener took from the
                # last version, and where they stumbled. A person's note, when there is
                # one, is the whole of what to change, so the report stays out of it.
                "listener_report": None if feedback else state.get("audience_report"),
                "human_review_feedback": feedback,
                # The person's own words: every one must stand in the new script exactly.
                "locked_lines": locked_lines(state.get("line_edits", [])),
                "script_revision_number": revision_count,
            },
            ScriptPackage,
            operation="script" if previous is None else "script_revision",
        )
        script, normalization_warnings = self._normalize_units(generated_script)
        return {
            "line_edits": (
                _changes(previous, script, "writer", reason, revision_count)
                if previous is not None
                else []
            ),
            "script_package": script,
            "fact_check_report": None,
            # The listener heard the previous version; the next one is heard afresh.
            "audience_report": None,
            "visual_package": None,
            "final_package": None,
            "human_review_feedback": None,
            "revision_notes": [],
            "script_revision_count": revision_count,
            "current_stage": "script",
            "status": "running",
            "call_log": [call],
            "events": [{"stage": "script", "message": "Master script created"}],
            "revision_history": revisions,
            "script_warnings": normalization_warnings,
        }

    def _revise_lines(
        self, state: ContentState, previous: ScriptPackage, revision: int
    ) -> ContentState | None:
        """A revision confined to named lines: the person's own words put in by code, the
        rest of the named lines rewritten by the edit model, every other line untouched.
        None when the revision is the whole script's."""
        from_person = state.get("routing_decision") == "human_revise"
        response = state.get("human_review_response") if from_person else None
        units = previous.script_units
        known = {unit.unit_id: unit for unit in units}
        edits = {
            unit_id: text.strip()
            for unit_id, text in (response.edits if response else {}).items()
            if unit_id in known and text.strip() and text.strip() != known[unit_id].text
        }
        feedback = state.get("human_review_feedback")
        person = split_notes(feedback or "")
        if person.untargeted or (state.get("audience_report") is not None and not from_person):
            # A note on the whole, or the listener's report: the whole script's to answer.
            return None
        notes = [*state.get("revision_notes", []), *person.units]
        locked = {*locked_lines(state.get("line_edits", [])), *edits.values()}
        targets = line_targets(
            notes,
            units,
            locked={unit.unit_id for unit in units if unit.text in locked or unit.unit_id in edits},
            scope=response.scope if response else None,
        )
        if targets is None:
            return None
        texts = {unit.unit_id: unit.text for unit in units} | edits
        line_edits = [
            LineEdit(
                unit_id=unit_id,
                before=known[unit_id].text,
                after=text,
                author="person",
                reason="Edited by the person at the sign-off.",
                script_revision=revision,
            )
            for unit_id, text in edits.items()
        ]
        calls: list[CallRecord] = []
        warnings: list[str] = []
        tries = dict(state.get("small_edit_tries", {}))
        if targets:
            author, alias = self._line_editor(state, targets, revision)
            in_order = [unit.unit_id for unit in units if unit.unit_id in targets]
            edited, call = self.generate(
                _line_payload(state, previous, in_order, notes),
                LineEditPackage,
                operation="script_line_edit",
                model_alias=alias,
                instructions=self.line_instructions,
            )
            calls.append(call)
            if author == "editor":
                tries |= dict.fromkeys(targets, revision)
            written = {
                line.unit_id: line.text.strip()
                for line in edited.lines
                if line.unit_id in targets and line.text.strip()
            }
            missing = [unit_id for unit_id in in_order if unit_id not in written]
            if missing:
                warnings.append(f"The line edit left {', '.join(missing)} unchanged.")
            reason = "; ".join(note for note in notes if note)
            for unit_id, text in written.items():
                if text != texts[unit_id]:
                    line_edits.append(
                        LineEdit(
                            unit_id=unit_id,
                            before=texts[unit_id],
                            after=text,
                            author=author,
                            reason=reason,
                            script_revision=revision,
                        )
                    )
                    texts[unit_id] = text
        script = previous.model_copy(
            update={
                "script_units": [
                    unit.model_copy(update={"text": texts[unit.unit_id]})
                    if texts[unit.unit_id] != unit.text
                    else unit
                    for unit in units
                ]
            }
        )
        changed = {edit.unit_id for edit in line_edits}
        carried: list[Judgement] = unchanged_judgements(
            current_judgements(state, "script"), changed, units, revision
        )
        return {
            "script_package": script,
            "line_edits": line_edits,
            "small_edit_tries": tries,
            # Lines the change leaves alone keep their judgements; only touched ones are
            # asked again.
            "judgements": carried,
            "fact_check_report": None,
            "audience_report": None,
            "visual_package": None,
            "final_package": None,
            "human_review_feedback": None,
            "revision_notes": [],
            "script_revision_count": revision,
            "current_stage": "script",
            "status": "running",
            "call_log": calls,
            "events": [
                {
                    "stage": "script",
                    "message": f"Line edit: {', '.join(sorted(changed)) or 'no line changed'}",
                }
            ],
            "script_warnings": warnings,
        }

    def _line_editor(
        self, state: ContentState, targets: set[str], revision: int
    ) -> tuple[LineAuthor, str | None]:
        """The small edit model first; the writer's own model when the small one already
        edited one of these lines in the last revision and it came back again."""
        tries = state.get("small_edit_tries", {})
        again = any(tries.get(unit_id) == revision - 1 for unit_id in targets)
        if again or self.config.edit_model_alias is None:
            return "writer", None
        return "editor", self.config.edit_model_alias

    @staticmethod
    def _normalize_units(
        script: ScriptPackage,
    ) -> tuple[ScriptPackage, list[str]]:
        normalized_units: list[ScriptUnit] = []
        changed = False
        for index, unit in enumerate(script.script_units, start=1):
            updates: dict[str, object] = {
                "unit_id": f"U{index}",
                "order": index,
            }
            if index == 1:
                updates["narrative_function"] = "hook"
            normalized = unit.model_copy(update=updates)
            normalized_units.append(normalized)
            changed = changed or normalized != unit
        if not changed:
            return script, []
        return (
            script.model_copy(update={"script_units": normalized_units}),
            ["Script unit IDs, order, or opening function were normalized."],
        )


def _selected_evidence(
    research: ResearchPack, brief: EditorialBrief, stances: dict[str, str]
) -> dict[str, Any]:
    """The research's own plain account of the story, then only the claims the plan chose,
    with their qualifications, how firmly each may be stated (`assert`, `attribute`, or
    only `ask`), and the safe wording."""
    selected = {*brief.required_claim_ids, *brief.supporting_claim_ids}
    return {
        "research_summary": research.research_summary,
        "claims": [
            {**claim.model_dump(), "state_as": stances.get(claim.claim_id, "attribute")}
            for claim in research.all_claims
            if claim.claim_id in selected
        ],
        "cast": research.cast,
        # Only a `led_to` link may be told as cause; everything else is sequence.
        "documented_links": [
            link
            for link in research.links
            if link.from_claim_id in selected and link.to_claim_id in selected
        ],
        "safe_wording": research.safe_wording,
        "factual_limitations": research.factual_limitations,
    }


def _line_payload(
    state: ContentState, script: ScriptPackage, targets: list[str], notes: list[str]
) -> dict[str, Any]:
    """Only what a line edit needs: each named line with its neighbours, its beat's job,
    the claims it carries and their limits, and the notes on it. Nothing else."""
    brief, research = state.get("editorial_brief"), state.get("research_pack")
    if brief is None or research is None:
        raise ValueError("A line edit needs the plan and the research")
    units = script.script_units
    index = {unit.unit_id: position for position, unit in enumerate(units)}
    claims = {claim.claim_id: claim for claim in research.all_claims}
    phases = {phase.phase_id: phase for phase in brief.arc}
    stances = state.get("claim_stances", {})
    constraints = state.get("fact_constraints", [])

    def line(unit_id: str) -> dict[str, Any]:
        position = index[unit_id]
        unit = units[position]
        phase = phases.get(unit.arc_phase_id)
        return {
            "unit_id": unit_id,
            "text": unit.text,
            "previous_line": units[position - 1].text if position > 0 else None,
            "next_line": units[position + 1].text if position + 1 < len(units) else None,
            "beat": (
                {
                    "narrative_job": phase.narrative_job,
                    "audience_knows_after": phase.audience_knows_after,
                }
                if phase is not None
                else None
            ),
            "claims": [
                {
                    "claim": claims[claim_id].claim,
                    "qualification": claims[claim_id].qualification,
                    "state_as": stances.get(claim_id, "attribute"),
                }
                for claim_id in unit.claim_ids
                if claim_id in claims
            ],
            "fact_constraints": [
                constraint.model_dump(
                    include={
                        "issue",
                        "evidence_boundary",
                        "required_qualification",
                        "forbidden_implication",
                    }
                )
                for constraint in constraints
                if unit_id in constraint.script_unit_ids or constraint.claim_id in unit.claim_ids
            ],
            "notes": [note for note in notes if unit_id in note_units(note)],
        }

    return {
        "lines": [line(unit_id) for unit_id in targets],
        "voice_direction": script.voice_direction,
    }


def _changes(
    before: ScriptPackage,
    after: ScriptPackage,
    author: LineAuthor,
    reason: str,
    revision: int,
) -> list[LineEdit]:
    """The lines a whole rewrite changed, by unit ID."""
    old = {unit.unit_id: unit.text for unit in before.script_units}
    return [
        LineEdit(
            unit_id=unit.unit_id,
            before=old.get(unit.unit_id, ""),
            after=unit.text,
            author=author,
            reason=reason or "A revision was requested.",
            script_revision=revision,
        )
        for unit in after.script_units
        if old.get(unit.unit_id) != unit.text
    ]


def _music_landmarks(state: ContentState) -> dict[str, float] | None:
    """Where the planned edit of the music peaks, as guidance for placing the turn."""
    arrangement = state.get("arrangement")
    if arrangement is None:
        return None
    return {"music_seconds": arrangement.seconds, "peak_starts_at": arrangement.peak_at}
