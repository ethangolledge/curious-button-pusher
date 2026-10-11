"""Production's shared workbench: the stages' common dependencies and steps.

Generation and assembly are code. Taste stays with Jev: after each render a vision model
describes what was made, and Jev's questions judge that description against the
storyboard. Every paid call goes through the asset cache."""

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypedDict

from content.agents.base import load_prompt
from content.blender.job import Job, Join, Report
from content.config import ProductionConfig
from content.judging.judge import Judge
from content.judging.outcomes import correction_line
from content.production import assemble, focus
from content.production.budget import (
    Pricing,
    past_averages,
    spent,
)
from content.production.media import GenerationRefused, MediaProvider
from content.production.music_map import MusicMap, map_for
from content.production.score import (
    render,
)
from content.providers.base import Usage
from content.providers.blender import Renderer
from content.providers.cache import AssetCache, file_digest
from content.providers.images import ImageSource
from content.schemas.judgement import JudgedStage
from content.schemas.media import (
    Arrangement,
    RenderedAsset,
    Timeline,
)
from content.schemas.perception import Observation
from content.schemas.story import Feeling
from content.schemas.visuals import Scene, SceneAnchor
from content.staging.catalogue import Catalogue
from content.staging.resolve import FindModel
from content.state import CallRecord, ContentState, call_record
from content.story.field import (
    ripple_tint,
    story_fields,
)
from content.theme import Theme

# Bumped whenever the code that renders the local look (glide, breathing, morph effects,
# texture) changes, so cached clips made the old way are rebuilt. A change to the theme's
# motion settings rebuilds what it affects on its own: they are part of each clip's key.
LOOK = "focus-breathing-1"
# Bumped whenever the code that builds or renders 3D shots changes in a way the job does not
# show (a block, the foundation, a look), so cached shots are rendered again.
STAGING_LOOK = "staging-1"
# A staged scene's picture is shown whole, from its centre; its animatic draft is rendered at
# half size and this many frames a second (the cut's rate is made up by repeating them).
CENTRE = (0.5, 0.5)
WHOLE = assemble.Framing(1.0, 0.5, 0.5)
DRAFT_FPS = 12

# What the vision model is told when it describes rendered frames for Jev.
PERCEPTION_PROMPT = Path(__file__).with_name("perception_prompt.md")


class NarrationTask(TypedDict):
    passage_id: str
    unit_ids: list[str]
    spoken_text: str
    # The rate the take is brought to: the voice's, a little slower for the hook.
    words_per_minute: float
    # How the passage is spoken: its beat's direction from the script, and any pause or
    # emphasis the person asked for.
    direction: str | None
    # Where its take numbering starts: past every take a person already heard and rejected.
    first_take: int


class RenderTask(TypedDict):
    """Everything one keyframe or segment render needs; Send payloads carry no state."""

    scene_id: str
    attempt: int
    prompt: str
    signature: str
    anchor: str
    next_anchor: str | None
    first_frame: str | None
    last_frame: str | None
    clip_seconds: int
    silhouette: bool
    # Real photographs the keyframe is drawn from, after the theme's style images.
    references: list[str]
    # What the scene's emotional field asks of the image, checked after rendering.
    expected_framing: str
    expected_temperature: str | None
    # Keyframes only: the field's (pleasure, arousal), which sets its colour targets.
    field_point: tuple[float, float] | None
    expected_shift: str | None
    # A staged scene's keyframe: the render job (JSON) instead of a prompt to an image model.
    shot: str | None
    # A rendered join: the transition job (JSON) instead of a prompt to the video model.
    join: str | None


@dataclass(frozen=True)
class ShotWindow:
    """Where, in seconds from the start of a staged scene's shot, its own picture holds
    (`held_from` to `out_from`) and the morph out of it begins (`out_from`)."""

    seconds: float
    held_from: float
    out_from: float

    @property
    def held(self) -> float:
        return self.out_from - self.held_from

    def frame(self, at: float, fps: int) -> int:
        """The shot's frame number at `at` seconds (frames count from 1)."""
        return min(max(round(at * fps) + 1, 1), max(round(self.seconds * fps), 1))


class Studio:
    """What every production stage shares: the configuration, theme, media provider, judge
    and asset cache, and the steps more than one stage takes (fetching through the cache,
    describing frames, rendering a still, the music and the mix)."""

    def __init__(
        self,
        *,
        config: ProductionConfig,
        theme: Theme,
        media: MediaProvider,
        judge: Judge,
        image_sources: Sequence[ImageSource],
        renderer: Renderer | None = None,
        catalogue: Catalogue | None = None,
        find_model: FindModel | None = None,
    ) -> None:
        self.config = config
        self.theme = theme
        self.media = media
        self.judge = judge
        self.perception_instructions = load_prompt(PERCEPTION_PROMPT)
        self.image_sources = image_sources
        self.cache = AssetCache(config.cache_directory)
        # Staged scenes (`production.pictures` "staged"): Blender, and what shots are made of.
        self.renderer = renderer
        self.catalogue = catalogue
        # What a staged scene lacks, found online and taken automatically (None: never).
        self.find_model = find_model

    def perceive(self, images: Sequence[Path]) -> tuple[list[Observation], list[CallRecord]]:
        """Describe rendered frames (cached by their content) so Jev can judge them."""
        model = self.config.vision_model

        def describe() -> tuple[bytes, Usage]:
            observations, usage = self.media.perceive(
                model=model, instructions=self.perception_instructions, images=images
            )
            return json.dumps([o.model_dump() for o in observations]).encode(), usage

        stored, calls = self.fetch(
            "perception",
            {"model": model, "images": [file_digest(path) for path in images]},
            ".json",
            "perception",
            describe,
            about=f"{len(images)} frame(s) described for Jev",
        )
        observations = [Observation.model_validate(item) for item in json.loads(stored.read_text())]
        if len(observations) != len(images):
            raise RuntimeError(f"{model} described {len(observations)} of {len(images)} images")
        return observations, calls

    def theme_look(self) -> str:
        visual = self.theme.spec.visual
        palette = ", ".join(self.theme.spec.palette)
        return f"{visual.style}. {visual.texture}. {visual.lighting}. Palette: {palette}."

    def current(self, state: ContentState, kind: JudgedStage) -> list[RenderedAsset]:
        """The asset of every current scene, in scene order."""
        visuals = required(state.get("visual_package"), "a storyboard")
        assets = state.get("keyframes", {}) if kind == "keyframes" else state.get("segments", {})
        missing = [scene.scene_id for scene in visuals.scenes if scene.scene_id not in assets]
        if missing:
            raise ValueError(f"No {kind} rendered for: {', '.join(missing)}")
        return [assets[scene.scene_id] for scene in visuals.scenes]

    def video_segments(self, state: ContentState) -> list[RenderedAsset]:
        """The AI morph of every transition on the timeline, in order (keyed by the scene
        each one leaves)."""
        timeline = required(state.get("timeline"), "a timeline")
        segments = state.get("segments", {})
        wanted = [transition.from_scene_id for transition in timeline.transitions]
        if missing := [scene_id for scene_id in wanted if scene_id not in segments]:
            raise ValueError(f"No transitions rendered after: {', '.join(missing)}")
        return [segments[scene_id] for scene_id in wanted]

    @staticmethod
    def retry_possible(assets: Sequence[RenderedAsset], attempts: int) -> bool:
        return any(asset.failed and asset.attempt + 1 < attempts for asset in assets)

    def fetch(
        self,
        kind: str,
        request: dict[str, Any],
        suffix: str,
        operation: str,
        produce: Callable[[], tuple[bytes, Usage]],
        about: str = "",
    ) -> tuple[Path, list[CallRecord]]:
        """A paid generation through the cache; `about` says what it is, for the cache's
        readable index."""
        started = time.perf_counter()
        path, usage = self.cache.fetch(
            kind, request, suffix, produce, refusal=GenerationRefused, about=about
        )
        if usage is None:
            return path, []
        return path, [call_record(operation, usage, time.perf_counter() - started)]

    def derived(self, kind: str, parts: Sequence[str], suffix: str) -> Path:
        """A cache path for a file computed locally from other files; build it if missing."""
        key = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]
        path = self.cache.root / kind / f"{key}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def fields(self, state: ContentState) -> dict[str, Feeling]:
        return story_fields(
            state.get("script_package"),
            state.get("visual_package"),
            state.get("research_pack"),
            state.get("unit_feelings", {}),
            state.get("unit_seconds", {}),
        )

    def music(
        self, timeline: Timeline, arrangement: Arrangement | None
    ) -> tuple[Path | None, list[CallRecord]]:
        """The theme's locked bed, fitted to this video; generated only when none is locked."""
        track = self.theme.music_track
        music = self.music_map()
        if track is not None and music is not None and arrangement is not None:
            key = ",".join(str(index) for index in arrangement.phrases)
            scored = self.derived("score", [file_digest(track), key], ".wav")
            if not scored.is_file():
                render(track, music, arrangement, scored)
            return scored, []
        if track is not None:
            bed = self.derived(
                "music-bed", [file_digest(track), f"{timeline.total_seconds:.3f}"], ".wav"
            )
            if not bed.is_file():
                assemble.music_bed(track, timeline.total_seconds, bed)
            return bed, []
        model = self.config.music_model
        if model is None:
            return None, []
        prompt = self.theme.spec.music.prompt
        return self.fetch(
            "music",
            {"model": model, "prompt": prompt, "seconds": round(timeline.total_seconds)},
            ".audio",
            "music",
            lambda: self.media.music(model=model, prompt=prompt, seconds=timeline.total_seconds),
            about=f"music bed, {timeline.total_seconds:.0f} s: {prompt}",
        )

    def music_map(self) -> MusicMap | None:
        """The locked bed's beat grid and sections, when it has been mapped."""
        return map_for(self.theme.music_track)

    def mix(self, timeline: Timeline, music: Path | None) -> Path:
        spec = self.theme.spec
        inputs = [file_digest(Path(timeline.narration_path)), file_digest(music) if music else ""]
        mix = self.derived("mix", [*inputs, spec.music.model_dump_json()], ".m4a")
        if not mix.is_file():
            assemble.mix_audio(Path(timeline.narration_path), music, spec.music, mix)
        return mix

    def picture(
        self,
        timeline: Timeline,
        scenes: Sequence[Scene],
        keyframes: Sequence[RenderedAsset],
        segments: dict[str, RenderedAsset],
        fields: Mapping[str, Feeling],
        *,
        final: bool = True,
    ) -> Path:
        """The picture track: every scene is its keyframe moved slowly by the scene's
        camera (or, staged, its 3D shot, whose camera is its own), and the AI morph into the
        next scene plays across the join between them, taking its time from both sides so
        every scene still starts on its words. Joins dissolve, and the last picture holds
        while the music plays out. The animatic has no morphs yet, so its pictures simply
        dissolve, and its shots are quick drafts (`final` False)."""
        spec = self.theme.spec.format
        motion = self.theme.spec.visual.motion
        images = {asset.scene_id: Path(asset.path) for asset in keyframes}
        shots = {asset.scene_id: asset for asset in keyframes if asset.shot}
        focals = {
            scene.scene_id: CENTRE
            if scene.scene_id in shots
            else self.focal(scene, images[scene.scene_id])
            for scene in scenes
            if scene.scene_id in images
        }
        # A shot's frame is shown whole: the morphs into and out of it neither zoom nor pan.
        glides = {
            scene.scene_id: (WHOLE, WHOLE)
            if scene.scene_id in shots
            else assemble.glide(
                self.theme.spec.visual.camera_moves[scene.camera], focals[scene.scene_id]
            )
            for scene in scenes
            if scene.scene_id in focals
        }
        starts = {timing.scene_id: timing.start for timing in timeline.scenes}
        # Each rendered morph, with the seconds it takes from the scene before and after.
        morphs = {
            t.from_scene_id: (t, segments[t.from_scene_id], starts[t.to_scene_id] - t.start)
            for t in timeline.transitions
            if t.from_scene_id in segments
        }
        entering = {t.to_scene_id: t.seconds - taken for t, _, taken in morphs.values()}
        clips: list[tuple[Path, float]] = []
        joins: list[float] = []
        after_morph = False
        for timing in timeline.scenes:
            leaving = morphs.get(timing.scene_id)
            seconds = (
                timing.end
                - timing.start
                - entering.get(timing.scene_id, 0.0)
                - (leaving[2] if leaving else 0.0)
            )
            image = images[timing.scene_id]
            start, end = glides[timing.scene_id]
            focal = focals[timing.scene_id]
            # The ripples take on the scene's emotional colour, faintly.
            tint = ripple_tint(
                fields.get(timing.scene_id), self.theme.spec.visual.field, motion.breath.tint
            )
            if timing.scene_id in shots:
                skip = self.window(timeline, timing.scene_id).held_from
                still = self._shot_clip(shots[timing.scene_id], seconds, skip, tint, final=final)
            else:
                still = self._still(image, seconds, start, end, focal, tint)
            if clips:
                # A morph meets its stills frame to frame; two stills dissolve.
                joins.append(0.0 if after_morph else motion.dissolve_seconds)
            clips.append((still, seconds))
            after_morph = leaving is not None
            if leaving:
                transition, segment, _ = leaving
                source = Path(segment.path)
                # The camera carries on from this still's last framing to the next one's first.
                path = (end, glides[transition.to_scene_id][0])
                morph = self.derived(
                    "conformed",
                    [
                        file_digest(source),
                        f"{transition.seconds:.3f}",
                        repr(path),
                        motion.morph.model_dump_json(),
                        LOOK,
                    ],
                    ".mp4",
                )
                if not morph.is_file():
                    # A morph squeezed between short scenes plays faster.
                    assemble.conform_segment(
                        source,
                        morph,
                        seconds=transition.seconds,
                        speed=transition.seconds / self.config.transition_seconds,
                        start=path[0],
                        end=path[1],
                        layer=motion.morph,
                        width=spec.width,
                        height=spec.height,
                        fps=spec.fps,
                    )
                joins.append(0.0)
                clips.append((morph, transition.seconds))
        parts = [f"{file_digest(clip)}@{seconds:.3f}" for clip, seconds in clips]
        cut = self.derived("cut", [*parts, repr(joins)], ".mp4")
        if not cut.is_file():
            assemble.dissolve_join(clips, cut, joins=joins, fps=spec.fps)
        coda = timeline.total_seconds - timeline.scenes[-1].end
        held = cut
        if coda > 0.05:
            held = self.derived("held", [*parts, f"{coda:.3f}"], ".mp4")
            if not held.is_file():
                assemble.hold_ending(cut, coda, held)
        textured = self.derived(
            "textured", [file_digest(held), motion.texture.model_dump_json(), LOOK], ".mp4"
        )
        if not textured.is_file():
            assemble.texture(
                held,
                textured,
                spec=motion.texture,
                breath_seconds=motion.breath.seconds,
                fps=spec.fps,
            )
        return textured

    def _still(
        self,
        image: Path,
        seconds: float,
        start: assemble.Framing,
        end: assemble.Framing,
        focal: tuple[float, float],
        tint: tuple[str, float] | None,
    ) -> Path:
        """A keyframe moved by its camera, breathing, for `seconds`."""
        spec = self.theme.spec.format
        breath = self.theme.spec.visual.motion.breath
        still = self.derived(
            "still",
            [
                file_digest(image),
                f"{seconds:.3f}",
                repr((start, end, focal)),
                breath.model_dump_json(),
                repr(tint),
                LOOK,
            ],
            ".mp4",
        )
        if not still.is_file():
            assemble.motion_clip(
                image, seconds, start, end, focal, still, breath=breath,
                width=spec.width, height=spec.height, fps=spec.fps, tint=tint,
            )  # fmt: skip
        return still

    def _shot_clip(
        self,
        asset: RenderedAsset,
        seconds: float,
        skip: float,
        tint: tuple[str, float] | None,
        *,
        final: bool,
    ) -> Path:
        """A staged scene's clip: its 3D shot rendered whole (a quick draft for the
        animatic, full quality for the cut), breathing and tinted as a keyframe would be."""
        spec = self.theme.spec.format
        breath = self.theme.spec.visual.motion.breath
        frames, job = self.shot_frames(asset, final=final)
        clip = self.derived(
            "shotclip",
            [
                job.dumps(),
                STAGING_LOOK,
                f"{seconds:.3f}",
                breath.model_dump_json(),
                repr(tint),
                LOOK,
            ],
            ".mp4",
        )
        if not clip.is_file():
            assemble.shot_clip(
                frames, job.fps, seconds, CENTRE, clip, breath=breath,
                width=spec.width, height=spec.height, fps=spec.fps, tint=tint, skip=skip,
            )  # fmt: skip
        return clip

    def shot_frames(self, asset: RenderedAsset, *, final: bool) -> tuple[Path, Job]:
        """A staged scene's whole shot, rendered (a quick half-size draft for the animatic, or
        full quality), as a folder of numbered frames, with the job that made it."""
        keyed = Job.loads(asset.shot)
        if final:
            job = replace(keyed, quality="final", frames=())
        else:
            job = replace(
                keyed, quality="draft", frames=(), fps=DRAFT_FPS,
                width=keyed.width // 4 * 2, height=keyed.height // 4 * 2,
            )  # fmt: skip
        report = self.render_shot(job)
        if not report.frames:
            raise ValueError(f"{asset.scene_id}: its 3D shot was not rendered: {report.issues}")
        return Path(report.frames[0]).parent, job

    def focal(self, scene: Scene, image: Path) -> tuple[float, float]:
        """Where the scene's focus sits in its keyframe, found once and kept."""
        phrase = scene.focus or re.split(r"[,;:]| in a | in the ", scene.anchor.subject)[0]
        person = scene.anchor.figure is not None
        path = self.derived("focus", [file_digest(image), phrase, str(person)], ".json")
        if not path.is_file():
            point = focus.find(image, phrase, person=person)
            path.write_text(point.model_dump_json(), encoding="utf-8")
        point = focus.FocalPoint.model_validate_json(path.read_text(encoding="utf-8"))
        return point.x, point.y

    def spent(self, state: ContentState) -> float:
        """The run's cost so far; unpriced calls count at past runs' averages."""
        past = past_averages(
            self.config.cache_directory.parent.glob("runs/*/.work/session-*.run.json")
        )
        return spent(state.get("call_log", []), past)

    def staging(self) -> tuple[Renderer, Catalogue] | None:
        """Blender and the catalogue, when this channel stages scenes."""
        if self.config.pictures != "staged" or self.renderer is None or self.catalogue is None:
            return None
        return self.renderer, self.catalogue

    def rendered_joins(self) -> Renderer | None:
        """Blender, when this channel renders its joins instead of buying AI morphs."""
        return self.renderer if self.config.joins == "rendered" else None

    def render_join(self, join: Join) -> Path:
        """A transition rendered once and encoded, kept by everything it is made from."""
        video = self.derived("join", [join.dumps(), STAGING_LOOK], ".mp4")
        if video.is_file():
            return video
        renderer = self.rendered_joins()
        if renderer is None:
            raise ValueError("A rendered join needs Blender (production.joins: rendered)")
        folder = self.derived("joinframes", [join.dumps(), STAGING_LOOK], "")
        report = renderer.render(join, folder)
        assemble.encode_frames(Path(report.frames[0]).parent, join.fps, video)
        return video

    def render_shot(self, job: Job) -> Report:
        """A 3D shot rendered once: kept by everything it is built from (the job, the block
        and look code, and the files of its models), as paid assets are."""
        folder = self.derived("shot", [job.dumps(), STAGING_LOOK], "")
        report = folder / "report.json"
        if report.is_file():
            return Report(**json.loads(report.read_text(encoding="utf-8")))
        staging = self.staging()
        if staging is None:
            raise ValueError("A staged scene needs Blender (production.pictures: staged)")
        return staging[0].render(job, folder)

    def window(self, timeline: Timeline, scene_id: str) -> "ShotWindow":
        """The stretch of time a staged scene's shot covers: from the start of the morph into
        it to the end of the morph out of it, so the morphs play over its moving frames."""
        timing = next(t for t in timeline.scenes if t.scene_id == scene_id)
        into = next((t for t in timeline.transitions if t.to_scene_id == scene_id), None)
        out = next((t for t in timeline.transitions if t.from_scene_id == scene_id), None)
        begins = into.start if into else timing.start
        held_from = (into.start + into.seconds if into else timing.start) - begins
        out_from = (out.start if out else timing.end) - begins
        ends = out.start + out.seconds if out else timing.end
        return ShotWindow(seconds=ends - begins, held_from=held_from, out_from=out_from)

    def pricing(self) -> Pricing:
        return Pricing(
            cap=self.config.max_usd,
            # A staged scene's picture, and a rendered join, are rendered, not bought.
            image_usd=0.0 if self.staging() else self.config.image_usd,
            video_usd_per_second=0.0 if self.rendered_joins() else self.config.video_usd_per_second,
            morph_seconds=self.config.transition_seconds,
        )


def next_attempt(asset: RenderedAsset | None, signature: str, attempts: int) -> int | None:
    """None when the current asset can stand; otherwise the attempt number to render."""
    if asset is None or asset.signature != signature:
        return 0
    if asset.failed and asset.attempt + 1 < attempts:
        return asset.attempt + 1
    return None


def refused(task: RenderTask, refusal: GenerationRefused) -> RenderedAsset:
    return RenderedAsset(
        scene_id=task["scene_id"],
        attempt=task["attempt"],
        prompt=task["prompt"],
        signature=task["signature"],
        path="",
        observations=[],
        judgements=[],
        issues=[f"{task['scene_id']}: the model refused to render it ({refusal})"],
        silhouette=task["silhouette"],
    )


def corrections(assets: Sequence[RenderedAsset]) -> list[str]:
    return [
        *(issue for asset in assets for issue in asset.issues),
        *(
            correction_line(judgement)
            for asset in assets
            for judgement in asset.judgements
            if judgement.blocking and judgement.outcome != "pass"
        ),
    ]


def render_signature(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


def anchor_text(anchor: SceneAnchor) -> str:
    return f"{anchor.subject}, in {anchor.setting}; {', '.join(anchor.key_elements)}"


def decision(stage: str, route: str, notes: list[str], *, structural: bool) -> ContentState:
    return {
        "current_stage": stage,
        "routing_decision": route,
        "revision_notes": notes,
        "structural_blockers": structural,
        "events": [{"stage": stage, "message": f"{stage}: {route}"}],
    }


def required(value: Any, what: str) -> Any:
    if value is None:
        raise ValueError(f"This production stage requires {what}")
    return value
