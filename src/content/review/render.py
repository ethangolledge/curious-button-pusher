"""Plain-text renderings of each stage's output, for the review pages, the saved handoff and
the final package."""

from content.judging.outcomes import judgement_line
from content.schemas.audience import AudienceReport
from content.schemas.fact_check import FactCheckReport
from content.schemas.media import ProductionResult
from content.schemas.package import FinalContentPackage, ReviewHandoff, ScenePrompts
from content.schemas.plan import ArcPhase, EditorialBrief, StorySize
from content.schemas.research import ResearchClaim, ResearchPack
from content.schemas.review import HumanDecision
from content.schemas.script import ScriptPackage
from content.schemas.visuals import VisualPackage


def _beat_line(phase: ArcPhase, seconds: float | None) -> str:
    size = f", {phase.words} words ≈ {seconds:.0f} s" if seconds is not None else ""
    claims = f" [{', '.join(phase.claim_ids)}]" if phase.claim_ids else ""
    answers = "".join(
        f" {label}: {answer}"
        for label, answer in (
            ("Leaves them knowing", phase.audience_knows_after),
            ("Next question", phase.next_question),
            ("Next", phase.leads_to_next),
        )
        if answer
    )
    return (
        f"- **{phase.phase_id} · {phase.role}** ({phase.link}, told with {phase.telling}, "
        f"{phase.tension}{size}): {phase.audience_feeling} — {phase.narrative_job}{answers}"
        f"{claims}"
    )


def render_scene_prompts(prompts: list[ScenePrompts]) -> list[str]:
    lines = ["## Scene Prompts", ""]
    for scene in prompts:
        lines.extend(
            [
                f"### {scene.scene_id}",
                "",
                "**Keyframe (image):**",
                "",
                "```text",
                scene.keyframe_prompt,
                "```",
                "",
                "**Segment (video, from this keyframe to the next):**",
                "",
                "```text",
                scene.segment_prompt,
                "```",
                "",
            ]
        )
    return lines


def _claim_lines(claims: list[ResearchClaim]) -> list[str]:
    if not claims:
        return ["- None"]
    lines = []
    for claim in claims:
        details = f"Sources: {', '.join(claim.source_ids) or 'None'}"
        if claim.qualification:
            details += f"; Qualification: {claim.qualification}"
        lines.append(f"- **{claim.claim_id}:** {claim.claim} _{details}_")
    return lines


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- None"]


def render_plan(brief: EditorialBrief, size: StorySize | None = None) -> list[str]:
    beat_seconds = size.beat_seconds if size else {}
    lines = [
        "## Creative Plan",
        "",
        f"**Central question:** {brief.central_question}",
        f"**Promise:** {brief.promise}",
        f"**Angle:** {brief.central_angle}",
        f"**Audience:** {brief.intended_audience}",
        f"**Takeaway:** {brief.intended_takeaway}",
        f"**Tone:** {brief.tone}",
        "",
        brief.narrative_direction,
        "",
        "### The Story, Plainly",
        "",
        *[f"{index}. {step}" for index, step in enumerate(brief.story_chain, start=1)],
        "",
        "### Story Spine",
        "",
        f"The listener starts out knowing: {brief.audience_starts_knowing}",
        "",
        *[_beat_line(phase, beat_seconds.get(phase.phase_id)) for phase in brief.arc],
        "",
        "### What Each Claim Is For",
        "",
        "| Claim | Role | Job in the story | What it means |",
        "|---|---|---|---|",
        *[
            f"| {plan.claim_id} | {plan.story_role.replace('_', ' ')} | {plan.narrative_job} "
            f"| {plan.meaning} |"
            for plan in brief.claims
        ],
        "",
    ]
    if brief.explain:
        lines += [
            "### Explained for the Listener",
            "",
            *[f"- **{item.term}**: {item.plain}" for item in brief.explain],
            "",
        ]
    if size is not None:
        lines += [
            "### Length",
            "",
            f"About **{size.estimate_seconds:.0f} s** of narration; planned at "
            f"**{size.target_seconds:.0f} s**.",
            *([brief.length_note] if brief.length_note else []),
            *[
                f"- The {seconds:.0f} s edit of the music: "
                + (
                    "the nearest, used as planned"
                    if change == min((words for _, words in size.edits), key=abs)
                    else f"{'add' if change > 0 else 'cut'} about {abs(change)} words"
                )
                for seconds, change in size.edits
            ],
            "",
        ]
    if size is not None and size.claims:
        lines += [
            "### Weights",
            "",
            "Score = worth × connection × evidence (in full from 0.7). Words go to beats by "
            "their strongest claim's score.",
            "",
            "| Claim | Evidence | Worth | Connection | Score |",
            "|---|---|---|---|---|",
            *[
                f"| {c.claim_id} | {c.evidence:.2f} | {c.worth:.2f} | {c.connection:.2f} | "
                f"{c.score:.2f} |"
                for c in size.claims
            ],
            "",
        ]
    if brief.left_out:
        lines += [
            "### Left Out",
            "",
            *[f"- **{item.what}**: {item.why}" for item in brief.left_out],
            "",
        ]
    for heading, items in (
        ("Style Boundaries", brief.style_boundaries),
        ("Script Assignment", brief.story_assignment),
        ("Required Context", brief.required_context),
        ("Fact-Check Priorities", brief.fact_check_priorities),
        ("Visual Principles", brief.visual_principles),
        ("Editorial Risks", brief.editorial_risks),
    ):
        lines.extend([f"### {heading}", "", *_bullet_lines(items), ""])
    return lines


def render_script(script: ScriptPackage) -> list[str]:
    lines = [
        f"## Master Narration — {script.title}",
        "",
        script.master_script,
        "",
        f"**Intended takeaway:** {script.intended_takeaway}",
        f"**Claims used:** {', '.join(script.claims_used) or 'None'}",
        f"**Voice:** {script.voice_direction.tone}; {script.voice_direction.pace}; "
        f"{script.voice_direction.delivery}",
        "",
        "### Pronunciation Notes",
        "",
        *_bullet_lines(script.voice_direction.pronunciation_notes),
        "",
        "### Connected Script Units",
        "",
    ]
    for unit in script.script_units:
        lines.extend(
            [
                f"#### {unit.unit_id} — {unit.narrative_function.replace('_', ' ').title()} "
                f"· {unit.arc_phase_id} · enters: {unit.transition_intent}",
                "",
                unit.text,
                "",
                "**Research claims:** " + (", ".join(unit.claim_ids) or "None"),
                "",
            ]
        )
    return lines


def render_fact_check(report: FactCheckReport) -> list[str]:
    return [
        "## Fact Check",
        "",
        f"**Severity:** {report.severity}",
        f"**Auditor route:** {report.routing_result}",
        f"**Non-factual units:** {', '.join(report.non_factual_unit_ids) or 'None'}",
        "",
        "### Findings",
        "",
        *_bullet_lines(
            [
                f"{finding.status}: {finding.claim} "
                f"(units {', '.join(finding.script_unit_ids) or 'none'}) — {finding.issue}"
                + "".join(
                    f" {label}: {value}."
                    for label, value in (
                        ("Evidence supports", finding.evidence_boundary),
                        ("Must carry", finding.required_qualification),
                        ("Must not imply", finding.forbidden_implication),
                    )
                    if value
                )
                for finding in report.claim_findings
            ]
        ),
        "",
    ]


def render_audience(report: AudienceReport, brief: EditorialBrief) -> list[str]:
    """What a first-time listener took from the narration, beside what the plan meant
    them to: the gap is what the audience missed."""
    stumbles = [
        f"{label}: “{flag.quote}” — {flag.note}"
        for label, flags in (
            ("Confused by", report.confusions),
            ("Could not see why it was there", report.unrelated_facts),
            ("Needed prior knowledge", report.unclear_terms),
            ("Lost the thread at", [report.lost_thread_at] if report.lost_thread_at else []),
        )
        for flag in flags
    ]
    return [
        "## What a First-Time Listener Heard",
        "",
        f"**About:** {report.about}",
        f"**What happened:** {report.what_happened}",
        f"**Why:** {report.why_it_happened}",
        f"**Why it matters:** {report.why_it_matters}",
        f"**The question:** {report.question}",
        f"**Unresolved:** {report.unresolved}",
        "",
        "Facts that stayed with them:",
        *_bullet_lines(report.key_facts),
        "",
        "Where they stumbled:",
        *_bullet_lines(stumbles or ["Nowhere."]),
        "",
        "### The Story the Plan Meant to Tell",
        "",
        *[f"{index}. {step}" for index, step in enumerate(brief.story_chain, start=1)],
        "",
    ]


def render_visuals(visuals: VisualPackage) -> list[str]:
    lines = ["## Storyboard", "", visuals.overall_visual_direction, ""]
    for scene in visuals.scenes:
        anchor = scene.anchor
        lines.extend(
            [
                f"### {scene.scene_id} — {scene.visual_function.replace('_', ' ').title()} "
                f"· units {', '.join(scene.script_unit_ids)}",
                "",
                f"**Anchor:** {anchor.subject}, in {anchor.setting}",
                f"**Composition:** {anchor.composition}",
                f"**Key elements:** {', '.join(anchor.key_elements)}",
                f"**Light and colour:** {anchor.light_and_colour}",
                f"**Camera:** {scene.camera} — {scene.motion}",
                f"**Morph bridge:** {scene.morph_bridge}",
                f"**Purpose:** {scene.purpose} ({scene.evidence_presentation})",
                "",
            ]
        )
    lines.extend(["### Continuity Notes", "", *_bullet_lines(visuals.continuity_notes), ""])
    return lines


def render_production(result: ProductionResult) -> list[str]:
    return [
        "## Production",
        "",
        f"**Video:** {result.video_path} ({result.duration:.1f} s)",
        f"**Storyboard:** {result.contact_sheet_path}",
        f"**Narration:** {result.narration_path}",
        f"**Subtitles:** {result.subtitles_path}",
        f"**Music:** {result.music_path or 'None'}",
        "",
        *_bullet_lines(
            [
                f"{timing.scene_id}: {timing.start:.1f}–{timing.end:.1f} s"
                for timing in result.scenes
            ]
        ),
        "",
    ]


def render_research(research: ResearchPack) -> list[str]:
    lines = [
        "## Research Pack",
        "",
        research.research_summary,
        "",
        f"**Confidence:** {research.research_confidence}",
        f"**Evidence status:** {research.evidence_status}",
        f"**Research status:** {research.research_status}",
        f"**Classified claims:** {research.classified_claim_count}",
        f"**Sources:** {len(research.source_references)}",
        "",
        "### Timeline",
        "",
        *_bullet_lines(
            [
                f"{event.date_or_period}: {event.event} (Claims: {', '.join(event.claim_ids)})"
                for event in research.timeline
            ]
        ),
        "",
        "### Cast",
        "",
        *_bullet_lines(
            [
                f"**{member.name}** ({member.role}): {member.wanted} "
                f"(Claims: {', '.join(member.claim_ids)})"
                for member in research.cast
            ]
        ),
        "",
        "### Documented Links",
        "",
        *_bullet_lines(
            [
                f"{link.from_claim_id} {link.relation.replace('_', ' ')} {link.to_claim_id} "
                f"(Sources: {', '.join(link.source_ids)})"
                for link in research.links
            ]
        ),
        "",
    ]
    for heading, claims in (
        ("Verified Facts", research.verified_facts),
        ("Reported Claims", research.reported_claims),
        ("Disputed Claims", research.disputed_claims),
        ("Inferences", research.inferences),
        ("Unsupported Claims", research.unsupported_claims),
    ):
        lines.extend([f"### {heading}", "", *_claim_lines(claims), ""])

    lines.extend(["### Source Comparisons", ""])
    if not research.source_comparisons:
        lines.extend(["- None", ""])
    for comparison in research.source_comparisons:
        lines.extend(
            [
                f"#### {comparison.subject}",
                "",
                f"**Sources:** {', '.join(comparison.source_ids)}",
                f"**Consensus:** {comparison.consensus}",
                f"**Significance:** {comparison.significance}",
                "",
                "**Disagreements:**",
                "",
                *_bullet_lines(comparison.disagreements),
                "",
            ]
        )
    for heading, items in (
        ("Contradictions", research.contradictions),
        ("Missing Evidence", research.missing_evidence),
        ("Factual Limitations", research.factual_limitations),
        ("Safe Wording", research.safe_wording),
    ):
        lines.extend([f"### {heading}", "", *_bullet_lines(items), ""])

    lines.extend(["### Sources and Assessments", ""])
    for source in research.source_references:
        supported_claim_ids = [
            claim.claim_id for claim in research.all_claims if source.source_id in claim.source_ids
        ]
        lines.append(
            f"- **{source.source_id}: {source.title}**" + (f" ({source.url})" if source.url else "")
        )
        lines.append(f"  - Supports claims: {', '.join(supported_claim_ids) or 'None'}")
        lines.append(f"  - Type: {source.source_type.replace('_', ' ')}")
        lines.append(f"  - Assessment: {source.credibility_notes}")
        if source.limitations:
            lines.append(f"  - Limitations: {'; '.join(source.limitations)}")
    if not research.source_references:
        lines.append("- None")
    lines.append("")
    return lines


def render_human_decisions(decisions: list[HumanDecision]) -> list[str]:
    return [
        "## Human Decisions",
        "",
        *_bullet_lines(
            [
                f"{decision.stage} (revision {decision.revision}): {decision.action}"
                + (f" — {decision.feedback}" if decision.feedback else "")
                for decision in decisions
            ]
        ),
        "",
    ]


def package_to_markdown(package: FinalContentPackage) -> str:
    lines = [
        f"# {package.approved_script.title}",
        "",
        f"**Topic:** {package.topic}",
        f"**Approval:** {package.approval_status}",
        f"**Target duration:** {package.duration_seconds} seconds",
        f"**Aspect ratio:** {package.aspect_ratio}",
        "",
        *render_plan(package.editorial_brief),
        *render_script(package.approved_script),
        "## Narration Generation Prompt",
        "",
        "```text",
        package.narration_prompt,
        "```",
        "",
        *render_visuals(package.visual_plan),
        *render_scene_prompts(package.scene_prompts),
        *(render_production(package.production) if package.production else []),
        *render_fact_check(package.fact_check_report),
        *render_human_decisions(package.human_decisions),
        *render_research(package.research_pack),
        "## Warnings",
        "",
        *_bullet_lines(package.warnings),
        "",
    ]
    return "\n".join(lines)


def review_handoff_to_markdown(handoff: ReviewHandoff) -> str:
    request, response = handoff.review_request, handoff.review_response
    lines = [
        f"# Human Review — {request.stage.replace('_', ' ').title()}",
        "",
        f"**Topic:** {handoff.topic}",
        f"**Reason:** {request.reason}",
        f"**Decision:** {response.action if response else 'waiting'}",
        "",
        "## Findings",
        "",
        *_bullet_lines(request.findings),
        "",
        "## Required Changes",
        "",
        *_bullet_lines(request.required_changes),
        "",
    ]
    if response and response.feedback:
        lines.extend(["## Human Feedback", "", response.feedback, ""])
    if handoff.editorial_brief is not None:
        lines.extend(render_plan(handoff.editorial_brief))
    if handoff.script_package is not None:
        lines.extend(render_script(handoff.script_package))
    if handoff.fact_check_report is not None:
        lines.extend(render_fact_check(handoff.fact_check_report))
    if handoff.visual_package is not None:
        lines.extend(render_visuals(handoff.visual_package))
    lines.extend(
        [
            "## Jev Judgements",
            "",
            *_bullet_lines([judgement_line(judgement) for judgement in handoff.judgements]),
            "",
        ]
    )
    if handoff.research_pack is not None:
        lines.extend(render_research(handoff.research_pack))
    lines.extend(
        [
            "## Warnings",
            "",
            *_bullet_lines(handoff.warnings),
            "",
            "_The companion JSON file contains every completed structured artifact._",
            "",
        ]
    )
    return "\n".join(lines)
