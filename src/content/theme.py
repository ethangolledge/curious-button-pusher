"""The theme: one config (`theme.json`, exact values for code) and one skill (`SKILL.md`,
prose for the models). Together they are the channel's look, sound, and subtitles."""

import hashlib
import json
import re
import shutil
import statistics
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from string import Formatter
from typing import Any, Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from content.schemas.base import ImmutableModel
from content.schemas.script import VoiceDirection
from content.schemas.story import Reaction, StoryRole, Transition
from content.schemas.visuals import SceneAnchor

# A channel's own theme is kept in the cloud bucket, not in git (see `storage.py`).
PULL_HINT = " (a channel's theme comes back from the bucket: content storage pull)"
HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")

# The slots each prompt template may use. Anything else is a typo, caught at load time.
KEYFRAME_SLOTS = frozenset(
    {
        "style",
        "texture",
        "lighting",
        "avoid",
        "subject",
        "setting",
        "composition",
        "key_elements",
        "light_and_colour",
        "field_frame",
        "field_light",
        "frame",
        "orientation",
    }
)
FIGURE_SLOTS = frozenset({"subject", "name", "likeness"})
SILHOUETTE_SLOTS = frozenset({"subject", "silhouette"})
SEGMENT_SLOTS = frozenset(
    {
        "style",
        "texture",
        "lighting",
        "morph",
        "avoid",
        "subject",
        "setting",
        "camera",
        "motion",
        "morph_bridge",
        "next_subject",
        "next_setting",
        "frame",
        "orientation",
        "field_motion",
        "shift",
    }
)


class ThemeError(ValueError):
    pass


class FormatSpec(ImmutableModel):
    """One shape of video the channel makes: short vertical, long widescreen. Each video
    picks one; the look, voice and music stay the channel's."""

    # Where it goes, in plain words, for the person choosing.
    platforms: str = ""
    width: int
    height: int
    fps: int
    aspect_ratio: str
    # The frame as the image and video prompts name it: "Vertical 9:16", "vertical".
    frame: str
    orientation: str
    min_seconds: float
    max_seconds: float
    # A person signs off the story plan before any script is written: worth it where a
    # rewrite costs most.
    review_plan: bool = False
    # Subtitles sized for this frame, over the theme's `subtitles`.
    subtitle_font_size: int | None = None
    subtitle_max_words: int | None = None
    subtitle_margin_bottom: int | None = None


class ColourScale(ImmutableModel):
    """Where the colour-emotion model's standard units land in this theme's keyframes.

    Valdez and Mehrabian's coefficients are standardised, so one unit is one standard
    deviation: `neutral` and `per_unit` are the median and spread measured on real
    keyframes, and should be refitted from `learning/keyframes.jsonl` as runs add more."""

    neutral: float
    per_unit: float
    # How far a keyframe may miss its target before it is redrawn.
    tolerance: float

    def target(self, units: float) -> float:
        return self.neutral + units * self.per_unit


class ToneSpec(ImmutableModel):
    """The light and colour every keyframe aims for, measured by code on 8-bit values:
    ceilings it must stay under, and the brightness and saturation each scene's field
    sets as its target."""

    # Mean brightness (luma, 0–255).
    max_mean_brightness: float
    # Saturation of the most saturated tenth of the image (0–181).
    max_highlight_saturation: float
    # Added to a keyframe's prompt when it is redrawn for being too bright.
    darker: str
    # Mean brightness (luma) and mean saturation targets for a scene's field.
    brightness: ColourScale
    saturation: ColourScale
    # Added when a keyframe is redrawn for being too dark, or too muted, for its scene.
    lighter: str
    richer: str


class ReactionLook(ImmutableModel):
    """How a scene is shaped when its lines make the listener react this way. Only
    space, light, colour, and motion: never emotion words, never added content.
    Each wording has three strengths: slight, clear, strong."""

    # How open the space is: -1 enclosed, 1 wide open.
    aperture: float = Field(ge=-1, le=1)
    # Colour temperature: -1 cold, 1 warm.
    temperature: float = Field(ge=-1, le=1)
    # The reaction's place on Russell's circumplex at full strength, -1 to 1: how pleasant
    # and how activating it is. Sets the scene's brightness and saturation targets.
    pleasure: float = Field(ge=-1, le=1)
    arousal: float = Field(ge=-1, le=1)
    frame: tuple[str, str, str]
    light: tuple[str, str, str]
    motion: tuple[str, str, str]
    # Plain words for how the frame should look, checked against perception.
    framing: str
    cameras: list[str]
    # The colour a still's breathing ripples take on when its scene lands this way.
    ripple_colour: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class FieldSpec(ImmutableModel):
    reactions: dict[Reaction, ReactionLook]
    # Used when a scene has no measured reaction (for example a resumed run).
    neutral: ReactionLook
    # How the space changes between scenes, by the change in aperture.
    shifts: dict[Literal["inward", "outward", "sideways"], str]
    # How fast it changes: a small change is slow; a large one is swift, never a cut.
    speeds: dict[Literal["slow", "swift"], str]
    swift_above: float
    # Added to a keyframe redrawn for having the wrong colour temperature.
    warmer: str
    cooler: str


class CameraFraming(ImmutableModel):
    """One end of a camera move over a still. The view's centre starts at the scene's focal
    point, moves `toward_centre` of the way to the frame's centre, then shifts by `x` and
    `y` (fractions of the picture); `zoom` is how far the view is magnified."""

    zoom: float = Field(ge=1.0, le=2.0)
    toward_centre: float = Field(default=0.0, ge=0.0, le=1.0)
    x: float = Field(default=0.0, ge=-0.5, le=0.5)
    y: float = Field(default=0.0, ge=-0.5, le=0.5)


class CameraMove(ImmutableModel):
    """A camera move: how it is described to the video model, and how it glides over a
    still from `start` to `end`."""

    describe: str
    start: CameraFraming
    end: CameraFraming


class BreathSpec(ImmutableModel):
    """A still breathes: it swells by `swell` (a share of the frame) once every `seconds`,
    and ripples of `ripple_pixels` (at 1080 wide) spread from its focal point. The ripple
    crests take on the scene's emotional colour (each reaction's `ripple_colour`), at most
    `tint` opacity for a scene that lands strongly, less for a quieter one; 0 keeps them
    colourless."""

    seconds: float = Field(gt=0)
    swell: float = Field(ge=0.0, le=0.1)
    ripple_pixels: float = Field(ge=0.0, le=40.0)
    tint: float = Field(ge=0.0, le=0.3)


class MorphLayerSpec(ImmutableModel):
    """The local effects laid over an AI morph, peaking mid-morph and zero at both ends:
    liquid warp (pixels at 1080 wide), light trails, a mirrored bloom, colour plates slid
    apart (pixels), a hue swing (radians) and extra saturation. Zero switches one off."""

    warp_pixels: float = Field(ge=0.0, le=80.0)
    trails: float = Field(ge=0.0, le=1.0)
    mirror: float = Field(ge=0.0, le=1.0)
    plate_shift_pixels: int = Field(ge=0, le=60)
    hue_radians: float = Field(ge=0.0, le=3.2)
    saturation: float = Field(ge=0.0, le=2.0)


class TextureSpec(ImmutableModel):
    """One continuous pass over the whole cut: a slowly zooming fractal blended into the
    shadows (`fractal`, an opacity), a vignette breathing by `vignette_swing` radians,
    colour fringing (pixels), grain strength, and a light flicker. Zero switches one off."""

    fractal: float = Field(ge=0.0, le=1.0)
    vignette_swing: float = Field(ge=0.0, le=0.5)
    fringe_pixels: int = Field(ge=0, le=10)
    grain: int = Field(ge=0, le=40)
    flicker: float = Field(ge=0.0, le=0.1)


class MotionSpec(ImmutableModel):
    """Everything that moves locally, at no cost: the stills, the morph effects, the
    texture, and how long two stills dissolve when no morph joins them."""

    breath: BreathSpec
    morph: MorphLayerSpec
    texture: TextureSpec
    dissolve_seconds: float = Field(ge=0.0, le=3.0)


class VisualSpec(ImmutableModel):
    style: str
    texture: str
    lighting: str
    morph: str
    camera_moves: dict[str, CameraMove] = Field(min_length=1)
    motion: MotionSpec
    # How a public figure is drawn ({subject}, {name}, {likeness}), and how as a silhouette
    # when a portrait was refused or garbled ({subject}, {silhouette}).
    figure: str
    silhouette: str
    avoid: str
    # The morphs are where the picture is allowed to run wild: brief colour, panels
    # flipping. So they have their own list, without the stills' limits on colour and cuts.
    morph_avoid: str
    tone: ToneSpec
    field: FieldSpec
    # Added to a keyframe prompt when real reference images are attached.
    reference_note: str
    keyframe_template: str
    segment_template: str
    final_segment_template: str

    @model_validator(mode="after")
    def _templates_use_known_slots(self) -> Self:
        for name, template, allowed in (
            ("keyframe_template", self.keyframe_template, KEYFRAME_SLOTS),
            ("segment_template", self.segment_template, SEGMENT_SLOTS),
            ("final_segment_template", self.final_segment_template, SEGMENT_SLOTS),
            ("figure", self.figure, FIGURE_SLOTS),
            ("silhouette", self.silhouette, SILHOUETTE_SLOTS),
        ):
            if unknown := _slots(template) - allowed:
                raise ValueError(f"{name} uses unknown slots: {', '.join(sorted(unknown))}")
        looks = [*self.field.reactions.values(), self.field.neutral]
        if unknown := {camera for look in looks for camera in look.cameras} - set(
            self.camera_moves
        ):
            raise ValueError(
                f"field names camera moves the theme lacks: {', '.join(sorted(unknown))}"
            )
        return self


# How a voice model takes spoken direction: not at all, through OpenAI's or Google's
# provider options, or as a bracketed tag at the start of the text.
DirectionStyle = Literal["none", "openai", "google", "inline"]


class VoiceCandidate(ImmutableModel):
    model: str
    voice: str | None
    direction_style: DirectionStyle = "none"
    # Speak with the theme's master recording (cloning) instead of the model's own voice.
    clone: bool = False


class VoiceDesign(ImmutableModel):
    """One attempt at designing the channel's own narrator: a model and base voice, shaped by
    a written description of who is speaking."""

    model: str
    voice: str | None
    direction_style: DirectionStyle
    description: str


# Fewer recorded takes than this and the voice's own pace is not trusted yet.
MIN_MEASURED_TAKES = 8


class VoicePace(ImmutableModel):
    """What the locked voice actually does, measured from its recorded takes (the learning
    store's `narration.jsonl`); never set by hand."""

    takes: int
    # The voice's own speed, before any stretch.
    natural_median: float
    # The pace a passage comes out at, each take brought towards `words_per_minute` no
    # further than `tempo_range` allows: the median over the measured takes.
    delivered: float
    # The share of takes that fall short of the delivered pace by more than the length
    # tolerance, and so are recorded again.
    short: float


class VoiceSpec(ImmutableModel):
    """The locked narrator. Every narration uses exactly this model and voice (or clip)."""

    model: str
    voice: str | None
    reference_audio: str | None
    reference_transcript: str | None
    direction_style: DirectionStyle = "none"
    # The rate every passage is brought to, whatever speed the voice model happened to
    # take it at: each take is measured and sped up or slowed (pitch kept) to match, so
    # the whole narration keeps one pace. The hook runs a little slower, at `hook_pace`.
    words_per_minute: float = Field(gt=60, lt=260)
    hook_pace: float = Field(gt=0.5, le=1.2)
    # The most a take may be slowed or sped up to reach its rate. Past about 1.2x a
    # passage audibly lurches against its neighbours (docs/narration.md).
    tempo_range: tuple[float, float]
    # Fresh takes recorded when one would need more than `tempo_range` allows; the take
    # needing the least adjustment is kept.
    retakes: int = Field(ge=0, le=3)
    # How every passage is spoken, for voices that take direction. The voice's own
    # phrasing carries the rhythm inside a passage.
    direction: str
    # The breath before a passage, by how it enters: a build runs on, a turn gets a beat.
    pauses: dict[Transition, float]
    tail_seconds: float
    # How far the spoken narration may miss its planned length, either way, before the
    # writer revises it. Inside that, the music is fitted to the narration.
    length_tolerance: float = Field(ge=0, le=0.25)
    lexicon: dict[str, str]
    candidates: list[VoiceCandidate]
    audition_text: str
    # The direction every directable candidate is given in the audition.
    audition_direction: str

    # Attempts at a narrator no one else uses; the chosen one becomes `reference_audio`.
    designs: list[VoiceDesign] = Field(default_factory=list)
    # Filled in when the configuration loads, from the voice's own recorded takes.
    measured: VoicePace | None = None

    @property
    def rate(self) -> float:
        """The pace a narration is sized at: what this voice delivers within the stretch
        limit, once enough takes are measured; the target until then."""
        return self.measured.delivered if self.measured is not None else self.words_per_minute

    @property
    def expected_takes(self) -> float:
        """Takes a passage needs on average: one, and another for each that falls short,
        up to `retakes`. Every allowed take until the voice is measured."""
        if self.measured is None:
            return float(self.retakes + 1)
        return sum(self.measured.short**take for take in range(self.retakes + 1))


class SubtitleSpec(ImmutableModel):
    font_file: str
    font_name: str
    font_size: int
    primary_colour: str
    highlight_colour: str
    outline_colour: str
    outline: int
    shadow: int
    max_words: int = Field(ge=1)
    max_chunk_seconds: float
    uppercase: bool
    margin_bottom: int

    @field_validator("primary_colour", "highlight_colour", "outline_colour")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not HEX_COLOUR.match(value):
            raise ValueError(f"Expected a #RRGGBB colour, got {value!r}")
        return value


class MusicSpec(ImmutableModel):
    """One locked music bed for every video, chosen once by audition, like the voice."""

    # The chosen bed, relative to the theme folder; until one is locked, each video's
    # music is generated from `prompt`.
    track: str | None = None
    prompt: str
    # Endings added to `prompt` to give the audition distinct candidates.
    variations: list[str] = Field(default_factory=list)
    # The music bed sits this far below the voice, measured, before ducking under speech.
    below_voice_db: float = Field(ge=6)
    # How long the music plays on after the last line: the story ends inside the track.
    outro_seconds: tuple[float, float] = (1.0, 6.0)
    # Ducking under speech: how hard (ratio), and how gently it eases down and back up,
    # in milliseconds. Slow attack and release keep the music from pumping between lines.
    duck_attack_ms: float = 150
    duck_release_ms: float = 1200
    duck_threshold: float
    duck_ratio: float
    loudness_lufs: float
    true_peak_db: float


class RhythmSpec(ImmutableModel):
    """How a told story is shaped, measured on a reference narration the page admires
    (numbers only; never its words). Guidance for the writer and the flow judgement,
    never a gate."""

    sentence_words_mean: float
    sentence_words_spread: float
    # Shares of sentences that are very short (four words or fewer) and long (twenty or
    # more). How often to ask a question is deliberately not a number: questions are
    # earned by the story, never inserted to meet a share.
    short_share: float = Field(ge=0, le=1)
    long_share: float = Field(ge=0, le=1)
    # Where the numbers came from.
    source: str


class StoryWeights(ImmutableModel):
    """The open weights that choose and place a story's statements (see `story_weights.py`).
    Readable numbers, meant to be fitted to a person's verdicts as they accumulate."""

    # How far each kind of claim can be stated as fact (0 to 1), and the cost of resting
    # on a single source.
    evidence: dict[Literal["verified", "reported", "disputed", "inference", "unsupported"], float]
    single_source_penalty: float = Field(ge=0, le=1)
    # Evidence at or above this counts in full; below it, a claim's score is scaled down.
    full_evidence: float = Field(gt=0, le=1)
    # State a claim plainly at or above `assert_from`, attributed at or above
    # `attribute_from`, and otherwise only as a question.
    assert_from: float = Field(ge=0, le=1)
    attribute_from: float = Field(ge=0, le=1)
    # A beat whose strongest claim is worth at least this is told with feeling.
    feeling_from: float = Field(ge=0, le=1)
    # Where, as a share of the narration, the strongest beat after the hook should start:
    # around the music's peak.
    turn_window: tuple[float, float]
    # Seconds of narration each story role may take (shortest, longest). A claim's place in
    # its band comes from its score and how many claims rest on it; a beat gets its claims'
    # time plus `transition_seconds`, and never less than `beat_floor_seconds`.
    role_seconds: dict[StoryRole, tuple[float, float]]
    transition_seconds: float = Field(ge=0)
    beat_floor_seconds: float = Field(ge=0)


class WritingSpec(ImmutableModel):
    """How the narration is written: one exact limit, the rhythm to aim for, and the
    weights that place and size its statements."""

    # The voice the narration should have, in a sentence; Jev judges scripts against it.
    voice: str
    # Lines judged solemn or aphoristic the whole script may carry.
    max_weighty_lines: int = Field(ge=0)
    rhythm: RhythmSpec
    weights: StoryWeights


class StagingSpec(ImmutableModel):
    """How the channel's 3D shots are drawn: a look by name (the engine's in
    `content/blender/blocks/looks/`, or the channel's own in `<theme>/blender/looks/`) and
    the settings it takes, which set the feel."""

    look: str = "plain"
    look_settings: dict[str, str | float | int | bool] = {}


class ThemeSpec(ImmutableModel):
    name: str
    # The formats the channel makes, by name, and the one in use: in theme.json, the
    # default's name; a run may pick another (`Theme.with_format`).
    formats: dict[str, FormatSpec]
    format: FormatSpec
    palette: dict[str, str]
    visual: VisualSpec
    references: list[str]
    writing: WritingSpec
    voice: VoiceSpec
    subtitles: SubtitleSpec
    music: MusicSpec
    staging: StagingSpec = StagingSpec()

    @model_validator(mode="before")
    @classmethod
    def _format_by_name(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("format"), str):
            formats = data.get("formats", {})
            if data["format"] not in formats:
                raise ValueError(f"The default format {data['format']!r} is not in formats")
            return {**data, "format": formats[data["format"]]}
        return data

    @field_validator("palette")
    @classmethod
    def _palette_is_hex(cls, value: dict[str, str]) -> dict[str, str]:
        if bad := [name for name, colour in value.items() if not HEX_COLOUR.match(colour)]:
            raise ValueError(f"Palette colours must be #RRGGBB: {', '.join(bad)}")
        return value


class Theme:
    """A loaded theme: its spec, its skill text, and paths resolved against its folder."""

    def __init__(self, root: Path, spec: ThemeSpec, skill: str) -> None:
        self.root = root
        self.spec = spec
        self.skill = skill

    @property
    def references(self) -> list[Path]:
        return [self.root / reference for reference in self.spec.references]

    def with_format(self, name: str) -> "Theme":
        """The theme making `name` videos: its frame, lengths and subtitles."""
        if name not in self.spec.formats:
            raise ThemeError(
                f"No format {name!r}; this theme makes: {', '.join(self.spec.formats)}"
            )
        chosen = self.spec.formats[name]
        subtitles = self.spec.subtitles.model_copy(
            update={
                key: value
                for key, value in (
                    ("font_size", chosen.subtitle_font_size),
                    ("max_words", chosen.subtitle_max_words),
                    ("margin_bottom", chosen.subtitle_margin_bottom),
                )
                if value is not None
            }
        )
        spec = self.spec.model_copy(update={"format": chosen, "subtitles": subtitles})
        return Theme(self.root, spec, self.skill)

    @property
    def font_file(self) -> Path:
        return self.root / self.spec.subtitles.font_file

    @property
    def music_track(self) -> Path | None:
        track = self.spec.music.track
        return None if track is None else self.root / track

    @property
    def reference_audio(self) -> Path | None:
        clip = self.spec.voice.reference_audio
        return None if clip is None else self.root / clip

    @property
    def locks(self) -> list[Path]:
        """The locked recordings, the narrator's master voice and the music bed."""
        return [path for path in (self.reference_audio, self.music_track) if path is not None]

    def neutral_field(self) -> dict[str, str]:
        """Field wording for a scene with no measured feeling."""
        neutral = self.spec.visual.field.neutral
        return {
            "field_frame": neutral.frame[1],
            "field_light": neutral.light[1],
            "field_motion": neutral.motion[1],
        }

    def keyframe_prompt(
        self,
        anchor: SceneAnchor,
        *,
        silhouette: bool = False,
        field: Mapping[str, str] | None = None,
    ) -> str:
        visual = self.spec.visual
        return _render(
            visual.keyframe_template,
            {
                "style": visual.style,
                "texture": visual.texture,
                "lighting": visual.lighting,
                "avoid": visual.avoid,
                **anchor.model_dump(exclude={"figure"}),
                "subject": self.drawn_subject(anchor, silhouette=silhouette),
                "key_elements": ", ".join(anchor.key_elements),
                **(field or self.neutral_field()),
                "frame": self.spec.format.frame,
                "orientation": self.spec.format.orientation,
            },
        )

    def segment_prompt(
        self,
        anchor: SceneAnchor,
        *,
        camera: str,
        motion: str,
        morph_bridge: str,
        next_anchor: SceneAnchor | None,
        silhouette: bool = False,
        field: Mapping[str, str] | None = None,
        shift: str | None = None,
    ) -> str:
        visual = self.spec.visual
        values = {
            "style": visual.style,
            "texture": visual.texture,
            "lighting": visual.lighting,
            "morph": visual.morph,
            "avoid": visual.morph_avoid,
            "subject": self.drawn_subject(anchor, silhouette=silhouette),
            "setting": anchor.setting,
            "camera": visual.camera_moves[camera].describe,
            "motion": motion,
            "morph_bridge": morph_bridge,
            "next_subject": (
                self.drawn_subject(next_anchor, silhouette=silhouette) if next_anchor else ""
            ),
            "next_setting": next_anchor.setting if next_anchor else "",
            **(field or self.neutral_field()),
            "shift": shift or visual.field.shifts["sideways"],
            "frame": self.spec.format.frame,
            "orientation": self.spec.format.orientation,
        }
        template = visual.segment_template if next_anchor else visual.final_segment_template
        return _render(template, values)

    def drawn_subject(self, anchor: SceneAnchor, *, silhouette: bool) -> str:
        """The subject as the image model should draw it: a public figure in the theme's way
        of drawing people, or as a silhouette when a portrait was refused or garbled."""
        figure = anchor.figure
        if figure is None:
            return anchor.subject
        visual = self.spec.visual
        if silhouette:
            return _render(
                visual.silhouette, {"subject": anchor.subject, "silhouette": figure.silhouette}
            )
        return _render(
            visual.figure,
            {"subject": anchor.subject, "name": figure.name, "likeness": figure.likeness},
        )

    def spoken_text(self, text: str, say_as: Mapping[str, str] | None = None) -> str:
        """Write narration as it should be pronounced: the theme's lexicon, then the
        script's own `say_as`."""
        for written, spoken in {**self.spec.voice.lexicon, **(say_as or {})}.items():
            text = re.sub(rf"\b{re.escape(written)}\b", spoken, text)
        return text

    def speaker(self, direction: VoiceDirection) -> Callable[[str], str]:
        """`spoken_text` for one script, with its own pronunciations."""
        return lambda text: self.spoken_text(text, direction.say_as)


def theme_guidance(theme: Theme) -> str:
    """The theme's skill, the exact camera vocabulary scenes must choose from, and the
    rhythm of a narration this channel admires."""
    moves = "\n".join(
        f"- `{name}`: {move.describe}" for name, move in theme.spec.visual.camera_moves.items()
    )
    suits = "\n".join(
        f"- {reaction.replace('_', ' ')}: {', '.join(look.cameras)}"
        for reaction, look in theme.spec.visual.field.reactions.items()
    )
    rhythm = theme.spec.writing.rhythm
    return (
        f"{theme.skill}\n\n## Camera moves (use these names exactly)\n\n{moves}\n\n"
        f"## Which moves suit each reaction\n\n{suits}\n\n"
        "## Rhythm to aim for (measured on a narration this theme admires; a guide, not a rule)"
        f"\n\n- Sentences average about {rhythm.sentence_words_mean:.0f} words, and vary a lot "
        f"(spread about {rhythm.sentence_words_spread:.0f}).\n"
        f"- About {rhythm.short_share:.0%} are very short (four words or fewer) and "
        f"{rhythm.long_share:.0%} long (twenty or more): long ones carry the listener, short "
        "ones land."
    )


def load_theme(root: Path) -> Theme:
    spec_path, skill_path = root / "theme.json", root / "SKILL.md"
    if not spec_path.is_file() or not skill_path.is_file():
        raise ThemeError(f"A theme needs theme.json and SKILL.md: {root}{PULL_HINT}")
    try:
        spec = ThemeSpec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ThemeError(f"Invalid theme {root.name}: {exc}") from exc
    theme = Theme(root, spec, skill_path.read_text(encoding="utf-8").strip())
    missing = [path for path in [theme.font_file, *theme.references] if not path.is_file()]
    missing += [path for path in theme.locks if not path.is_file()]
    if missing:
        raise ThemeError(
            "Theme files are missing: " + ", ".join(str(path) for path in missing) + PULL_HINT
        )
    return theme


def with_measured_voice(theme: Theme, narration_log: Path) -> Theme:
    """The theme with its voice's pace measured from every recorded take of it in
    `narration_log` (the learning store's `narration.jsonl`, filled after each run)."""
    voice, clip = theme.spec.voice, theme.reference_audio
    reference = (
        hashlib.sha256(clip.read_bytes()).hexdigest()
        if clip is not None and clip.is_file()
        else None
    )
    natural = []
    if narration_log.is_file():
        for line in narration_log.read_text(encoding="utf-8").splitlines():
            take = json.loads(line) if line.strip() else None
            if take and (take["model"], take["voice"], take["reference"]) == (
                voice.model,
                voice.voice,
                reference,
            ):
                natural.append(len(take["text"].split()) / take["seconds"] * 60)
    measured = measure_voice(voice, natural)
    if measured is None:
        return theme
    spec = theme.spec.model_copy(update={"voice": voice.model_copy(update={"measured": measured})})
    return Theme(theme.root, spec, theme.skill)


def measure_voice(voice: VoiceSpec, natural: Sequence[float]) -> VoicePace | None:
    """The voice's measured pace, from the natural pace of its takes; None with too few."""
    if len(natural) < MIN_MEASURED_TAKES:
        return None
    low, high = voice.tempo_range
    target = voice.words_per_minute
    delivered = [max(min(target, pace * high), pace * low) for pace in natural]
    typical = statistics.median(delivered)
    floor = typical * (1 - voice.length_tolerance)
    return VoicePace(
        takes=len(natural),
        natural_median=round(statistics.median(natural), 1),
        delivered=round(typical, 1),
        short=round(sum(pace < floor for pace in delivered) / len(delivered), 3),
    )


def new_theme(starter: Path, target: Path) -> Path:
    """A new theme folder copied from the starter, named after its folder, ready to edit."""
    if target.exists():
        raise ThemeError(f"{target} already exists")
    shutil.copytree(starter, target)
    spec_path = target / "theme.json"
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    data["name"] = target.name
    spec_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def narration_direction(theme: Theme, script: VoiceDirection | None, phase_id: str) -> str | None:
    """How one passage is spoken: the script's tone and its beat's own direction (or the
    script's delivery), from the writer; the theme's direction only for a script that gives
    none. None for voices that take no direction."""
    voice = theme.spec.voice
    if voice.direction_style == "none":
        return None
    if script is None:
        return voice.direction
    words = [script.tone.strip(), (script.beats.get(phase_id) or script.delivery).strip()]
    return "; ".join(word for word in words if word) or voice.direction


def _slots(template: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(template) if field}


def _render(template: str, values: dict[str, Any]) -> str:
    return template.format_map({slot: values[slot] for slot in _slots(template)})
