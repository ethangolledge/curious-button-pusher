from pathlib import Path

import pytest

from content.schemas.judgement import Answer, Judgement
from content.schemas.plan import ArcPhase, ClaimPlan, EditorialBrief
from content.schemas.research import ResearchClaim, ResearchPack
from content.schemas.story import StoryRole
from content.story.weights import (
    allot_words,
    claim_weights,
    evidence,
    hook_issues,
    selection_issues,
    stance,
    strongest,
    tell_beats,
    turn_issues,
)
from content.theme import load_theme
from content.workflow.demo import _brief_response, _research_response

_SPEC = load_theme(Path(__file__).parents[1] / "themes/starter").spec
WEIGHTS = _SPEC.writing.weights


def test_evidence_follows_the_research_and_sets_how_firmly_to_state_it() -> None:
    research = _research(
        verified=[_claim("C1", 2), _claim("C2", 1)],
        reported=[_claim("C3", 2)],
        disputed=[_claim("C4", 2)],
    )

    grounded = evidence(research, WEIGHTS)

    assert grounded == {"C1": 1.0, "C2": 0.9, "C3": 0.7, "C4": 0.4}
    assert [stance(grounded[c], WEIGHTS) for c in ("C1", "C3", "C4")] == [
        "assert",
        "attribute",
        "ask",
    ]


def test_a_claim_scores_by_worth_connection_and_evidence() -> None:
    research = _research(verified=[_claim("C1", 2)], disputed=[_claim("C2", 2)])
    judged = [*_measured("C1", worth=2, connection=2), *_measured("C2", worth=2, connection=2)]

    claims = claim_weights(research, judged, WEIGHTS)

    assert claims["C1"].score == pytest.approx(1.0)
    # Strong story, weak evidence: scaled down, and only ever asked about.
    assert claims["C2"].score == pytest.approx(0.4 / WEIGHTS.full_evidence, abs=0.001)


def test_the_strongest_facts_are_found_where_the_scores_naturally_break() -> None:
    research = _research(verified=[_claim(f"C{i}", 2) for i in range(1, 6)])
    judged = [
        *_measured("C1", worth=2, connection=2),
        *_measured("C2", worth=2, connection=2),
        *_measured("C3", worth=2, connection=1),
        *_measured("C4", worth=1, connection=1),
        *_measured("C5", worth=1, connection=1),
    ]
    claims = claim_weights(research, judged, WEIGHTS)

    # Scores 1, 1, 0.5, 0.25, 0.25: the least spread within each side splits after C2.
    assert strongest(claims) == {"C1", "C2"}


def test_the_weights_advise_on_the_facts_but_never_resize_the_plan() -> None:
    research = _research(verified=[_claim(f"C{i}", 2) for i in range(1, 5)])
    judged = [
        *_measured("C1", worth=2, connection=2),
        *_measured("C2", worth=2, connection=2),
        *_measured("C3", worth=1, connection=1),
        *_measured("C4", worth=1, connection=1),
    ]
    claims = claim_weights(research, judged, WEIGHTS)
    brief = _brief([("P1", ["C1"], 40), ("P2", ["C3"], 90), ("P3", ["C4"], 60)])

    told = tell_beats(brief, claims, WEIGHTS)
    weak, missing, long = selection_issues(told, claims, estimate=200, longest=170)

    assert [beat.words for beat in told.arc] == [40, 90, 60]
    assert [beat.telling for beat in told.arc] == ["feeling", "logic", "logic"]
    assert weak.startswith("Weaker than the story's strongest facts: C3 (0.25), C4 (0.25)")
    assert missing == "Among the strongest facts but not told: C2 (1.00)."
    assert "rather than rushing the rest" in long
    assert (
        selection_issues(
            _brief([("P1", ["C1"], 40), ("P2", ["C2"], 90)]), claims, estimate=60, longest=170
        )
        == []
    )


def test_the_turn_should_land_where_the_music_peaks_and_the_hook_should_matter_most() -> None:
    research = _research(verified=[_claim("C1", 2), _claim("C2", 2), _claim("C3", 2)])
    judged = [
        *_measured("C1", worth=1, connection=1),
        *_measured("C2", worth=2, connection=2),
        *_measured("C3", worth=1, connection=1),
    ]
    claims = claim_weights(research, judged, WEIGHTS)
    early = _brief([("P1", ["C1"], 10), ("P2", ["C2"], 30), ("P3", ["C3"], 60)])
    well_placed = _brief([("P1", ["C1"], 30), ("P2", ["C3"], 30), ("P3", ["C2"], 40)])

    assert "P2, starts 10% of the way in" in turn_issues(early, claims, WEIGHTS)[0]
    assert turn_issues(well_placed, claims, WEIGHTS) == []
    (hook,) = hook_issues(early, claims, WEIGHTS)
    assert hook.startswith("The weights suggest C2 as the hook")


def _research(**buckets: list[ResearchClaim]) -> ResearchPack:
    base = ResearchPack.model_validate(_research_response("The Great Stink", []))
    names = {
        "verified": "verified_facts",
        "reported": "reported_claims",
        "disputed": "disputed_claims",
    }
    empty = ("verified_facts", "reported_claims", "disputed_claims", "inferences")
    update: dict[str, list[ResearchClaim]] = {f: [] for f in (*empty, "unsupported_claims")}
    update |= {names[kind]: claims for kind, claims in buckets.items()}
    return base.model_copy(update=update)


def _claim(claim_id: str, sources: int) -> ResearchClaim:
    return ResearchClaim(
        claim_id=claim_id, claim=f"Claim {claim_id}.", source_ids=[f"W{i}" for i in range(sources)]
    )


def _brief(beats: list[tuple[str, list[str], int]]) -> EditorialBrief:
    base = EditorialBrief.model_validate(_brief_response("The Great Stink"))
    arc = [
        ArcPhase(
            phase_id=phase,
            role="explain",
            audience_feeling="curious",
            narrative_job="Tell it.",
            audience_knows_after="It.",
            question_answered="",
            next_question="",
            next_reveal="",
            leads_to_next="",
            tension="build",
            claim_ids=claims,
            words=words,
        )
        for phase, claims, words in beats
    ]
    return base.model_copy(update={"arc": arc, "hook_claim_id": beats[0][1][0]})


def _measured(claim_id: str, *, worth: int, connection: int) -> list[Judgement]:
    return [
        Judgement(
            stage="plan",
            revision=0,
            target_id=claim_id,
            question_id=question,
            answer=Answer(kind="score", score=float(level), probabilities={str(level): 1.0}),
            expected=None,
            outcome="pass",
            blocking=False,
            model="jev",
        )
        for question, level in (("claim_worth", worth), ("claim_connection", connection))
    ]


def test_time_follows_each_claims_story_role() -> None:
    brief = _ledger(
        [
            ("P1", "C1", "spine", None),
            ("P2", "C2", "essential_context", None),
            ("P3", "C3", "supporting_evidence", "C1"),
            ("P4", "C4", "colour", None),
        ]
    )

    words = [beat.words for beat in allot_words(brief, {}, WEIGHTS, _SPEC.voice, 1000).arc]

    # The spine slows down and explains; a bridge of colour passes quickly.
    assert words[0] > words[1] > words[2] > words[3]


def test_a_central_claim_gets_more_time_within_its_band() -> None:
    brief = _ledger(
        [
            ("P1", "C1", "spine", None),
            ("P2", "C2", "spine", None),
            ("P3", "C3", "supporting_evidence", "C2"),
            ("P4", "C4", "supporting_evidence", "C2"),
        ]
    )

    words = [beat.words for beat in allot_words(brief, {}, WEIGHTS, _SPEC.voice, 1000).arc]

    # Two claims rest on C2, none on C1. (P1 is spoken at the slower hook pace, so compare
    # in seconds rather than words.)
    seconds_per_word, hook_seconds_per_word = 60 / 160, 60 / (160 * 0.92)
    assert words[1] * seconds_per_word > words[0] * hook_seconds_per_word


def test_a_long_story_loses_colour_first_and_never_squeezes_the_spine() -> None:
    brief = _ledger(
        [
            ("P1", "C1", "spine", None),
            ("P2", "C2", "colour", None),
            ("P2", "C4", "essential_context", None),
            ("P3", "C3", "supporting_evidence", "C1"),
        ]
    )
    roomy = allot_words(brief, {}, WEIGHTS, _SPEC.voice, 1000).arc

    tight = allot_words(brief, {}, WEIGHTS, _SPEC.voice, 25).arc

    assert tight[0].words == roomy[0].words
    assert tight[1].words < roomy[1].words
    assert tight[2].words <= roomy[2].words


def _ledger(beats: list[tuple[str, str, StoryRole, str | None]]) -> EditorialBrief:
    phases = list(dict.fromkeys(phase for phase, _, _, _ in beats))
    brief = _brief([(phase, [c for p, c, _, _ in beats if p == phase], 0) for phase in phases])
    claims = [
        ClaimPlan(
            claim_id=claim_id,
            story_role=role,
            narrative_job="It matters.",
            meaning="What it shows.",
            requires_explanation=False,
            supports_claim=supports,
        )
        for _, claim_id, role, supports in beats
    ]
    return brief.model_copy(update={"claims": claims})
