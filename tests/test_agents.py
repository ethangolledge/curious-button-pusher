from collections.abc import Callable
from dataclasses import replace
from typing import TypedDict, cast

from content.agents.editorial_director.agent import EditorialDirector
from content.agents.editorial_director.critic import Critic
from content.agents.fact_checker.agent import FactChecker
from content.agents.fact_researcher.agent import FactResearcher
from content.agents.script_writer.agent import ScriptWriter, _selected_evidence
from content.agents.visual_director.agent import VisualDirector
from content.config import AgentConfig, ContentConfig
from content.judging.judge import Judge
from content.models import ModelRegistry
from content.providers.base import ModelProvider
from content.providers.fake import FakeModelProvider
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Critique
from content.schemas.plan import EditorialBrief, Explanation
from content.schemas.research import ResearchPack
from content.state import ContentState
from content.story.ledger import script_tasks
from content.story.notes import split_notes
from content.story.pace import passages
from content.workflow.demo import (
    create_demo_decision_provider,
    create_demo_provider,
    demo_response,
)
from content.workflow.director_notes import apply_director_notes
from content.workflow.run import create_initial_state


def test_topic_string_creates_fresh_initial_state(app_config: ContentConfig) -> None:
    first = create_initial_state(
        "  Example topic  ",
        source_material=None,
        user_instructions=None,
        config=app_config,
    )
    second = create_initial_state(
        "Another topic",
        source_material=None,
        user_instructions=None,
        config=app_config,
    )

    assert first["topic"] == "Example topic"
    assert first["source_material"] == []
    assert first["source_material"] is not second["source_material"]


def test_each_agent_returns_its_expected_structured_update(
    app_config: ContentConfig,
) -> None:
    provider = create_demo_provider()
    state = cast(
        ContentState,
        create_initial_state(
            "Example topic",
            source_material=None,
            user_instructions=None,
            config=app_config,
        ),
    )
    researcher = FactResearcher(**_node_args("fact_researcher", app_config, provider))
    editorial = EditorialDirector(**_node_args("editorial_director", app_config, provider))
    writer = ScriptWriter(**_node_args("script_writer", app_config, provider))
    checker = FactChecker(**_node_args("fact_checker", app_config, provider))
    visual = VisualDirector(**_node_args("visual_director", app_config, provider))

    operations: list[tuple[Callable[[ContentState], ContentState], str]] = [
        (researcher, "research_pack"),
        (editorial.create_plan, "editorial_brief"),
        (writer, "script_package"),
        (checker, "fact_check_report"),
        (visual, "visual_package"),
    ]
    # Advice about an earlier script version must not survive into the next one.
    state["script_warnings"] = ["The narration is predicted to run 189 s."]
    for operation, expected_key in operations:
        update = operation(state)
        if operation is writer:
            assert update["script_warnings"] == []
        assert update[expected_key] is not None  # type: ignore[literal-required]
        assert "topic" not in update
        assert len(update["call_log"]) == 1
        state.update(update)

    assert [call.output_type.__name__ for call in provider.calls] == [
        "ResearchPack",
        "EditorialBrief",
        "ScriptPackage",
        "FactCheckReport",
        "VisualPackage",
    ]
    assert [call.web_search for call in provider.calls] == [True, False, False, False, False]
    assert all("# Role" in call.instructions for call in provider.calls)


def test_editorial_director_judges_one_story_node_in_one_batch(
    app_config: ContentConfig,
) -> None:
    decisions = create_demo_decision_provider()
    state = _state_through_script(app_config)
    script, brief, research = (
        state["script_package"],
        state["editorial_brief"],
        state["research_pack"],
    )
    assert script is not None and brief is not None and research is not None
    unit_task = next(
        task for task in script_tasks(script, brief, research, 0) if task["target"] == "unit"
    )

    update = Judge(decisions, app_config.decisions).judge(unit_task)

    unit_questions = (
        "unit_pace",
        "unit_supported",
        "unit_plain",
        "unit_clear",
        "unit_meaning",
        "unit_spoken",
        "unit_new",
        "unit_reaction",
        "unit_intensity",
    )
    assert [judgement.question_id for judgement in update["judgements"]] == list(unit_questions)
    assert decisions.calls[0].question_ids == unit_questions
    # Every question about a line sees who is listening and why the beat matters, so it
    # can judge whether a first-time listener would follow it.
    assert set(decisions.calls[0].state) == {
        "unit",
        "earlier_units",
        "audience",
        "narrative_job",
        "intended_feeling",
        "meanings",
        "supporting_claims",
    }
    assert update["call_log"][0]["operation"] == "judge_unit"


def _state_through_script(config: ContentConfig) -> ContentState:
    provider = create_demo_provider()
    state = cast(
        ContentState,
        create_initial_state("Topic", source_material=None, user_instructions=None, config=config),
    )
    editorial = EditorialDirector(**_node_args("editorial_director", config, provider))
    for operation in (
        FactResearcher(**_node_args("fact_researcher", config, provider)),
        editorial.create_plan,
        ScriptWriter(**_node_args("script_writer", config, provider)),
    ):
        state.update(operation(state))
    return state


class NodeArgs(TypedDict):
    name: str
    config: AgentConfig
    models: ModelRegistry
    provider: ModelProvider


def _node_args(name: str, config: ContentConfig, provider: FakeModelProvider) -> NodeArgs:
    return {
        "name": name,
        "config": config.agents[name],
        "models": config.models,
        "provider": provider,
    }


def test_director_notes_go_to_their_owners_narration_first(app_config: ContentConfig) -> None:
    sorted_note = Critique(verdict="revise", corrections=["U1: say the year first."], reasoning="")
    provider = FakeModelProvider({Critique: [sorted_note]}, default_factory=demo_response)
    critic = Critic(**_node_args("editorial_director", app_config, provider))
    state = _state_through_script(app_config)
    state["human_review_feedback"] = (
        "Tighter overall. U3: lead with the number. S2: show the archive. R1: wrong building"
    )

    update = apply_director_notes(state, sort_notes=critic.sort_notes)

    assert update["routing_decision"] == "notes_script"
    assert update["revision_notes"] == ["U3: lead with the number.", "U1: say the year first."]
    assert update["director_notes"] == ["S2: show the archive.", "R1: wrong building"]
    assert update["human_review_feedback"] is None


def test_notes_are_split_by_what_they_target() -> None:
    notes = split_notes("Punchier. U3: open with the number; S2: show him R1 - wrong island")

    assert notes.untargeted == "Punchier."
    assert notes.units == ["U3: open with the number"]
    assert notes.scenes == ["S2: show him"]
    assert notes.references == ["R1: wrong island"]
    assert split_notes("Make S2 feel colder.").scenes == []


def test_the_claims_behind_each_explanation_reach_the_writer() -> None:
    research = ResearchPack.model_validate(demo_response('{"topic": "x"}', ResearchPack))
    background = research.verified_facts[0].model_copy(
        update={"claim_id": "C2", "claim": "The record is what the sources document."}
    )
    research = research.model_copy(
        update={"verified_facts": [*research.verified_facts, background]}
    )
    brief = EditorialBrief.model_validate(demo_response('{"topic": "x"}', EditorialBrief))
    explanation = Explanation(
        term="the record", plain="what the sources document", claim_ids=["C2", "C9"]
    )
    brief = brief.model_copy(update={"explain": [explanation]})

    normalized, warnings = EditorialDirector._normalize_brief_claims(brief, research)
    evidence = _selected_evidence(research, normalized, {})

    assert "C2" in normalized.supporting_claim_ids
    assert normalized.explain[0].claim_ids == ["C2"]
    assert "C9" in warnings[0]
    # The writer also reads the research's own plain account of the story.
    assert evidence["research_summary"] == research.research_summary
    assert "C2" in {claim["claim_id"] for claim in evidence["claims"]}


def test_a_narration_note_is_fixed_by_its_kind(app_config: ContentConfig) -> None:
    critic = Critic(**_node_args("editorial_director", app_config, create_demo_provider()))
    state = _state_through_script(app_config)
    script = state["script_package"]
    assert script is not None
    first, second = passages(script.script_units)[:2]
    state["retakes_asked"] = {second.passage_id: 1}
    state["human_review_feedback"] = (
        f"{first.passage_id} [pronunciation]: Eniac = EN-ee-ack "
        f"{first.passage_id} [pause]: a beat before the number "
        f"{second.passage_id} [voice]: sounds bored"
    )

    update = apply_director_notes(state, sort_notes=critic.sort_notes)

    # Nothing for the writer: only the passages are recorded again.
    assert update["routing_decision"] == "notes_references"
    fixed = update["script_package"]
    assert fixed is not None
    assert fixed.voice_direction.say_as == {"Eniac": "EN-ee-ack"}
    assert fixed.script_units == script.script_units
    assert update["passage_directions"] == {first.passage_id: "a beat before the number"}
    assert update["retakes_asked"] == {second.passage_id: 2}

    state["human_review_feedback"] = f"{second.passage_id}: too many names at once"
    wording = apply_director_notes(state, sort_notes=critic.sort_notes)
    assert wording["routing_decision"] == "notes_script"
    assert wording["revision_notes"] == [f"{', '.join(second.unit_ids)}: too many names at once"]


def test_a_few_changed_lines_get_a_light_audit_confirmed_at_full_effort(
    app_config: ContentConfig,
) -> None:
    agent = replace(app_config.agents["fact_checker"], light_model_alias="creative")
    config = replace(app_config, agents={**app_config.agents, "fact_checker": agent})
    state = _state_through_script(config)
    provider = FakeModelProvider(default_factory=demo_response)
    checker = FactChecker(**_node_args("fact_checker", config, provider))

    def check(node: FactChecker) -> None:
        update = node(state)
        # As the graph's reducer does: clean audits accumulate.
        state.update(
            {**update, "unit_audits": {**state.get("unit_audits", {}), **update["unit_audits"]}}
        )

    check(checker)  # the first audit covers every line: full effort
    script = state["script_package"]
    assert script is not None

    def change_one_line(words: str) -> None:
        units = [
            unit.model_copy(update={"text": words}) if unit.unit_id == "U2" else unit
            for unit in script.script_units
        ]
        state["script_package"] = script.model_copy(update={"script_units": units})

    change_one_line("A plainer second line.")
    check(checker)
    change_one_line("Another plainer second line.")
    flagged = FakeModelProvider(
        {
            FactCheckReport: [
                {
                    "claim_findings": [
                        {
                            "claim": "x",
                            "claim_id": "C1",
                            "script_unit_ids": ["U2"],
                            "source_ids": [],
                            "status": "exaggerated",
                            "issue": "Stronger than the source.",
                        }
                    ],
                    "non_factual_unit_ids": [],
                    "routing_result": "revise_script",
                }
            ]
        },
        default_factory=demo_response,
    )
    check(FactChecker(**_node_args("fact_checker", config, flagged)))

    models = [call.model.model for call in provider.calls]
    assert models == ["deterministic-accurate", "deterministic-creative"]
    # The light audit's finding is confirmed on the full model before it counts.
    assert [call.model.model for call in flagged.calls] == [
        "deterministic-creative",
        "deterministic-accurate",
    ]
