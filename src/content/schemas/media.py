"""Records of produced media: narration, timing, the score, rendered assets, the result.
Files live in the asset cache; records hold their paths."""

from typing import Literal

from content.schemas.base import ImmutableModel
from content.schemas.judgement import Judgement
from content.schemas.perception import Observation

SectionLabel = Literal["intro", "build", "peak", "outro"]


class Word(ImmutableModel):
    text: str
    start: float
    end: float


class NarrationClip(ImmutableModel):
    """One passage, spoken in one take."""

    passage_id: str
    unit_ids: list[str]
    # The pronounced form sent to the voice; a clip is current only while it and the
    # target rate match.
    spoken_text: str
    words_per_minute: float
    # How the passage was directed: a changed direction is recorded again.
    direction: str | None = None
    # The take numbering it was recorded from: a person asking for a fresh take moves it on.
    first_take: int = 0
    # The speed-up applied to the voice model's take to reach that rate (pitch kept).
    tempo: float
    path: str
    duration: float
    # Words as transcribed from the clip, timed from its start. Empty when unknown.
    heard: list[Word]
    # Problems found by comparing what was heard with what was written.
    issues: list[str]


class SceneTiming(ImmutableModel):
    """A scene on the timeline: its keyframe, moved slowly by its camera (a motion still)."""

    scene_id: str
    start: float
    end: float


class TransitionTiming(ImmutableModel):
    """An AI morph from one scene's keyframe into the next, across the join between them."""

    from_scene_id: str
    to_scene_id: str
    start: float
    seconds: float


class Budget(ImmutableModel):
    """What the run has spent and is projected to spend, against its cap."""

    cap: float
    spent: float
    # Keyframes and morphs still to come, with their perception and judging.
    keyframes: float
    morphs: int
    transitions: float

    @property
    def projected(self) -> float:
        return round(self.spent + self.keyframes + self.transitions, 2)


class ScoreSpan(ImmutableModel):
    """Where on the video's timeline a section of the music bed plays."""

    label: SectionLabel
    start: float
    end: float


class Timeline(ImmutableModel):
    narration_path: str
    subtitles_path: str
    total_seconds: float
    scenes: list[SceneTiming]
    # The music cut to the story; empty when the bed has no map and simply loops.
    score: list[ScoreSpan] = []
    # The scene boundaries that morph through the AI video model.
    transitions: list[TransitionTiming] = []
    # Where each narration passage starts, so a review can play it from there.
    passage_starts: dict[str, float] = {}


class ColourCheck(ImmutableModel):
    """A keyframe's measured light and colour against what its scene's field asked for.

    `pleasure` and `arousal` are the field's point on the circumplex (-1 to 1); the
    targets come from them by Valdez and Mehrabian's colour-emotion model. Kept with each
    keyframe so the constants can later be refitted to what the image model really does.
    """

    pleasure: float
    arousal: float
    # Mean luma (0-255) and mean saturation (0-181), as ffmpeg's signalstats measures them.
    target_brightness: float
    target_saturation: float
    brightness: float
    saturation: float
    # Red chroma minus blue chroma: positive is warm, negative is cool.
    warmth: float


class RenderedAsset(ImmutableModel):
    """One keyframe or video segment, with what was seen in it and how Jev judged it."""

    scene_id: str
    attempt: int
    prompt: str
    # Identifies everything the asset was generated from; a changed input means stale.
    signature: str
    path: str
    observations: list[Observation]
    judgements: list[Judgement]
    # Exact problems found by code (hard cuts, frozen or black frames, refusals, tone).
    issues: list[str]
    # A public figure was drawn as a silhouette after the portrait failed.
    silhouette: bool = False
    # Keyframes only: measured colour against the scene's target.
    colour: ColourCheck | None = None
    # A staged scene: the 3D layout its picture was drawn over (the guide's render job, as
    # JSON; `docs/3d-reuse.md`).
    guide: str = ""
    # A moving picture: its shot (the render job, as JSON); and its first and last frames,
    # which the morphs into and out of it start and end on.
    shot: str = ""
    first_frame: str = ""
    last_frame: str = ""

    @property
    def rendered(self) -> bool:
        """False when the model refused and there is no file."""
        return bool(self.path)

    @property
    def failed(self) -> bool:
        return bool(self.issues) or any(
            judgement.blocking and judgement.outcome == "fail" for judgement in self.judgements
        )


class ProductionResult(ImmutableModel):
    video_path: str
    narration_path: str
    subtitles_path: str
    music_path: str | None
    contact_sheet_path: str
    duration: float
    scenes: list[SceneTiming]
    # Whoever must be credited where the video is published (the makers of CC BY models).
    credits: list[str] = []


class Arrangement(ImmutableModel):
    """The track as a sequence of its phrases (indices into the map's sections)."""

    phrases: list[int]
    seconds: float
    # When, in the arranged music, the peak's first bar plays.
    peak_at: float
    # Output time of each phrase's first bar, in play order.
    phrase_starts: list[float]
