from content.agents.fact_checker.agent import decide_route
from content.agents.script_writer.agent import ScriptWriter
from content.agents.visual_director.agent import VisualDirector
from content.schemas.fact_check import FactCheckReport
from content.schemas.research import ResearchPack
from content.schemas.script import ScriptPackage
from content.schemas.visuals import VisualPackage


def test_source_assessment_is_embedded_in_each_source_reference() -> None:
    research = _research_pack()
    schema = ResearchPack.model_json_schema()
    source_schema = schema["$defs"]["SourceReference"]

    assert len(research.source_references) == 2
    assert research.source_references[0].credibility_notes == "Direct record."
    assert {"source_type", "credibility_notes"}.issubset(source_schema["required"])
    assert "source_assessments" not in schema["properties"]


def test_unknown_research_links_warn_without_discarding_output() -> None:
    research = _research_pack(unknown_source=True)

    assert any(
        "Research references unknown source IDs: W-missing." in warning
        for warning in research.integrity_warnings
    )


def test_script_unit_identifiers_are_normalized_without_rejecting_output() -> None:
    generated = _script_package(noncanonical=True)

    normalized, warnings = ScriptWriter._normalize_units(generated)

    assert [unit.unit_id for unit in normalized.script_units] == ["U1", "U2"]
    assert [unit.order for unit in normalized.script_units] == [1, 2]
    assert normalized.script_units[0].narrative_function == "hook"
    assert warnings


def test_fact_check_route_follows_the_findings() -> None:
    report = FactCheckReport.model_validate(
        {
            "claim_findings": [
                {
                    "claim": "Claim one",
                    "claim_id": "C1",
                    "script_unit_ids": ["U1"],
                    "source_ids": ["W1"],
                    "status": "exaggerated",
                    "issue": "The wording is broader than the source.",
                    "required_qualification": "That the source reports it.",
                    "severity": "major",
                }
            ],
            "non_factual_unit_ids": ["U2"],
            "routing_result": "verified",
        }
    )

    routed, advisory = decide_route(report)
    assert routed.routing_result == "revise_script"
    assert advisory == []

    context_only = report.model_copy(
        update={
            "claim_findings": [
                report.claim_findings[0].model_copy(update={"status": "missing_context"})
            ],
            "routing_result": "revise_script",
        }
    )
    routed, advisory = decide_route(context_only)
    assert routed.routing_result == "verified"
    assert advisory == ["Context note: Claim one: The wording is broader than the source."]


def test_scene_identifiers_are_normalized_without_rejecting_output() -> None:
    anchor = {
        "subject": "a cipher machine",
        "setting": "a dark office",
        "composition": "close",
        "key_elements": ["rotors"],
        "light_and_colour": "teal glow",
    }
    generated = VisualPackage.model_validate(
        {
            "overall_visual_direction": "Direction",
            "scenes": [
                {
                    "scene_id": "duplicate",
                    "script_unit_ids": ["U1", "U1", "U2"],
                    "purpose": "Purpose",
                    "visual_function": "show",
                    "evidence_presentation": "symbolic",
                    "anchor": anchor,
                    "camera": "push_in",
                    "motion": "rotors turn",
                    "morph_bridge": "the rotor spiral",
                }
            ],
            "continuity_notes": [],
        }
    )

    normalized, warnings = VisualDirector._normalize_scenes(generated)

    assert normalized.scenes[0].scene_id == "S1"
    assert normalized.scenes[0].script_unit_ids == ["U1", "U2"]
    assert warnings


def _research_pack(*, unknown_source: bool = False) -> ResearchPack:
    return ResearchPack.model_validate(
        {
            "research_summary": "Summary",
            "timeline": [
                {
                    "date_or_period": "Period",
                    "event": "Event",
                    "claim_ids": ["C1"],
                }
            ],
            "verified_facts": [
                {
                    "claim_id": "C1",
                    "claim": "Claim one",
                    "source_ids": ["W1", "W-missing"] if unknown_source else ["W1"],
                    "qualification": None,
                }
            ],
            "reported_claims": [],
            "disputed_claims": [],
            "inferences": [],
            "unsupported_claims": [],
            "source_references": [
                {
                    "source_id": "W1",
                    "title": "Primary source",
                    "url": "https://example.com/primary",
                    "source_type": "primary",
                    "credibility_notes": "Direct record.",
                    "limitations": [],
                },
                {
                    "source_id": "W2",
                    "title": "Context source",
                    "url": "https://example.com/context",
                    "source_type": "quality_secondary",
                    "credibility_notes": "Useful context.",
                    "limitations": ["Does not establish the central claim."],
                },
            ],
            "source_comparisons": [],
            "contradictions": [],
            "missing_evidence": [],
            "factual_limitations": [],
            "safe_wording": [],
            "research_confidence": "high",
            "evidence_status": "source_backed",
            "research_status": "sufficient",
        }
    )


def _script_package(*, noncanonical: bool = False) -> ScriptPackage:
    return ScriptPackage.model_validate(
        {
            "title": "Title",
            "script_units": [
                {
                    "unit_id": "duplicate" if noncanonical else "U1",
                    "order": 7 if noncanonical else 1,
                    "narrative_function": "context" if noncanonical else "hook",
                    "arc_phase_id": "P1",
                    "transition_intent": "build",
                    "text": "Opening.",
                    "claim_ids": ["C1"],
                },
                {
                    "unit_id": "duplicate" if noncanonical else "U2",
                    "order": 9 if noncanonical else 2,
                    "narrative_function": "ending",
                    "arc_phase_id": "P2",
                    "transition_intent": "release",
                    "text": "Ending.",
                    "claim_ids": [],
                },
            ],
            "intended_takeaway": "Takeaway",
            "voice_direction": {
                "tone": "Measured",
                "pace": "Steady",
                "delivery": "Continuous",
                "pronunciation_notes": [],
            },
        }
    )
