"""The pictures: how many the budget affords, each scene's keyframe drawn and judged, then the
animatic and story sheet for the Pictures sign-off."""

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from langgraph.types import Send

from content.blender.job import BlockCall, Job
from content.production import assemble, checks
from content.production.budget import (
    scene_allowance,
)
from content.production.media import GenerationRefused
from content.production.story_sheet import write_story_sheet
from content.production.studio import (
    RenderTask,
    ShotWindow,
    Studio,
    anchor_text,
    corrections,
    decision,
    next_attempt,
    refused,
    render_signature,
    required,
)
from content.providers.blender import LocalBlender, people_ready
from content.providers.cache import file_digest
from content.schemas.media import (
    ColourCheck,
    RenderedAsset,
)
from content.schemas.staging import StagedScene
from content.schemas.visuals import Scene
from content.staging.backlog import record_gap
from content.staging.compose import compose
from content.staging.plan import GUIDE, StagingError, job_for, picture_job, staged, unstage
from content.staging.resolve import with_online
from content.state import CallRecord, ContentState, merge_warnings
from content.story.field import (
    circumplex,
    colour_units,
    expected_temperature,
    field_slots,
    look,
)
from content.theme import ToneSpec

# Why a staged scene's layout was not rendered (its checks in Blender failed).
UNBUILT = "its 3D layout was not rendered"
# Image models accept a limited number of references; the theme's style images come first.
MAX_STORY_REFERENCES = 6


class Keyframes(Studio):
    def price_pictures(self, state: ContentState) -> ContentState:
        """Before the storyboard: how many scenes the rest of the budget pays for, and no
        more than the person chose."""
        affordable = scene_allowance(self.spent(state), self.pricing())
        wanted = state.get("scenes_wanted")
        return {"scene_allowance": affordable if wanted is None else min(affordable, wanted)}

    def start_keyframes(self, state: ContentState) -> ContentState:
        """The person approved the narration they heard: remember it, so re-timing the same
        narration after storyboard notes does not ask again."""
        timeline = required(state.get("timeline"), "a timeline")
        return {
            "current_stage": "keyframes",
            "listened_narration": timeline.narration_path,
            "warnings": merge_warnings(state.get("warnings", []), self._prepare_models(state)),
        }

    def _prepare_models(self, state: ContentState) -> list[str]:
        """Before any shot is rendered, what the staged scenes need and the library lacks is
        found online and taken (free; it is kept for every later video). Each model taken
        without a person is named for review."""
        staging = self.staging()
        people = people_ready() and isinstance(staging[0], LocalBlender) if staging else False
        if staging is None or (self.find_model is None and not people):
            return []
        catalogue = staging[1]
        before = set(catalogue.library.models)
        resolve = with_online(catalogue.library, self.find_model, make_people=people)
        visuals = required(state.get("visual_package"), "a storyboard")
        for scene in visuals.scenes:
            shot = staged(scene)
            if shot is not None and shot.staging is not None:
                compose(shot.staging, catalogue.registry, resolve, seed=shot.scene_id)
        taken = [catalogue.library.get(m) for m in sorted(set(catalogue.library.models) - before)]
        return [
            f"Model taken automatically for '{model.names[0]}': {model.describe} by "
            f"{model.author} ({model.source}, {model.licence}, sure {model.score:.2f}). If it "
            f"is wrong: content staging veto {model.model_id}"
            for model in taken
            if model.status == "auto"
        ]

    def keyframe_tasks(self, state: ContentState) -> list[Send] | str:
        visuals = required(state.get("visual_package"), "a storyboard")
        existing = state.get("keyframes", {})
        references = state.get("references", {})
        fields = self.fields(state)
        spec = self.theme.spec.visual.field
        tasks = []
        for scene in visuals.scenes:
            feeling = fields.get(scene.scene_id)
            slots = field_slots(feeling, spec)
            drawn_from = [
                (reference.request.kind, Path(path))
                for ref_id in scene.reference_ids
                if (reference := references.get(ref_id)) is not None
                # The channel's design first: it already has the look and the identity.
                for path in [*([reference.design] if reference.design else []), *reference.chosen]
            ]
            guide = self._guide(state, scene, self.config.seed)
            signature = render_signature(
                self.config.image_model,
                self.config.image_resolution,
                self.theme.keyframe_prompt(scene.anchor, field=slots),
                *(file_digest(path) for path in self.theme.references),
                *(file_digest(path) for _, path in drawn_from),
                *([self.theme.spec.visual.repaint_note, guide.dumps()] if guide else []),
            )
            previous = existing.get(scene.scene_id)
            attempt = next_attempt(previous, signature, self.config.keyframe_attempts)
            if attempt is None:
                continue
            # A retry learns from what went wrong: a refused or garbled portrait becomes a
            # silhouette (without the person's photographs), a frame that measured too
            # bright is asked to be darker, and a layout that failed its checks, or was drawn
            # with something physically wrong in it (a hand short of its glass), is composed
            # again, differently.
            retry = previous if attempt > 0 else None
            unbuilt = retry is not None and _layout_unbuilt(retry)
            silhouette = (
                retry is not None
                and not unbuilt
                and scene.anchor.figure is not None
                and (retry.silhouette or not retry.rendered or _judged_unclean(retry))
            )
            if guide is not None and retry is not None and (unbuilt or _judged_unclean(retry)):
                guide = self._guide(state, scene, self.config.seed + attempt)
            photos = [
                str(path) for kind, path in drawn_from if not (silhouette and kind == "person")
            ][:MAX_STORY_REFERENCES]
            prompt = self.theme.keyframe_prompt(scene.anchor, silhouette=silhouette, field=slots)
            if guide is not None:
                prompt = f"{self.theme.spec.visual.repaint_note} {prompt}"
            if photos:
                prompt = f"{prompt} {self.theme.spec.visual.reference_note}"
            if retry is not None:
                prompt = " ".join([prompt, *self._fixes(retry)])
            tasks.append(
                Send(
                    "produce_keyframe",
                    RenderTask(
                        scene_id=scene.scene_id,
                        attempt=attempt,
                        prompt=prompt,
                        signature=signature,
                        anchor=anchor_text(scene.anchor),
                        next_anchor=None,
                        first_frame=None,
                        last_frame=None,
                        clip_seconds=0,
                        silhouette=silhouette,
                        references=photos,
                        expected_framing=look(feeling, spec).framing,
                        expected_temperature=expected_temperature(feeling, spec),
                        field_point=circumplex(feeling, spec),
                        expected_shift=None,
                        guide=guide.dumps() if guide else None,
                        join=None,
                        animate=self._animation(state, scene),
                    ),
                )
            )
        return tasks or "keyframe_verdict"

    def _guide(self, state: ContentState, scene: Scene, seed: int) -> Job | None:
        """A staged scene's 3D layout as a guide for the image model (`docs/3d-reuse.md`): the
        scene composed with this seed, seen from where its camera starts, in the guide look.
        None when the scene is drawn from words alone; what stopped it is noted."""
        staging = self.staging()
        shot = staged(scene) if staging else None
        if staging is None or shot is None:
            if staging is not None and isinstance(scene, StagedScene) and scene.missing:
                record_gap(self.theme.root, state["topic"], scene.scene_id, scene.missing)
            return None
        assert shot.staging is not None
        window, _ = self._hold(state, scene.scene_id)
        try:
            job = job_for(
                shot.scene_id, shot.staging, self.theme, staging[1], seconds=window.seconds,
                quality="still", frames=(1,), seed=seed,
            )  # fmt: skip
        except StagingError as exc:
            # Something it needs could not be found or made: drawn, and the gap noted.
            for missing in exc.missing:
                record_gap(self.theme.root, state["topic"], scene.scene_id, missing)
            return None
        # Composed as the storyboard's check composed it; named apart from the scene's shot.
        return replace(job, shot_id=f"{shot.scene_id}-layout", look=BlockCall(GUIDE))

    def _hold(self, state: ContentState, scene_id: str) -> tuple[ShotWindow, list[int]]:
        """A scene's shot window, and the frames it is judged by and morphed from: where its
        picture starts holding, the middle of the hold, and where the morph out begins."""
        window = self.window(required(state.get("timeline"), "a timeline"), scene_id)
        fps = self.theme.spec.format.fps
        frames = {
            window.frame(window.held_from, fps),
            window.frame(window.held_from + window.held / 2, fps),
            window.frame(window.out_from, fps),
        }
        return window, sorted(frames)

    def _animation(self, state: ContentState, scene: Scene) -> str | None:
        """What animating a scene's keyframe needs (`production.pictures` "animated" or
        "staged"): its hold and its camera move."""
        if self.config.pictures == "keyframes":
            return None
        window, frames = self._hold(state, scene.scene_id)
        return json.dumps(
            {"seconds": window.seconds, "frames": frames, "move": scene.camera,
             "topic": state["topic"]}
        )  # fmt: skip

    def _animated(self, task: RenderTask, judged: ContentState) -> ContentState:
        """A drawn keyframe that passed, animated in Blender as a picture shot
        (docs/picture-shots.md): lifted into depth, its camera gliding, its people breathing.
        The drawing stays the scene's picture (its signature, its judgements); the shot is
        added to it, so the cut plays the shot and the morphs meet its frames. A picture that
        cannot be animated stays a drawn keyframe, and the gap is noted."""
        asset = judged["keyframes"][task["scene_id"]]
        staging = self.staging()
        if task["animate"] is None or staging is None or asset.failed or not asset.rendered:
            return judged
        plan = json.loads(task["animate"])
        try:
            job = picture_job(
                task["scene_id"], Path(asset.path), plan["move"], self.theme, staging[1],
                seconds=plan["seconds"], quality="final", frames=plan["frames"],
            )  # fmt: skip
            report = self.render_shot(job)
        except StagingError as exc:
            for missing in exc.missing:
                record_gap(self.theme.root, plan["topic"], task["scene_id"], missing)
            return judged
        if not report.frames:
            for issue in report.issues:
                record_gap(self.theme.root, plan["topic"], task["scene_id"], f"animate: {issue}")
            return judged
        moving = asset.model_copy(
            update={
                "shot": job.dumps(),
                "first_frame": report.frames[0],
                "last_frame": report.frames[-1],
            }
        )
        return {**judged, "keyframes": {task["scene_id"]: moving}}

    def _fixes(self, retry: RenderedAsset) -> list[str]:
        """What a redrawn keyframe is told, from the exact problems code measured."""
        visual = self.theme.spec.visual
        fixes = []
        if any(_is_tone_issue(issue) for issue in retry.issues):
            fixes.append(visual.tone.darker)
        if any("too cool" in issue for issue in retry.issues):
            fixes.append(visual.field.warmer)
        if any("too warm" in issue for issue in retry.issues):
            fixes.append(visual.field.cooler)
        if any("too dark for the scene" in issue for issue in retry.issues):
            fixes.append(visual.tone.lighter)
        if any("too muted for the scene" in issue for issue in retry.issues):
            fixes.append(visual.tone.richer)
        return fixes

    def produce_keyframe(self, state: RenderTask) -> ContentState:
        task = state
        spec = self.theme.spec
        references = [*self.theme.references, *map(Path, task["references"])]
        if task["guide"]:
            report = self.render_shot(Job.loads(task["guide"]))
            if not report.frames:
                return {"keyframes": {task["scene_id"]: _unrendered(task, report.issues)}}
            # The layout first: the repaint note speaks of "the first image".
            references = [Path(report.frames[0]), *references]
        try:
            image, calls = self.fetch(
                "keyframe",
                {"signature": task["signature"], "attempt": task["attempt"]},
                ".png",
                "keyframe",
                lambda: self.media.image(
                    model=self.config.image_model,
                    prompt=task["prompt"],
                    references=references,
                    aspect_ratio=spec.format.aspect_ratio,
                    resolution=self.config.image_resolution,
                    seed=self.config.seed + task["attempt"],
                ),
                about=f"{task['scene_id']} keyframe, attempt {task['attempt']}: {task['prompt']}",
            )
        except GenerationRefused as refusal:
            return {"keyframes": {task["scene_id"]: refused(task, refusal)}}
        return self._animated(task, self._judged(task, image, calls))

    def _judged(
        self,
        task: RenderTask,
        image: Path,
        calls: list[CallRecord],
    ) -> ContentState:
        """A keyframe measured against its scene's tone and colour, described, and judged."""
        spec = self.theme.spec
        tone = spec.visual.tone
        signal = checks.measure(image)
        colour = _colour_check(signal, task["field_point"], tone)
        issues = [
            f"{task['scene_id']}: {issue}"
            for issue in [
                *checks.tone_issues(
                    signal,
                    max_mean_brightness=tone.max_mean_brightness,
                    max_highlight_saturation=tone.max_highlight_saturation,
                ),
                *checks.temperature_issues(signal, task["expected_temperature"]),
                *(
                    checks.colour_issues(
                        signal,
                        target_brightness=colour.target_brightness,
                        target_saturation=colour.target_saturation,
                        brightness_tolerance=tone.brightness.tolerance,
                        saturation_tolerance=tone.saturation.tolerance,
                    )
                    if colour
                    else []
                ),
            ]
        ]
        observations, perception_calls = self.perceive([image], layout=bool(task["guide"]))
        judgements, judge_call = self.judge.evaluate(
            {
                "stage": "keyframes",
                "revision": task["attempt"],
                "target": "keyframe",
                "target_id": task["scene_id"],
                "state": {
                    "anchor": task["anchor"],
                    "theme_look": self.theme_look(),
                    "expected_framing": task["expected_framing"],
                    "observation": observations[0].model_dump(),
                },
                "expected": None,
            }
        )
        asset = RenderedAsset(
            scene_id=task["scene_id"],
            attempt=task["attempt"],
            prompt=task["prompt"],
            signature=task["signature"],
            path=str(image),
            observations=observations,
            judgements=judgements,
            issues=issues,
            silhouette=task["silhouette"],
            colour=colour,
            guide=task["guide"] or "",
        )
        return {
            "keyframes": {task["scene_id"]: asset},
            "judgements": judgements,
            "call_log": [*calls, *perception_calls, judge_call],
        }

    def keyframe_verdict(self, state: ContentState) -> ContentState:
        """Retry failed keyframes within their allowance; then always show a person. A staged
        scene whose layout could not be built is drawn from words instead."""
        assets = self.current(state, "keyframes")
        abandoned = {
            asset.scene_id: reason
            for asset in assets
            if (reason := _abandoned(asset, self.config.keyframe_attempts))
        }
        if abandoned:
            visuals = required(state.get("visual_package"), "a storyboard")
            for scene_id, reason in abandoned.items():
                visuals = unstage(visuals, {scene_id}, reason)
            return {
                **decision("keyframes", "retry", [], structural=False),
                "visual_package": visuals,
            }
        if self.retry_possible(assets, self.config.keyframe_attempts):
            return decision("keyframes", "retry", [], structural=False)
        drawn = [asset for asset in assets if asset.rendered]
        sheet = self.derived("storyboard", [asset.path for asset in drawn], ".png")
        if drawn and not sheet.is_file():
            assemble.contact_sheet([Path(asset.path) for asset in drawn], sheet)
        # A scene with no image cannot become video; its anchor has to change.
        missing = len(drawn) < len(assets)
        animatic, calls = (None, []) if missing else self._animatic(state, assets)
        notes = corrections(assets)
        return {
            **decision("storyboard", "review", notes, structural=missing),
            "contact_sheet": str(sheet) if drawn else None,
            "animatic": str(animatic) if animatic else None,
            "story_sheet": str(self._story_sheet(state, animatic, notes)),
            "call_log": calls,
        }

    def _story_sheet(self, state: ContentState, animatic: Path | None, notes: list[str]) -> Path:
        """The piece as a story with its pictures, for the person who approves it."""
        script = required(state.get("script_package"), "a script")
        visuals = required(state.get("visual_package"), "a storyboard")
        keyframes = state.get("keyframes", {})
        folder = self.derived(
            "story",
            [
                script.model_dump_json(),
                visuals.model_dump_json(),
                *(asset.path for asset in keyframes.values()),
                str(animatic),
            ],
            "",
        )
        return write_story_sheet(
            folder,
            brief=required(state.get("editorial_brief"), "a creative plan"),
            script=script,
            visuals=visuals,
            timeline=required(state.get("timeline"), "a timeline"),
            keyframes=keyframes,
            references=state.get("references", {}),
            animatic=animatic,
            notes=notes,
            fields=self.fields(state),
            budget=state.get("budget"),
        )

    def _animatic(
        self, state: ContentState, keyframes: Sequence[RenderedAsset]
    ) -> tuple[Path, list[CallRecord]]:
        """The whole piece as moving stills, with the real narration, music, and
        subtitles: timing, music, and colour can be judged before any video is paid for."""
        timeline = required(state.get("timeline"), "a timeline")
        visuals = required(state.get("visual_package"), "a storyboard")
        picture = self.picture(
            timeline, visuals.scenes, keyframes, {}, self.fields(state), final=False
        )
        music, calls = self.music(timeline, state.get("arrangement"))
        mix = self.mix(timeline, music)
        animatic = self.derived(
            "animatic",
            [file_digest(picture), file_digest(mix), file_digest(Path(timeline.subtitles_path))],
            ".mp4",
        )
        if not animatic.is_file():
            assemble.finish(
                picture,
                mix,
                Path(timeline.subtitles_path),
                self.theme.font_file.parent,
                animatic,
                crf=28,
                preset="veryfast",
            )
        return animatic, calls


def _abandoned(asset: RenderedAsset, attempts: int) -> str:
    """Why a staged scene gives way to a keyframe drawn from words alone, or nothing if its
    layout stands: one that failed its checks every time it was composed. A picture drawn over
    a layout that misses the scene is drawn again, like any keyframe."""
    if _layout_unbuilt(asset) and asset.attempt + 1 >= attempts:
        return asset.issues[0].removeprefix(f"{asset.scene_id}: ")
    return ""


def _layout_unbuilt(asset: RenderedAsset) -> bool:
    return bool(asset.guide) and not asset.rendered and UNBUILT in asset.issues[0]


def _judged_unclean(asset: RenderedAsset) -> bool:
    return any(
        judgement.question_id == "keyframe_clean" and judgement.outcome != "pass"
        for judgement in asset.judgements
    )


def _colour_check(
    signal: checks.Signal, point: tuple[float, float] | None, tone: ToneSpec
) -> ColourCheck | None:
    """The keyframe's measured colour against its field's targets. The brightness target
    never exceeds the theme's ceiling."""
    if point is None:
        return None
    pleasure, arousal = point
    brightness, saturation = colour_units(pleasure, arousal)
    return ColourCheck(
        pleasure=pleasure,
        arousal=arousal,
        target_brightness=round(
            min(tone.brightness.target(brightness), tone.max_mean_brightness), 1
        ),
        target_saturation=round(tone.saturation.target(saturation), 1),
        brightness=round(signal.brightness, 1),
        saturation=round(signal.saturation, 1),
        warmth=round(signal.warmth, 1),
    )


def _is_tone_issue(issue: str) -> bool:
    return "too bright" in issue or "too saturated" in issue


def _unrendered(task: RenderTask, issues: list[str]) -> RenderedAsset:
    """A layout the checks stopped before rendering: the scene will be drawn from words."""
    return RenderedAsset(
        scene_id=task["scene_id"],
        attempt=task["attempt"],
        prompt=task["prompt"],
        signature=task["signature"],
        path="",
        observations=[],
        judgements=[],
        issues=[f"{task['scene_id']}: {UNBUILT} ({'; '.join(issues)})"],
        guide=task["guide"] or "",
    )
