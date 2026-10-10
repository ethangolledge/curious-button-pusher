"""The Editorial Director's System 1 rubric.

Each question asks Jev for exactly one judgement about one story node or connection.
Instructions name the state fields they rely on, because Jev reads literally and
is distracted by unrelated state. Arithmetic and comparisons stay in code: for
example, Jev classifies a transition and code compares it with the plan.

These are code rather than SKILL.md prose because question IDs, answer types, and
passing values feed routing directly.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

QuestionKind = Literal["noul", "choice", "score"]
Target = Literal[
    "research",
    "claim",
    "plan",
    "opening",
    "unit",
    "transition",
    "script",
    "beat",
    "audience",
    "scene",
    "bridge",
    "visual_sequence",
    "keyframe",
    "segment",
    "reference",
    "reference_image",
]

_QUALITY_LEVELS = (
    "Weak: vague, generic, or flat.",
    "Adequate: clear, but not especially compelling.",
    "Strong: specific and compelling.",
)


@dataclass(frozen=True, slots=True)
class Question:
    question_id: str
    target: Target
    kind: QuestionKind
    instructions: str
    criteria: Mapping[str, str] | tuple[str, ...]
    # Fixed correction line sent to the owning writer when this question fails.
    # `{target}`, `{answer}`, and `{expected}` are filled in by code.
    correction: str
    # Choice answers that fail. Unused when the plan supplies an expected answer.
    failing_choices: frozenset[str] = field(default_factory=frozenset)
    # Lowest score level that passes.
    pass_level: int = 1
    # A measurement feeds code (for example the emotional field) and never passes, fails,
    # or blocks; its answer is used as a probability, not a verdict.
    measure: bool = False

    def request(self) -> dict[str, Any]:
        criteria = (
            dict(self.criteria) if isinstance(self.criteria, Mapping) else list(self.criteria)
        )
        return {"type": self.kind, "instructions": self.instructions, "criteria": criteria}


_QUESTIONS = (
    Question(
        question_id="research_core",
        target="research",
        kind="noul",
        instructions=(
            "Do `claims` contain one concrete, surprising core that a short story could be "
            "built around?"
        ),
        criteria={
            "true": "A specific, supported event, mechanism, or contradiction stands out.",
            "false": "The claims are generic, scattered, or too thin to anchor a story.",
        },
        correction="Research lacks a concrete core; find the event or mechanism to build on.",
    ),
    # The story's weights: measurements only, turned into numbers by `story_weights.py`.
    Question(
        question_id="claim_worth",
        target="claim",
        kind="score",
        instructions="How much would a curious stranger scrolling past want to know `claim`?",
        criteria=(
            "They would not care.",
            "Mildly interesting.",
            "They would stop scrolling for it.",
        ),
        measure=True,
        correction="",
    ),
    Question(
        question_id="claim_connection",
        target="claim",
        kind="score",
        instructions=(
            "Having heard `hook`, would learning `claim` change how the listener sees the hook?"
        ),
        criteria=(
            "Unrelated to it.",
            "Adds context to it.",
            "Changes how the hook lands.",
        ),
        measure=True,
        correction="",
    ),
    Question(
        question_id="plan_curiosity",
        target="plan",
        kind="score",
        instructions=(
            "How strongly does `central_question` make a general viewer want to hear the answer?"
        ),
        criteria=_QUALITY_LEVELS,
        correction="Sharpen the central question so it is specific and intriguing.",
    ),
    Question(
        question_id="plan_payoff",
        target="plan",
        kind="noul",
        instructions=(
            "Does the last phase of `arc` deliver `promise` as an answer to `central_question`?"
        ),
        criteria={
            "true": "The final phase clearly pays off the promise.",
            "false": "The arc ends without answering the question or keeping the promise.",
        },
        correction="Make the final arc phase deliver the promise.",
    ),
    Question(
        question_id="opening_hook",
        target="opening",
        kind="score",
        instructions="How strongly does `opening` make `audience` want to keep listening?",
        criteria=_QUALITY_LEVELS,
        correction=(
            "{target}: rewrite the opening so it raises a specific question the viewer "
            "needs answered."
        ),
    ),
    Question(
        question_id="opening_orients",
        target="opening",
        kind="noul",
        instructions=(
            "Having heard only `opening` then `orientation`, would a listener know who this "
            "story is about and what happened?"
        ),
        criteria={
            "true": "They could say who it is about and what the story is.",
            "false": "They would still be guessing who or what this is about.",
        },
        correction="{target}: after the hook, say plainly who this is about and what happened.",
    ),
    Question(
        question_id="unit_pace",
        target="unit",
        kind="choice",
        instructions=(
            "Given `narrative_job` and `intended_feeling`, how does `unit.text` feel to "
            "`audience`, hearing it once?"
        ),
        criteria={
            "too_slow": "It lingers, repeats, or adds little; attention would drift.",
            "right": "It does its job at a pace that holds attention.",
            "overloaded": "It packs in more names, figures, or ideas than one hearing absorbs.",
        },
        failing_choices=frozenset({"too_slow", "overloaded"}),
        correction="{target}: it was judged {answer}; adjust its pace to its narrative job.",
    ),
    Question(
        question_id="unit_supported",
        target="unit",
        kind="noul",
        instructions=(
            "Is every factual statement in `unit.text` supported by `supporting_claims`, "
            "keeping their qualifications?"
        ),
        criteria={
            "true": "Each factual statement matches a supporting claim, or there are none.",
            "false": (
                "It states a fact, figure, name, or cause missing from `supporting_claims`, "
                "or drops a qualification."
            ),
        },
        correction=(
            "{target}: state only what its cited claims support, keeping their qualifications."
        ),
    ),
    Question(
        question_id="unit_plain",
        target="unit",
        kind="noul",
        instructions=(
            "Is `unit.text` told plainly, rather than as a solemn, portentous, or aphoristic "
            "pronouncement meant to sound profound?"
        ),
        criteria={
            "true": "It states what happened in plain, direct words.",
            "false": (
                "It reaches for weight: a grave aside, a moral, a rhetorical flourish, or a "
                "line built to sound profound."
            ),
        },
        correction="{target}: say it plainly; save the weighty line for the ending.",
    ),
    Question(
        question_id="unit_clear",
        target="unit",
        kind="noul",
        instructions=(
            "Hearing `unit.text` once, after `earlier_units`, would `audience` understand "
            "every term, name, and number in it, and why they are being told it?"
        ),
        criteria={
            "true": "A first-time listener follows it: plain words, and its point is clear.",
            "false": (
                "It assumes knowledge the listener lacks: an unexplained term or institution, "
                "a number with no meaning given, a reference to something never set up, or "
                "a fact whose point is left for the listener to work out."
            ),
        },
        correction=(
            "{target}: a first-time listener would not follow it. Say plainly what each term "
            "or number means and why it is here, or cut it."
        ),
    ),
    Question(
        question_id="unit_meaning",
        target="unit",
        kind="noul",
        instructions=(
            "`meanings` says what this line's facts show. Hearing `unit.text` after "
            "`earlier_units`, would the listener understand that meaning, whether it is said "
            "outright or is plain from how the story is told? When `meanings` is empty, "
            "answer yes."
        ),
        criteria={
            "true": (
                "The listener understands what the fact or number shows, within the evidence; "
                "it need not be explained if the telling already makes it clear."
            ),
            "false": (
                "The listener is left with a bare fact or number and no sense of what it shows."
            ),
        },
        correction=(
            "{target}: the listener would not understand what this fact shows; make it clear, "
            "in the telling or in a few words, without going beyond the evidence."
        ),
    ),
    Question(
        question_id="unit_spoken",
        target="unit",
        kind="noul",
        instructions=(
            "Would a good storyteller telling this story aloud say `unit.text` as it is "
            "written, after `earlier_units`?"
        ),
        criteria={
            "true": "It sounds like someone telling the story: plain spoken sentences.",
            "false": (
                "It sounds written or generated: a question inserted for drama rather than "
                "raised by the facts, a stock phrase, a judgement the `supporting_claims` do "
                "not make, officialese, or clauses stacked for the page."
            ),
        },
        correction="{target}: say it the way someone telling the story aloud would.",
    ),
    Question(
        question_id="unit_new",
        target="unit",
        kind="noul",
        instructions=(
            "Does `unit.text` move the listener on from `earlier_units`: a new fact, or what "
            "something already told means or leads to?"
        ),
        criteria={
            "true": "The listener learns something new, or understands something better.",
            "false": "It repeats what was already said without adding meaning.",
        },
        correction=(
            "{target}: it repeats what was already said; cut it, or make it say what that means."
        ),
    ),
    Question(
        question_id="unit_reaction",
        target="unit",
        kind="choice",
        instructions="Having just heard `unit.text`, what does a listener instinctively do next?",
        criteria={
            "lean_in": "Leans in to hear more.",
            "brace": "Steels themselves against it.",
            "recoil": "Pulls back from it.",
            "settle": "Breathes out and settles.",
        },
        correction="",
        measure=True,
    ),
    Question(
        question_id="unit_intensity",
        target="unit",
        kind="score",
        instructions="How strongly does a listener react on hearing `unit.text`?",
        criteria=(
            "Barely: it passes by.",
            "Clearly: it registers.",
            "Strongly: it stops them.",
        ),
        correction="",
        pass_level=0,
        measure=True,
    ),
    Question(
        question_id="transition_tension",
        target="transition",
        kind="choice",
        instructions=(
            "Compared with `previous_unit`, what does `unit.text` do to the listener's tension?"
        ),
        criteria={
            "build": "Raises the stakes, adds a complication, or deepens the question.",
            "hold": "Keeps the same level; continues or clarifies the thread.",
            "release": "Resolves, explains, or lets the listener breathe.",
            "turn": "Changes direction with a reversal, contradiction, or new angle.",
        },
        correction=(
            "{target}: the plan asks this unit to {expected} tension, but it reads as {answer}."
        ),
    ),
    Question(
        question_id="transition_why",
        target="transition",
        kind="noul",
        instructions=(
            "After `previous_unit`, would `audience` know why they are now hearing "
            "`unit.text`: how it follows from, answers, or turns what came before? "
            "`why_next`, when given, is the reason the plan intends."
        ),
        criteria={
            "true": "The step is clear: the listener sees how this follows or why it is here.",
            "false": "It jumps to a new fact or thread without saying how it connects.",
        },
        correction=(
            "{target}: the listener cannot tell why this comes next; say how it follows from "
            "what came before."
        ),
    ),
    Question(
        question_id="script_payoff",
        target="script",
        kind="noul",
        instructions=(
            "Does `ending` come back to the question raised by `opening` and "
            "`central_question`, changed by what the story has shown?"
        ),
        criteria={
            "true": "The ending returns to the opening's question, now loaded with what the "
            "story showed, and leaves the listener holding it.",
            "false": "The ending changes subject, restates a fact already told, or closes the "
            "question flat.",
        },
        correction=(
            "Bring the ending back to the opening's question, sharpened by what the story "
            "showed; never restate a fact or close it flat."
        ),
    ),
    Question(
        question_id="script_story",
        target="script",
        kind="noul",
        instructions=(
            "Read `narration` aloud. Does it sound like one person telling a story, each "
            "sentence leading into the next?"
        ),
        criteria={
            "true": "It flows as one told story.",
            "false": "It sounds like a list of separate facts read out one after another.",
        },
        correction=(
            "Make it a told story: let each sentence lead into the next (so, which meant, by "
            "then, and yet), let long sentences carry and short ones land."
        ),
    ),
    Question(
        question_id="script_voice",
        target="script",
        kind="choice",
        instructions=(
            "How does the voice of `narration` come across, against `intended_voice` (the "
            "voice the narration is meant to have)?"
        ),
        criteria={
            "on_voice": "It sounds the way `intended_voice` describes, fair to everyone in it.",
            "flat": "A plain recitation with no voice at all.",
            "overdone": "Trying too hard: stock phrases, winking at the listener, more than "
            "the intended voice asks.",
            "unfair": "Mocking a person rather than letting the facts speak.",
        },
        # A measurement until it has earned trust: on scripts a person heard as soulless
        # it answered as on voice at 80–93% confidence. Its answers are recorded and
        # learned from people's verdicts, but never pass or fail anything.
        measure=True,
        correction="",
    ),
    Question(
        question_id="scene_duplication",
        target="scene",
        kind="choice",
        instructions="How does the image described in `scene` relate to `narration`?",
        criteria={
            "adds": "It shows something the words do not: context, evidence, scale, or feeling.",
            "reinforces": "It echoes the words in a way that helps them land.",
            "duplicates": "It literally illustrates what is said and adds nothing.",
        },
        failing_choices=frozenset({"duplicates"}),
        correction="{target}: show something the narration does not already say.",
    ),
    Question(
        question_id="scene_meaning",
        target="scene",
        kind="score",
        instructions=(
            "How much does the image in `scene` help a viewer understand or feel `narration`?"
        ),
        criteria=_QUALITY_LEVELS,
        correction="{target}: choose an anchor that makes the narration clearer or felt.",
    ),
    Question(
        question_id="scene_concrete",
        target="scene",
        kind="noul",
        instructions=(
            "Does `scene.anchor` show a specific person, place, or object that `narration` "
            "names or directly implies?"
        ),
        criteria={
            "true": (
                "A viewer could point at something in the image and name it from the "
                "narration: the person, the place, the money, the document, the object."
            ),
            "false": (
                "The image is only a general mood or abstract symbol that could accompany "
                "any story."
            ),
        },
        correction=(
            "{target}: anchor it on a concrete person, place, or object from its narration; "
            "keep any symbolism around that."
        ),
    ),
    Question(
        question_id="bridge_shared",
        target="bridge",
        kind="noul",
        instructions=(
            "Does `morph_bridge` name a shape, texture, colour, or motion that could plausibly "
            "appear in both `from_scene` and `to_scene`?"
        ),
        criteria={
            "true": "The bridge is something visible that both scenes can contain.",
            "false": "The bridge is abstract, or belongs to only one of the scenes.",
        },
        correction=(
            "{target}: choose a morph bridge (shape, texture, colour, or motion) visible in "
            "both scenes."
        ),
    ),
    Question(
        question_id="visual_flow",
        target="visual_sequence",
        kind="noul",
        instructions=(
            "Do `scenes`, in order, read as one connected visual journey rather than "
            "unrelated pictures?"
        ),
        criteria={
            "true": "The scenes share a motif, palette, or progression.",
            "false": "The scenes feel like unrelated pictures.",
        },
        correction="Connect the scenes through a shared motif, palette, or visual progression.",
    ),
    # Rendered media. Jev reads text only, so a vision model first describes what was
    # rendered (`observation`) and Jev judges that description against the plan.
    Question(
        question_id="reference_relevant",
        target="reference",
        kind="noul",
        instructions=(
            "Is `query` a specific person, place, or object that `narration` names or directly "
            "implies, and would a picture of it help show `narration`?"
        ),
        criteria={
            "true": "It is named or implied by the narration and worth showing.",
            "false": "It is unrelated, too vague to picture, or an abstract idea.",
        },
        correction="{target}: search only for a person, place, or object from its narration.",
    ),
    Question(
        question_id="reference_matches",
        target="reference_image",
        kind="noul",
        instructions=(
            "Going by `title`, `description`, and `observation`, does this image clearly show "
            "`query` (the `kind` asked for), well enough to draw it from?"
        ),
        criteria={
            "true": "The file is about the query, and the subject is clear and unobstructed.",
            "false": (
                "It shows something else, the subject is tiny or hidden, or it is mostly text, "
                "a document, or a crowd."
            ),
        },
        correction="{target}: find a clearer image of the query.",
    ),
    Question(
        question_id="keyframe_matches_anchor",
        target="keyframe",
        kind="noul",
        instructions=(
            "Does `observation` show the subject, setting, and key elements described in `anchor`?"
        ),
        criteria={
            "true": "The main subject and setting of `anchor` are clearly present.",
            "false": "The subject or setting is missing, replaced, or unrecognisable.",
        },
        correction=(
            "{target}: the image lost its anchor; put the main subject and setting clearly "
            "in frame."
        ),
    ),
    Question(
        question_id="keyframe_on_theme",
        target="keyframe",
        kind="score",
        instructions="How closely does `observation` match the look described in `theme_look`?",
        criteria=(
            "Off-theme: different palette, lighting, or style.",
            "Partly on-theme.",
            "On-theme: palette, lighting, and texture match.",
        ),
        correction="{target}: bring the image back to the theme's palette, light, and texture.",
    ),
    Question(
        question_id="keyframe_shows_story",
        target="keyframe",
        kind="noul",
        instructions=(
            "Does `observation` show the story subject described in `anchor`, rather than "
            "generic genre scenery `anchor` does not ask for (a city skyline, rain-soaked "
            "streets, a caped or masked figure)?"
        ),
        criteria={
            "true": "The image is about the anchor's person, place, or object.",
            "false": "Genre scenery or a stock figure takes the place of the story subject.",
        },
        correction="{target}: show the story's subject; drop scenery the scene did not ask for.",
    ),
    Question(
        question_id="keyframe_framing",
        target="keyframe",
        kind="noul",
        instructions="Does the `framing` in `observation` match `expected_framing`?",
        criteria={
            "true": "The space is as open or as enclosed as expected.",
            "false": "The space is clearly more open or more enclosed than expected.",
        },
        correction="{target}: reshape the space around the focal point as the scene's field asks.",
    ),
    Question(
        question_id="keyframe_clean",
        target="keyframe",
        kind="noul",
        instructions=(
            "Is `observation` free of readable text, letters, watermarks, deformed faces or "
            "anatomy, and other visible generation errors?"
        ),
        criteria={
            "true": "No text and no visible generation errors are reported.",
            "false": "Text, a watermark, deformed anatomy, or another visible error is reported.",
        },
        correction="{target}: regenerate without text or visual errors.",
    ),
    Question(
        question_id="segment_keeps_style",
        target="segment",
        kind="noul",
        instructions=(
            "Do `start`, `middle`, and `end` in `observations` all have the rendering style "
            "described in `theme_look`, without drifting towards photographic or 3D?"
        ),
        criteria={
            "true": "Every sampled frame keeps the theme's rendering style.",
            "false": "At least one frame turns photographic, 3D, or another style.",
        },
        correction="{target}: the clip drifted out of the theme's style; keep to it throughout.",
    ),
    Question(
        question_id="segment_shift",
        target="segment",
        kind="noul",
        instructions=(
            "From `start` to `end` in `observations`, does the space change the way "
            "`expected_shift` describes?"
        ),
        criteria={
            "true": "The framing changes that way: closing in, opening out, or flowing on.",
            "false": "It changes the opposite way, or not at all where a change was expected.",
        },
        correction="{target}: let the space change as the transition asks.",
    ),
    Question(
        question_id="segment_holds_anchor",
        target="segment",
        kind="noul",
        instructions=(
            "Do `start` and `middle` in `observations` show the subject and setting of `anchor`?"
        ),
        criteria={
            "true": "The clip opens on and holds the anchor scene before transforming.",
            "false": "The clip drifts away from the anchor too early or never shows it.",
        },
        correction="{target}: hold the anchor scene longer before the morph begins.",
    ),
    Question(
        question_id="segment_morph",
        target="segment",
        kind="choice",
        instructions=(
            "Across `start`, `middle`, and `end` in `observations`, how does the clip change "
            "from `anchor` towards `next_anchor`?"
        ),
        criteria={
            "smooth": "A gradual, continuous transformation with recognisable forms throughout.",
            "abrupt": "A sudden jump or cut rather than a transformation.",
            "melted": "The middle dissolves into shapeless, unrecognisable mush.",
        },
        failing_choices=frozenset({"abrupt", "melted"}),
        correction="{target}: the morph was {answer}; make the transformation gradual and legible.",
    ),
    Question(
        question_id="beat_heard",
        target="beat",
        kind="noul",
        instructions=(
            "`heard` is what a first-time listener said they took from the narration. Do they "
            "now know what `audience_should_know` says, in substance?"
        ),
        criteria={
            "true": "Their account shows they understood it.",
            "false": "Their account misses it, gets it wrong, or shows they were lost here.",
        },
        correction=(
            "{target}: a first-time listener did not come away knowing what this beat should "
            "leave them with; tell it so they do."
        ),
    ),
    Question(
        question_id="story_heard",
        target="audience",
        kind="noul",
        instructions=(
            "`heard` is what a first-time listener said they took from the narration. Does it "
            "retell `story_chain`, the same events in the same causal order, around a question "
            "close to `central_question`?"
        ),
        criteria={
            "true": "They could retell the story the plan meant to tell, and why it matters.",
            "false": "Their story differs, misses its causes, or asks a different question.",
        },
        correction=(
            "The story a first-time listener reconstructed is not the one the plan tells; "
            "make the causal chain and the central question audible."
        ),
    ),
)

QUESTIONS: Mapping[str, Question] = MappingProxyType(
    {question.question_id: question for question in _QUESTIONS}
)


def questions_for(target: Target) -> tuple[Question, ...]:
    return tuple(question for question in _QUESTIONS if question.target == target)
