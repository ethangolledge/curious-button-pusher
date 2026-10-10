"""The maths that places and sizes a story's statements, from three numbers per claim:

- **evidence** `e` (code, from the research's own classification): how far it can be
  stated as fact;
- **worth** `w` (a Jev measurement): how much a curious stranger would want to know it;
- **connection** `c` (a Jev measurement): how much it changes the way the hook lands.

Each claim's score is `s = w · c · min(1, e / full_evidence)`: a fact is worth telling
when it matters, ties back to the hook, and can be stood behind.

Time comes from each claim's story role first (`allot_words`): the plan's ledger says what
is spine, essential context, supporting evidence, colour, or expendable, and each role has a
band of seconds in the theme. Within its band, a claim sits higher the stronger its score
and the more claims rest on it, so the central revelation slows down and a bridge passes
quickly. When the story runs past the longest video, colour goes first, then supporting
evidence and essential context shrink to their minimum; the spine is never squeezed.

The scores also advise which
facts to build on (the strongest few, found where the scores naturally break), set each
beat's telling (the logician's `logic`, the storyteller's `feeling`, or `curiosity` when
the evidence can only be asked about), tell the writer how to state each claim, and check
that the strongest beat after the hook falls where the music peaks. The constants are the
theme's open weights (`writing.weights`), to be fitted to a person's verdicts.
"""

from collections.abc import Sequence
from typing import Literal

from content.schemas.judgement import Judgement
from content.schemas.plan import ArcPhase, ClaimWeight, EditorialBrief
from content.schemas.research import ResearchClaim, ResearchPack
from content.schemas.story import StoryRole
from content.story.pace import spoken_seconds, story_seconds
from content.theme import StoryWeights, VoiceSpec

Telling = Literal["logic", "feeling", "curiosity"]
EvidenceKind = Literal["verified", "reported", "disputed", "inference", "unsupported"]
Stance = Literal["assert", "attribute", "ask"]


def evidence(research: ResearchPack, weights: StoryWeights) -> dict[str, float]:
    """How far each claim can be stated as fact, from the research's classification, less
    a penalty for resting on one source."""
    buckets: dict[EvidenceKind, list[ResearchClaim]] = {
        "verified": research.verified_facts,
        "reported": research.reported_claims,
        "disputed": research.disputed_claims,
        "inference": research.inferences,
        "unsupported": research.unsupported_claims,
    }
    return {
        claim.claim_id: round(
            max(
                weights.evidence[kind]
                - (weights.single_source_penalty if len(claim.source_ids) < 2 else 0.0),
                0.0,
            ),
            2,
        )
        for kind, claims in buckets.items()
        for claim in claims
    }


def stance(value: float, weights: StoryWeights) -> Stance:
    if value >= weights.assert_from:
        return "assert"
    return "attribute" if value >= weights.attribute_from else "ask"


def claim_weights(
    research: ResearchPack, judgements: Sequence[Judgement], weights: StoryWeights
) -> dict[str, ClaimWeight]:
    """Every claim Jev measured, with its three numbers and its score (0 to 1)."""
    measured: dict[str, dict[str, float]] = {}
    for judgement in judgements:
        if judgement.question_id in {"claim_worth", "claim_connection"}:
            measured.setdefault(judgement.target_id, {})[judgement.question_id] = (
                _expected_level(judgement) / 2
            )
    grounded = evidence(research, weights)
    result = {}
    for claim_id, values in measured.items():
        if claim_id not in grounded or len(values) < 2:
            continue
        e, w, c = grounded[claim_id], values["claim_worth"], values["claim_connection"]
        score = w * c * min(1.0, e / weights.full_evidence)
        result[claim_id] = ClaimWeight(
            claim_id=claim_id,
            evidence=e,
            worth=round(w, 2),
            connection=round(c, 2),
            score=round(score, 3),
        )
    return result


def strongest(claims: dict[str, ClaimWeight]) -> set[str]:
    """The claims worth building the story on: the upper group where the scores split most
    naturally in two (Jenks natural breaks with two classes, which for sorted numbers is
    the split with the least spread within each side). No fixed count or threshold."""
    ranked = sorted(claims.values(), key=lambda claim: -claim.score)
    if len(ranked) < 3:
        return {claim.claim_id for claim in ranked}
    scores = [claim.score for claim in ranked]

    def spread(values: list[float]) -> float:
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values)

    split = min(range(1, len(scores)), key=lambda k: spread(scores[:k]) + spread(scores[k:]))
    return {claim.claim_id for claim in ranked[:split]}


def selection_issues(
    brief: EditorialBrief, claims: dict[str, ClaimWeight], *, estimate: float, longest: float
) -> list[str]:
    """Advice for the person and the planner: build on the strongest facts and give them
    room, rather than fitting more in. Never changes the plan."""
    best = strongest(claims)
    told = {claim_id for beat in brief.arc for claim_id in beat.claim_ids}
    weak = sorted(told & claims.keys() - best - {brief.hook_claim_id or ""})
    missing = sorted(best - told)
    issues = []
    if weak:
        issues.append(
            "Weaker than the story's strongest facts: "
            + ", ".join(f"{c} ({claims[c].score:.2f})" for c in weak)
            + ". Keep one only if the story needs it to make sense; leaving it out gives "
            "the strong facts room to land."
        )
    if missing:
        issues.append(
            "Among the strongest facts but not told: "
            + ", ".join(f"{c} ({claims[c].score:.2f})" for c in missing)
            + "."
        )
    if estimate > longest:
        issues.append(
            f"The plan runs about {estimate:.0f} s, past the {longest:.0f} s ceiling. Leave "
            "out a weaker fact rather than rushing the rest."
        )
    return issues


# Roles trimmed, in this order, when the story runs long: colour goes entirely, then the
# others shrink to the bottom of their band. The spine is never trimmed.
TRIM_ORDER: tuple[StoryRole, ...] = ("colour", "supporting_evidence", "essential_context")


def allot_words(
    brief: EditorialBrief,
    claims: dict[str, ClaimWeight],
    weights: StoryWeights,
    voice: VoiceSpec,
    longest_seconds: float,
) -> EditorialBrief:
    """Give each beat the words its claims' story roles and weights deserve."""
    plans = {plan.claim_id: plan for plan in brief.claims if plan.story_role != "expendable"}
    supporters: dict[str, int] = {}
    for plan in plans.values():
        if plan.supports_claim:
            supporters[plan.supports_claim] = supporters.get(plan.supports_claim, 0) + 1
    most = max(supporters.values(), default=0)
    seconds: dict[str, float] = {}
    for claim_id, plan in plans.items():
        low, high = weights.role_seconds[plan.story_role]
        score = claims[claim_id].score if claim_id in claims else 0.5
        centrality = supporters.get(claim_id, 0) / most if most else 0.0
        seconds[claim_id] = low + (high - low) * (score + centrality) / 2
    owner: dict[str, str] = {}
    for beat in brief.arc:
        for claim_id in beat.claim_ids:
            owner.setdefault(claim_id, beat.phase_id)

    def beat_seconds() -> list[float]:
        return [
            max(
                weights.beat_floor_seconds,
                weights.transition_seconds
                + sum(
                    seconds[c]
                    for c, phase in owner.items()
                    if phase == beat.phase_id and c in seconds
                ),
            )
            for beat in brief.arc
        ]

    for role in TRIM_ORDER:
        if story_seconds(beat_seconds(), voice) <= longest_seconds:
            break
        floor = 0.0 if role == "colour" else weights.role_seconds[role][0]
        for claim_id, plan in plans.items():
            if plan.story_role == role:
                seconds[claim_id] = floor
    arc = [
        beat.model_copy(update={"words": _words_for(time, voice, hook=index == 0)})
        for index, (beat, time) in enumerate(zip(brief.arc, beat_seconds(), strict=True))
    ]
    return brief.model_copy(update={"arc": arc})


def _words_for(seconds: float, voice: VoiceSpec, *, hook: bool) -> int:
    """The words that fill `seconds` at the voice's rate: the inverse of `spoken_seconds`."""
    return max(round(seconds / spoken_seconds(1, voice, hook=hook)), 1)


def tell_beats(
    brief: EditorialBrief, claims: dict[str, ClaimWeight], weights: StoryWeights
) -> EditorialBrief:
    """Set how each beat is told from its strongest claim; its words stay the planner's."""
    return brief.model_copy(
        update={
            "arc": [
                beat.model_copy(update={"telling": _telling(beat, claims, weights)})
                for beat in brief.arc
            ]
        }
    )


def turn_issues(
    brief: EditorialBrief, claims: dict[str, ClaimWeight], weights: StoryWeights
) -> list[str]:
    """The strongest beat after the hook should start around the music's peak."""
    beats = brief.arc
    if len(beats) < 3:
        return []
    scores = [_beat_score(beat, claims) for beat in beats]
    turn = max(range(1, len(beats)), key=lambda index: scores[index])
    total = sum(beat.words for beat in beats) or 1
    start = sum(beat.words for beat in beats[:turn]) / total
    low, high = weights.turn_window
    if low <= start <= high:
        return []
    return [
        f"The strongest beat after the hook, {beats[turn].phase_id}, starts {start:.0%} of the "
        f"way in; it lands best between {low:.0%} and {high:.0%}, where the music peaks."
    ]


def hook_issues(
    brief: EditorialBrief, claims: dict[str, ClaimWeight], weights: StoryWeights
) -> list[str]:
    """The hook should be the verified claim that matters most and ties everything together."""
    candidates = [c for c in claims.values() if c.evidence >= weights.assert_from]
    if not candidates or brief.hook_claim_id is None:
        return []
    best = max(candidates, key=lambda claim: claim.worth * claim.connection)
    chosen = claims.get(brief.hook_claim_id)
    if chosen is None or best.claim_id == chosen.claim_id:
        return []
    if best.worth * best.connection <= chosen.worth * chosen.connection + 0.1:
        return []
    return [
        f"The weights suggest {best.claim_id} as the hook (worth {best.worth:.2f} × connection "
        f"{best.connection:.2f}) over {chosen.claim_id} ({chosen.worth:.2f} × "
        f"{chosen.connection:.2f})."
    ]


def _beat_score(beat: ArcPhase, claims: dict[str, ClaimWeight]) -> float:
    return max((claims[c].score for c in beat.claim_ids if c in claims), default=0.0)


def _telling(beat: ArcPhase, claims: dict[str, ClaimWeight], weights: StoryWeights) -> Telling:
    measured = [claims[c] for c in beat.claim_ids if c in claims]
    if not measured:
        return beat.telling
    strongest = max(measured, key=lambda claim: claim.score)
    if strongest.evidence < weights.attribute_from:
        return "curiosity"
    return "feeling" if strongest.worth >= weights.feeling_from else "logic"


def _expected_level(judgement: Judgement) -> float:
    answer = judgement.answer
    if answer.probabilities:
        return sum(int(level) * p for level, p in answer.probabilities.items())
    return answer.score or 0.0
