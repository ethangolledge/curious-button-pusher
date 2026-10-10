"""The deterministic demo story: the answers every agent and Jev give in the offline
configurations and the tests, so the whole pipeline runs without a key."""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from content.judging.questions import QUESTIONS
from content.providers.fake import FakeDecisionProvider, FakeModelProvider, ResponseValue
from content.schemas.audience import AudienceReport, StoryDecisions
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Critique
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.script import LineEditPackage, ScriptPackage
from content.schemas.visuals import VisualPackage

# How each demo unit enters from the one before it; the fake Jev hears the same.
DEMO_TRANSITIONS = {"U2": "build", "U3": "turn", "U4": "hold", "U5": "build", "U6": "release"}


def create_demo_provider() -> FakeModelProvider:
    return FakeModelProvider(default_factory=demo_response)


def create_demo_decision_provider() -> FakeDecisionProvider:
    return FakeDecisionProvider(demo_answer)


def demo_answer(question_id: str, state: Mapping[str, Any]) -> dict[str, Any]:
    """A confident, passing System 1 answer for every question."""
    question = QUESTIONS[question_id]
    if question.kind == "noul":
        return {"kind": "noul", "noul": 0.95}
    if question.kind == "score":
        return {
            "kind": "score",
            "score": 1.95,
            "confidence": 0.93,
            "probabilities": {"0": 0.0, "1": 0.05, "2": 0.95},
        }
    if question_id == "transition_tension":
        choice = DEMO_TRANSITIONS[state["unit"]["unit_id"]]
    else:
        choice = next(key for key in question.criteria if key not in question.failing_choices)
    return {"kind": "choice", "choice": choice, "confidence": 0.9, "probabilities": {choice: 0.93}}


def demo_response(input_text: str, output_type: type[BaseModel]) -> ResponseValue:
    payload: dict[str, Any] = json.loads(input_text)
    if output_type is Critique:
        return {"verdict": "accept", "corrections": [], "reasoning": "Deterministic demo."}
    if output_type is AudienceReport:
        return _listener_response(str(payload["narration"]))
    if output_type is StoryDecisions:
        return {"decisions": [], "reasoning": "Deterministic demo."}
    if output_type is LineEditPackage:
        # A line edit keeps each named line's words: the demo shows the scope, not the prose.
        return {
            "lines": [
                {"unit_id": line["unit_id"], "text": line["text"]} for line in payload["lines"]
            ]
        }
    topic = str(payload["topic"])
    if output_type is ResearchPack:
        return _research_response(topic, payload.get("source_material", []))
    if output_type is EditorialBrief:
        return _brief_response(topic)
    if output_type is ScriptPackage:
        return _script_response(topic)
    if output_type is FactCheckReport:
        return _fact_check_response(topic)
    if output_type is VisualPackage:
        return _visual_response(topic)
    raise LookupError(f"No deterministic demo response for {output_type.__name__}")


def _research_response(topic: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    claim = f"The available material discusses {topic}."
    source_ids = [str(source["source_id"]) for source in sources]
    source_references = [
        {
            "source_id": source["source_id"],
            "title": source["title"],
            "url": source.get("url"),
            "source_type": "other",
            "credibility_notes": "Supplied material retained for deterministic demonstration.",
            "limitations": ["No independent source assessment was performed."],
        }
        for source in sources
    ]
    return {
        "research_summary": (
            f"The deterministic provider records a limited evidence foundation for {topic}. "
            "It demonstrates structure rather than real research quality."
        ),
        "timeline": [
            {
                "date_or_period": "Demo run",
                "event": "The supplied topic was organised into a research handoff.",
                "claim_ids": ["C1"],
            }
        ],
        "verified_facts": [
            {
                "claim_id": "C1",
                "claim": claim,
                "source_ids": source_ids,
                "qualification": (
                    "This establishes only what the supplied material discusses."
                    if sources
                    else "No external evidence was supplied or independently discovered."
                ),
            }
        ],
        "reported_claims": [],
        "disputed_claims": [],
        "inferences": [],
        "unsupported_claims": [],
        "source_references": source_references,
        "source_comparisons": [],
        "contradictions": [],
        "missing_evidence": ["Independent corroboration has not been performed."],
        "factual_limitations": ["The deterministic provider does not perform web research."],
        "safe_wording": [
            "Describe the material as a starting point rather than independent confirmation."
        ],
        "research_confidence": "medium" if sources else "low",
        "evidence_status": "source_backed" if sources else "provisional",
        "research_status": "sufficient",
    }


def _brief_response(topic: str) -> dict[str, Any]:
    return {
        "central_question": f"What can we actually establish about {topic}?",
        "promise": "A clear line between what the evidence shows and what it cannot.",
        "hook_claim_id": "C1",
        "orientation": f"This is about {topic}, and what the record can and cannot show.",
        "audience_starts_knowing": "Only that the account exists.",
        "story_chain": [
            f"An account of {topic} spread.",
            "The record supports less than the account claims.",
            "So the honest story is where the evidence stops.",
        ],
        "arc": [
            {
                "phase_id": "P1",
                "audience_feeling": "curious",
                "role": "hook",
                "narrative_job": "Pose the evidential question: the account is widely believed.",
                "audience_knows_after": "That an account is widely believed.",
                "question_answered": "",
                "next_question": "What does the record actually show?",
                "next_reveal": "The evidence itself.",
                "leads_to_next": "So we check what the record supports.",
                "tension": "build",
                "link": "setup",
                "claim_ids": ["C1"],
            },
            {
                "phase_id": "P2",
                "audience_feeling": "unsettled",
                "role": "reveal",
                "narrative_job": (
                    "Show that the premise outruns the evidence: what people repeat is more "
                    "than what is known."
                ),
                "audience_knows_after": "The record supports less than the account claims.",
                "question_answered": "What does the record actually show?",
                "next_question": "Why does the difference matter?",
                "next_reveal": "What can fairly be concluded.",
                "leads_to_next": "That gap is the real story.",
                "tension": "build",
                "link": "but",
                "claim_ids": ["C1"],
            },
            {
                "phase_id": "P3",
                "audience_feeling": "clear-eyed",
                "role": "resolve",
                "narrative_job": (
                    "Resolve with why the distinction matters: it changes what can fairly be "
                    "concluded."
                ),
                "audience_knows_after": "What can fairly be concluded, and what cannot.",
                "question_answered": "Why does the difference matter?",
                "next_question": "What remains unknown?",
                "next_reveal": "",
                "leads_to_next": "The listener is left with what is still unknown.",
                "tension": "release",
                "link": "therefore",
                "claim_ids": ["C1"],
            },
        ],
        "claims": [
            {
                "claim_id": "C1",
                "story_role": "spine",
                "narrative_job": "It is the account the whole story tests.",
                "meaning": "The material discusses the topic; it does not establish it.",
                "requires_explanation": True,
            }
        ],
        "explain": [
            {
                "term": "the record",
                "plain": "what the supplied sources actually document",
                "claim_ids": ["C1"],
            }
        ],
        "left_out": [
            {
                "what": "Who first circulated the account",
                "why": "It changes nothing we can establish.",
            }
        ],
        "style_boundaries": ["No speculation presented as fact."],
        "central_angle": f"What can responsibly be established about {topic}",
        "intended_audience": "General viewers interested in consequential events",
        "intended_takeaway": "Evidence limits are part of an honest story.",
        "story_assignment": [
            "Build one connected narration around what the evidence can establish."
        ],
        "fact_check_priorities": ["Confirm that the evidence limitation remains explicit."],
        "visual_principles": [
            "Use a small number of evidence-led visual ideas without fabricated artifacts."
        ],
        "tone": "restrained and investigative",
        "narrative_direction": (
            "Open with the evidential question, explain the limitation, and end on why "
            "that distinction matters."
        ),
        "required_context": ["This deterministic run performs no live research."],
        "editorial_risks": ["The topic premise may be mistaken for a verified conclusion."],
    }


def _script_response(topic: str) -> dict[str, Any]:
    return {
        "title": f"The evidence behind: {topic}",
        "script_units": [
            {
                "unit_id": "U1",
                "order": 1,
                "narrative_function": "hook",
                "arc_phase_id": "P1",
                "transition_intent": "build",
                "text": "One source says it happened. Nobody has checked it.",
                "claim_ids": ["C1"],
            },
            {
                "unit_id": "U2",
                "order": 2,
                "narrative_function": "orient",
                "arc_phase_id": "P2",
                "transition_intent": "build",
                "text": (
                    "This is about what the public record really shows, and what it still cannot."
                ),
                "claim_ids": ["C1"],
            },
            {
                "unit_id": "U3",
                "order": 3,
                "narrative_function": "consequence",
                "arc_phase_id": "P2",
                "transition_intent": "turn",
                "text": (
                    "That distinction changes which claims can be stated as fact. The rest "
                    "must stay attributed to whoever first said them publicly, and to exactly "
                    "when they said it."
                ),
                "claim_ids": ["C1"],
            },
            {
                "unit_id": "U4",
                "order": 4,
                "narrative_function": "context",
                "arc_phase_id": "P2",
                "transition_intent": "hold",
                "text": (
                    "Some details are documented in more than one place. Others rest on a "
                    "single, unconfirmed account from one source that nobody else has ever "
                    "checked properly."
                ),
                "claim_ids": ["C1"],
            },
            {
                "unit_id": "U5",
                "order": 5,
                "narrative_function": "consequence",
                "arc_phase_id": "P3",
                "transition_intent": "build",
                "text": (
                    "A careful story keeps those two kinds of detail apart, even when it "
                    "costs drama, attention and clicks. It usually does, and it is worth it."
                ),
                "claim_ids": ["C1"],
            },
            {
                "unit_id": "U6",
                "order": 6,
                "narrative_function": "ending",
                "arc_phase_id": "P3",
                "transition_intent": "release",
                "text": (
                    "The honest story is defined by both the evidence and all of its limits. "
                    "It says so out loud, every single time it is told."
                ),
                "claim_ids": ["C1"],
            },
        ],
        "intended_takeaway": "Evidence labels matter as much as an arresting premise.",
        "voice_direction": {
            "tone": "measured and curious",
            "pace": "steady, with space around qualifications",
            "delivery": "one continuous, restrained documentary reading",
            "pronunciation_notes": [],
        },
    }


def _fact_check_response(topic: str) -> dict[str, Any]:
    return {
        "claim_findings": [
            {
                "claim": f"The available material discusses {topic}.",
                "claim_id": "C1",
                "script_unit_ids": ["U1", "U2", "U3", "U4", "U5", "U6"],
                "source_ids": [],
                "status": "passed",
                "issue": "The script preserves the deterministic research limitation.",
            }
        ],
        "non_factual_unit_ids": [],
        "routing_result": "verified",
    }


def _listener_response(narration: str) -> dict[str, Any]:
    """A first-time listener who followed every step of the demo story."""
    return {
        "about": "What the record can and cannot establish about an account.",
        "what_happened": narration.split(".")[0],
        "why_it_happened": "The account outran its evidence.",
        "why_it_matters": "It changes what can fairly be concluded.",
        "key_facts": ["The record supports less than the account claims."],
        "question": "What can we actually establish?",
        "unresolved": "What the record cannot show.",
        "confusions": [],
        "unrelated_facts": [],
        "unclear_terms": [],
        "lost_thread_at": None,
    }


def _visual_response(topic: str) -> dict[str, Any]:
    return {
        "overall_visual_direction": (
            "One dreamlike evidence room: a glowing source card dissolves into a ledger, and "
            "the ledger into a quiet horizon."
        ),
        "scenes": [
            {
                "scene_id": "S1",
                "script_unit_ids": ["U1"],
                "purpose": "Open on the evidential question.",
                "visual_function": "make_it_felt",
                "evidence_presentation": "symbolic",
                "anchor": {
                    "subject": "a single glowing index card",
                    "setting": "a dark, empty archive",
                    "composition": "centred, close, shallow depth of field",
                    "key_elements": ["teal glow", "floating dust"],
                    "light_and_colour": "void black with a teal rim light",
                },
                "camera": "push_in",
                "motion": "dust drifts slowly through the light",
                "morph_bridge": "the card's ruled lines",
                "reference_ids": ["R2"],
            },
            {
                "scene_id": "S2",
                "script_unit_ids": ["U2"],
                "purpose": f"Show that the material about {topic} is a starting point.",
                "visual_function": "explain",
                "evidence_presentation": "symbolic",
                "anchor": {
                    "subject": "an endless ledger of ruled lines",
                    "setting": "the same archive, opened out",
                    "composition": "wide, symmetrical, lines receding to a vanishing point",
                    "key_elements": ["ruled lines", "teal glow"],
                    "light_and_colour": "dark red shadows with teal highlights",
                },
                "camera": "dolly",
                "motion": "the lines glow one by one",
                "morph_bridge": "the ruled lines thinning into threads",
                "reference_ids": ["R1"],
            },
            {
                "scene_id": "S3",
                "script_unit_ids": ["U3"],
                "purpose": "Show which claims can stand as fact.",
                "visual_function": "explain",
                "evidence_presentation": "symbolic",
                "anchor": {
                    "subject": "glowing threads, some bright and some fading",
                    "setting": "the same dark archive",
                    "composition": "wide, threads crossing the frame diagonally",
                    "key_elements": ["teal threads", "fading threads"],
                    "light_and_colour": "dark red shadow with teal highlights",
                },
                "camera": "drift",
                "motion": "the faint threads dissolve while the bright ones hold",
                "morph_bridge": "the brightest thread becoming a horizon",
            },
            {
                "scene_id": "S4",
                "script_unit_ids": ["U4"],
                "purpose": "Separate corroborated details from single accounts.",
                "visual_function": "explain",
                "evidence_presentation": "symbolic",
                "anchor": {
                    "subject": "two bright threads beside one faint thread",
                    "setting": "the same dark archive",
                    "composition": "wide, threads running parallel across the frame",
                    "key_elements": ["teal threads", "one fading thread"],
                    "light_and_colour": "dark red shadow with teal highlights",
                },
                "camera": "drift",
                "motion": "the faint thread flickers while the pair holds steady",
                "morph_bridge": "the threads parting into two separate strands",
            },
            {
                "scene_id": "S5",
                "script_unit_ids": ["U5"],
                "purpose": "Keep the two kinds of detail apart.",
                "visual_function": "explain",
                "evidence_presentation": "symbolic",
                "anchor": {
                    "subject": "two strands of light held apart",
                    "setting": "the same dark archive, opening onto water",
                    "composition": "wide, one strand above the other",
                    "key_elements": ["teal strands", "dark gap between them"],
                    "light_and_colour": "deep blue-black with teal light",
                },
                "camera": "dolly",
                "motion": "the gap between the strands widens slowly",
                "morph_bridge": "the lower strand flattening into a horizon",
            },
            {
                "scene_id": "S6",
                "script_unit_ids": ["U6"],
                "purpose": "Resolve on why the limits matter.",
                "visual_function": "make_it_felt",
                "evidence_presentation": "symbolic",
                "anchor": {
                    "subject": "a thin teal horizon",
                    "setting": "a calm dark sea",
                    "composition": "wide, horizon on the lower third",
                    "key_elements": ["teal horizon", "still water"],
                    "light_and_colour": "deep blue-black with a teal line of light",
                },
                "camera": "pull_out",
                "motion": "the water barely moves",
                "morph_bridge": "the horizon settles into darkness",
            },
        ],
        "continuity_notes": ["The teal glow carries through every scene."],
        "references": [
            {
                "ref_id": "R2",
                "kind": "object",
                "query": "archive index card",
                "unit_ids": ["U1"],
                "purpose": "The single unchecked record the story starts from.",
            },
            {
                "ref_id": "R1",
                "kind": "place",
                "query": "national archives reading room",
                "unit_ids": ["U2"],
                "purpose": "Where the material behind the story is kept.",
            },
        ],
    }
