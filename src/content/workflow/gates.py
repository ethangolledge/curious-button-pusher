"""Pure-code workflow nodes: exact structural gates and System 1 verdicts.

Gates check references and budgets and never call a model. Verdicts combine the
current revision's Jev judgements into one decision and a set of targeted
corrections; `routing.py` turns that decision into an edge.
"""

from content.config import WorkflowConfig
from content.judging.outcomes import (
    correction_line,
    current_judgements,
    judgement_line,
    stage_verdict,
)
from content.production.music_map import MusicMap
from content.production.score import arrangements, choose
from content.schemas.judgement import JudgedStage
from content.schemas.media import Arrangement
from content.schemas.plan import EditorialBrief, StorySize
from content.schemas.visuals import VisualPackage
from content.staging.catalogue import Catalogue
from content.staging.plan import staging_issues, unstage
from content.state import ContentState, merge_warnings
from content.story.faithfulness import Inference, contradiction_issues
from content.story.field import unit_feelings
from content.story.ledger import (
    listener_findings,
    listener_line,
    opening_issues,
    script_issues,
    visual_issues,
)
from content.story.pace import (
    NarrationEstimate,
    estimate,
    length_issues,
    passages,
    planned_seconds,
    story_seconds,
    word_budget,
    words_per_second,
)
from content.story.prose import (
    dense_issues,
    fragment_issues,
    question_issues,
    repetition_issues,
    setup_question_issues,
    stock_phrase_issues,
)
from content.story.revision_scope import locked_lines, note_units
from content.story.weights import (
    allot_words,
    claim_weights,
    evidence,
    hook_issues,
    selection_issues,
    stance,
    tell_beats,
    turn_issues,
)
from content.theme import Theme


def plan_verdict(
    state: ContentState,
    *,
    workflow: WorkflowConfig,
    theme: Theme,
    music: MusicMap | None,
) -> ContentState:
    judgements = current_judgements(state, "plan")
    verdict = stage_verdict(judgements)
    # The plan is the control plane: a person approves it unless explicitly configured
    # otherwise, and any problem with it goes to a person rather than an automatic rewrite.
    accept = verdict.route == "accept" and not workflow.review_plan
    brief, research = state.get("editorial_brief"), state.get("research_pack")
    sizing: ContentState = {}
    if brief is not None and research is not None and brief.claims:
        # The planner decides what matters (each claim's story role); code gives each beat
        # the time its claims deserve, and the weights advise which facts to build on, how
        # each beat is told, and where the hook and turn belong.
        weights = theme.spec.writing.weights
        claims = claim_weights(research, judgements, weights)
        brief = allot_words(
            brief, claims, weights, theme.spec.voice, longest_narration(theme, music)
        )
        brief = tell_beats(brief, claims, weights)
        size, arrangement = size_story(brief, theme, music)
        size = size.model_copy(
            update={"claims": sorted(claims.values(), key=lambda claim: -claim.score)}
        )
        sizing = {
            "editorial_brief": brief,
            "warnings": merge_warnings(
                state.get("warnings", []),
                [
                    *selection_issues(
                        brief, claims, estimate=size.estimate_seconds, longest=size.longest_seconds
                    ),
                    *hook_issues(brief, claims, weights),
                    *turn_issues(brief, claims, weights),
                ],
            ),
            "story_size": size,
            "claim_stances": {
                claim_id: stance(value, weights)
                for claim_id, value in evidence(research, weights).items()
            },
            "target_seconds": size.target_seconds,
            "word_budget": word_budget(
                size.target_seconds, theme.spec.voice, passage_count=len(brief.arc)
            ),
            "arrangement": arrangement,
        }
    return {
        **_decision(
            "plan",
            "accept" if accept else "human_review",
            verdict.corrections,
            structural=False,
            message=f"Plan verdict: {verdict.route}",
        ),
        **sizing,
    }


def longest_narration(theme: Theme, music: MusicMap | None) -> float:
    """The most narration the longest allowed video holds: it must end before the
    shortest outro of the longest edit of the music."""
    longest = theme.spec.format.max_seconds
    longest_video = (
        max(option.seconds for option in arrangements(music, longest))
        if music is not None
        else longest
    )
    return longest_video - theme.spec.music.outro_seconds[0]


def size_story(
    brief: EditorialBrief, theme: Theme, music: MusicMap | None
) -> tuple[StorySize, Arrangement | None]:
    """How long the plan's story is, from its beats' words, and the edit of the music
    nearest it. The plan's length becomes the writer's target: a guide, not a limit."""
    voice = theme.spec.voice
    beats = planned_seconds([phase.words for phase in brief.arc], voice)
    estimate = story_seconds(beats, voice)
    outro = theme.spec.music.outro_seconds
    middle = sum(outro) / 2
    longest = theme.spec.format.max_seconds
    arrangement = choose(music, estimate, outro, longest) if music is not None else None
    longest_seconds = longest_narration(theme, music)
    target = arrangement.seconds - middle if arrangement is not None else estimate
    rate = words_per_second(voice)
    edits = (
        [
            (option.seconds, round((option.seconds - middle - estimate) * rate))
            for option in arrangements(music, longest)
        ]
        if music is not None
        else []
    )
    return (
        StorySize(
            estimate_seconds=round(estimate, 1),
            target_seconds=round(target, 1),
            beat_seconds={
                phase.phase_id: round(seconds, 1)
                for phase, seconds in zip(brief.arc, beats, strict=True)
            },
            edits=edits,
            longest_seconds=round(longest_seconds, 1),
            longest_words=word_budget(longest_seconds, voice, passage_count=len(brief.arc)),
        ),
        arrangement,
    )


def check_script(
    state: ContentState, *, theme: Theme, faithfulness: Inference | None
) -> ContentState:
    """Blocking, exact checks: the claims, the opening's structure, and the writing that
    was measured to sound robotic (verbless statements, overloaded sentences, set-up
    questions, an ending that repeats). Advisory, shown at review but never forcing a
    rewrite: narration past the longest video, or a gross miss of the planned length (the
    music adapts), which rides along with any rewrite the blocking checks force; and a line
    its own claims appear to contradict (a hint for the fact checker, until that model is
    validated on more labelled lines)."""
    script, brief, research = (
        state.get("script_package"),
        state.get("editorial_brief"),
        state.get("research_pack"),
    )
    if script is None or brief is None or research is None:
        raise ValueError("The script gate requires a script, plan, and research")
    prediction = _predicted_narration(state, theme)
    size = state.get("story_size")
    units = script.script_units
    ending = passages(units)[-1].unit_ids if units else []
    issues = [
        *script_issues(script, brief, research),
        *opening_issues(script, brief, research),
        *fragment_issues(units),
        *dense_issues(units),
        *setup_question_issues(units),
        *question_issues(units, ending),
        *repetition_issues(units, ending),
    ]
    # The person's own lines are final: what the checks notice about them is shown, never
    # sent back for a rewrite; and a rewrite that lost one is sent back.
    locked = locked_lines(state.get("line_edits", []))
    theirs = {unit.unit_id for unit in units if unit.text in locked}
    advice_on_theirs = [
        issue for issue in issues if note_units(issue) and note_units(issue) <= theirs
    ]
    issues = [issue for issue in issues if issue not in advice_on_theirs] + [
        f'The director\'s line "{text}" must stand word for word as its own line; put it back.'
        for text in locked
        if text not in {unit.text for unit in units}
    ]
    longest = (
        size.longest_seconds
        if size is not None
        else theme.spec.format.max_seconds - theme.spec.music.outro_seconds[0]
    )
    length = length_issues(prediction, state["target_seconds"], longest, theme.spec.voice)
    advisory = [
        *advice_on_theirs,
        *stock_phrase_issues(units),
        *length,
        *(contradiction_issues(script, research, faithfulness) if faithfulness else []),
    ]
    return {
        "script_warnings": merge_warnings(state.get("script_warnings", []), advisory),
        **_decision(
            "script",
            "repair" if issues else "judge",
            # A rewrite that is happening anyway also fixes the length.
            [*issues, *length] if issues else [],
            structural=bool(issues),
            message=(
                f"Script structure: {len(issues)} blocking issue(s); narration predicted at "
                f"{prediction.total_seconds:.0f} s, planned {state['target_seconds']:.0f} s"
            ),
        ),
        "unit_seconds": {
            unit_id: round(seconds, 1) for unit_id, seconds in prediction.unit_seconds.items()
        },
    }


def script_verdict(state: ContentState, *, theme: Theme) -> ContentState:
    judgements = current_judgements(state, "script")
    verdict = stage_verdict(judgements)
    # One weighty line can land; a script full of them drags. Code keeps the count.
    weighty = [
        judgement
        for judgement in judgements
        if judgement.question_id == "unit_plain" and judgement.outcome == "fail"
    ]
    excess = weighty[: max(len(weighty) - theme.spec.writing.max_weighty_lines, 0)]
    route, corrections = verdict.route, verdict.corrections
    if excess:
        route = "revise"
        corrections = [*corrections, *(correction_line(judgement) for judgement in excess)]
    return {
        **_decision(
            "script",
            route,
            corrections,
            structural=False,
            message=f"Script verdict from {len(judgements)} judgements: {route}",
        ),
        "unit_feelings": unit_feelings(judgements),
    }


def audience_verdict(state: ContentState) -> ContentState:
    """Did a first-time listener understand the story the plan meant to tell?

    `pass` goes on to the Script sign-off. When something the listener found confusing or
    unrelated sits on a required claim, it is the Story Architect's call (`story`): only
    the Architect may change what the story requires. Everything else (a term, a lost
    thread, a beat the listener missed) is the writer's to fix in an oral revision
    (`script`). The stage stays the fact check's, so the person sees the listener's
    report at the Script sign-off."""
    script, brief, report = (
        state.get("script_package"),
        state.get("editorial_brief"),
        state.get("audience_report"),
    )
    if script is None or brief is None or report is None:
        raise ValueError("The audience verdict needs the script, the plan, and the listener test")
    findings = listener_findings(report, script.script_units)
    missed = [
        judgement
        for judgement in current_judgements(state, "audience")
        if judgement.blocking and judgement.outcome == "fail"
    ]
    required = set(brief.required_claim_ids)
    cited = {unit.unit_id: set(unit.claim_ids) for unit in script.script_units}
    on_required = [
        finding
        for finding in findings
        if finding.kind in {"confusion", "unrelated"}
        and finding.unit_id is not None
        and cited[finding.unit_id] & required
    ]
    notes = [
        *(listener_line(finding) for finding in findings),
        *(correction_line(judgement) for judgement in missed),
    ]
    route = "story" if on_required else "script" if notes else "pass"
    return {
        "routing_decision": route,
        "revision_notes": notes,
        "structural_blockers": False,
        "events": [
            {
                "stage": "audience",
                "message": (
                    f"Listener test: {route}; {len(findings)} stumble(s), "
                    f"{len(missed)} beat(s) or story missed"
                ),
            }
        ],
    }


def check_visuals(
    state: ContentState,
    *,
    theme: Theme,
    catalogue: Catalogue | None = None,
    most_revisions: int = 0,
) -> ContentState:
    visuals, script = state.get("visual_package"), state.get("script_package")
    if visuals is None or script is None:
        raise ValueError("The visual gate requires a visual plan and script")
    issues = [
        *visual_issues(visuals, script, theme.spec.visual.camera_moves),
        *scene_count_issues(visuals, state.get("scene_allowance")),
    ]
    unstaged: ContentState = {}
    if catalogue is not None:
        staging = staging_issues(visuals, theme, catalogue)
        if staging and state.get("visual_revision_count", 0) >= most_revisions:
            # Out of revisions: the scenes whose staging cannot be built are drawn instead.
            failing = {issue.split(" ", 1)[0] for issue in staging}
            unstaged = {"visual_package": unstage(visuals, failing, "its staging did not check")}
            staging = []
        issues += staging
    return {
        **_decision(
            "visuals",
            "repair" if issues else "judge",
            issues,
            structural=bool(issues),
            message=f"Visual structure: {len(issues)} blocking issue(s)",
        ),
        **unstaged,
    }


def scene_count_issues(visuals: VisualPackage, allowance: int | None) -> list[str]:
    """Each scene costs a keyframe and an AI morph into the next, so the budget sets how
    many scenes the story can have. The narration never changes to fit; scenes merge."""
    if allowance is None or len(visuals.scenes) <= allowance:
        return []
    return [
        f"The storyboard has {len(visuals.scenes)} scenes; the budget allows {allowance}. "
        "Merge neighbouring scenes at the quietest joins so each picture holds longer."
    ]


def visual_verdict(state: ContentState) -> ContentState:
    judgements = current_judgements(state, "visuals")
    verdict = stage_verdict(judgements)
    return _decision(
        "visuals",
        verdict.route,
        verdict.corrections,
        structural=False,
        message=f"Visual verdict from {len(judgements)} judgements: {verdict.route}",
    )


def judgement_findings(state: ContentState, stage: JudgedStage) -> list[str]:
    """Readable lines for every judgement that did not simply pass."""
    return [
        judgement_line(judgement)
        for judgement in current_judgements(state, stage)
        if judgement.outcome != "pass"
    ]


def _predicted_narration(state: ContentState, theme: Theme) -> NarrationEstimate:
    script = state.get("script_package")
    if script is None:
        raise ValueError("Predicting narration requires a script")
    return estimate(
        passages(script.script_units, theme.speaker(script.voice_direction)), theme.spec.voice
    )


def _decision(
    stage: str,
    route: str,
    notes: list[str],
    *,
    structural: bool,
    message: str,
) -> ContentState:
    return {
        "current_stage": stage,
        "routing_decision": route,
        "revision_notes": notes,
        "structural_blockers": structural,
        "events": [{"stage": stage, "message": message}],
    }
