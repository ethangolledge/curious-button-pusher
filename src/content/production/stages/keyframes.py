"""The pictures: how many the budget affords, each scene's keyframe drawn and judged, then the
animatic and story sheet for the Pictures sign-off."""

import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

from langgraph.types import Send

from content.blender.job import Grade, Job
from content.production import assemble, checks
from content.production.budget import (
    scene_allowance,
)
from content.production.media import GenerationRefused
from content.production.story_sheet import write_story_sheet
from content.production.studio import (
    STAGING_LOOK,
    RenderTask,
    Studio,
    anchor_text,
    corrections,
    decision,
    next_attempt,
    refused,
    render_signature,
    required,
)
from content.providers.cache import file_digest
from content.schemas.media import (
    ColourCheck,
    RenderedAsset,
)
from content.schemas.staging import StagedScene
from content.schemas.story import Feeling
from content.schemas.visuals import Scene
from content.staging.backlog import record_gap
from content.staging.plan import job_for, staged
from content.state import CallRecord, ContentState
from content.story.field import (
    circumplex,
    colour_units,
    expected_temperature,
    field_slots,
    look,
    warmth,
)
from content.theme import ToneSpec

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
        return {"current_stage": "keyframes", "listened_narration": timeline.narration_path}

    def keyframe_tasks(self, state: ContentState) -> list[Send] | str:
        visuals = required(state.get("visual_package"), "a storyboard")
        existing = state.get("keyframes", {})
        references = state.get("references", {})
        fields = self.fields(state)
        spec = self.theme.spec.visual.field
        tasks = []
        for scene in visuals.scenes:
            feeling = fields.get(scene.scene_id)
            shot = self._shot_task(state, scene, feeling, existing.get(scene.scene_id))
            if shot is not None:
                if shot != "kept":
                    tasks.append(Send("produce_keyframe", shot))
                continue
            slots = field_slots(feeling, spec)
            drawn_from = [
                (reference.request.kind, Path(path))
                for ref_id in scene.reference_ids
                if (reference := references.get(ref_id)) is not None
                for path in reference.chosen
            ]
            signature = render_signature(
                self.config.image_model,
                self.config.image_resolution,
                self.theme.keyframe_prompt(scene.anchor, field=slots),
                *(file_digest(path) for path in self.theme.references),
                *(file_digest(path) for _, path in drawn_from),
            )
            previous = existing.get(scene.scene_id)
            attempt = next_attempt(previous, signature, self.config.keyframe_attempts)
            if attempt is None:
                continue
            # A retry learns from what went wrong: a refused or garbled portrait becomes a
            # silhouette (without the person's photographs), and a frame that measured too
            # bright is asked to be darker.
            retry = previous if attempt > 0 else None
            silhouette = (
                retry is not None
                and scene.anchor.figure is not None
                and (retry.silhouette or not retry.rendered or _judged_unclean(retry))
            )
            photos = [
                str(path) for kind, path in drawn_from if not (silhouette and kind == "person")
            ][:MAX_STORY_REFERENCES]
            prompt = self.theme.keyframe_prompt(scene.anchor, silhouette=silhouette, field=slots)
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
                        shot=None,
                        join=None,
                    ),
                )
            )
        return tasks or "keyframe_verdict"

    def _shot_task(
        self,
        state: ContentState,
        scene: Scene,
        feeling: Feeling | None,
        previous: RenderedAsset | None,
    ) -> RenderTask | Literal["kept"] | None:
        """A staged scene's keyframe task: its 3D shot's first, middle and last frames,
        graded by its feeling. None when the scene is drawn instead: it is not staged, or its
        shot could not be rendered last time."""
        staging = self.staging()
        shot = staged(scene) if staging else None
        if staging is None or shot is None:
            if staging is not None and isinstance(scene, StagedScene) and scene.missing:
                record_gap(self.theme.root, state["topic"], scene.scene_id, scene.missing)
            return None
        if previous is not None and previous.shot and not previous.rendered:
            return None
        timeline = required(state.get("timeline"), "a timeline")
        spec = self.theme.spec.visual.field
        seconds = self.held_seconds(timeline, scene.scene_id)
        count = max(round(seconds * self.theme.spec.format.fps), 1)
        grade = Grade(warmth=warmth(feeling, spec))
        frames = sorted({1, (count + 1) // 2, count})
        base = job_for(
            shot, self.theme, staging[1], seconds=seconds, quality="final",
            frames=frames, grade=grade, seed=self.config.seed,
        )  # fmt: skip
        signature = render_signature("blender", STAGING_LOOK, base.dumps())
        attempt = next_attempt(previous, signature, self.config.keyframe_attempts)
        if attempt is None:
            return "kept"
        job = base
        if attempt > 0 and previous is not None:
            job = replace(base, grade=_regraded(grade, previous))
        return RenderTask(
            scene_id=scene.scene_id,
            attempt=attempt,
            prompt=f"3D shot: {_summary(shot)}",
            signature=signature,
            anchor=anchor_text(scene.anchor),
            next_anchor=None,
            first_frame=None,
            last_frame=None,
            clip_seconds=0,
            silhouette=False,
            references=[],
            expected_framing=look(feeling, spec).framing,
            expected_temperature=expected_temperature(feeling, spec),
            field_point=circumplex(feeling, spec),
            expected_shift=None,
            shot=job.dumps(),
            join=None,
        )

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
        if task["shot"]:
            report = self.render_shot(Job.loads(task["shot"]))
            if not report.frames:
                return {"keyframes": {task["scene_id"]: _unrendered(task, report.issues)}}
            first, image, last = (Path(report.frames[i]) for i in (0, len(report.frames) // 2, -1))
            return self._judged(task, image, [], shot=(first, last))
        try:
            image, calls = self.fetch(
                "keyframe",
                {"signature": task["signature"], "attempt": task["attempt"]},
                ".png",
                "keyframe",
                lambda: self.media.image(
                    model=self.config.image_model,
                    prompt=task["prompt"],
                    references=[*self.theme.references, *map(Path, task["references"])],
                    aspect_ratio=spec.format.aspect_ratio,
                    resolution=self.config.image_resolution,
                    seed=self.config.seed + task["attempt"],
                ),
                about=f"{task['scene_id']} keyframe, attempt {task['attempt']}: {task['prompt']}",
            )
        except GenerationRefused as refusal:
            return {"keyframes": {task["scene_id"]: refused(task, refusal)}}
        return self._judged(task, image, calls)

    def _judged(
        self,
        task: RenderTask,
        image: Path,
        calls: list[CallRecord],
        *,
        shot: tuple[Path, Path] | None = None,
    ) -> ContentState:
        """A keyframe, drawn or rendered, measured against its scene's tone and colour,
        described, and judged."""
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
        observations, perception_calls = self.perceive([image])
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
            shot=task["shot"] or "",
            first_frame=str(shot[0]) if shot else "",
            last_frame=str(shot[1]) if shot else "",
        )
        return {
            "keyframes": {task["scene_id"]: asset},
            "judgements": judgements,
            "call_log": [*calls, *perception_calls, judge_call],
        }

    def keyframe_verdict(self, state: ContentState) -> ContentState:
        """Retry failed keyframes within their allowance; then always show a person."""
        assets = self.current(state, "keyframes")
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


def _summary(plan: StagedScene) -> str:
    staging = plan.staging
    assert staging is not None
    things = ", ".join(f"{a.model} as {a.actor_id}" for a in staging.actors) or "nothing added"
    actions = ", ".join(choice.block for choice in staging.actions) or "no action"
    return f"{staging.layout.block} with {things}; {actions}; camera {staging.camera.block}"


def _regraded(grade: Grade, previous: RenderedAsset) -> Grade:
    """A shot rendered again, corrected by what its last render measured: exposure towards
    the scene's brightness target (luma is about 2.2 stops per doubling), warmth away from
    a temperature it missed."""
    exposure, warmer = grade.exposure, grade.warmth
    colour = previous.colour
    if colour is not None and colour.brightness > 0:
        exposure += max(
            -3.0, min(3.0, 2.2 * math.log2(colour.target_brightness / colour.brightness))
        )
    if any("too cool" in issue for issue in previous.issues):
        warmer = min(1.0, warmer + 0.4)
    if any("too warm" in issue for issue in previous.issues):
        warmer = max(-1.0, warmer - 0.4)
    return Grade(exposure=round(exposure, 2), warmth=round(warmer, 2))


def _unrendered(task: RenderTask, issues: list[str]) -> RenderedAsset:
    """A shot the checks stopped before rendering: the scene will be drawn instead."""
    return RenderedAsset(
        scene_id=task["scene_id"],
        attempt=task["attempt"],
        prompt=task["prompt"],
        signature=task["signature"],
        path="",
        observations=[],
        judgements=[],
        issues=[f"{task['scene_id']}: its 3D shot was not rendered ({'; '.join(issues)})"],
        shot=task["shot"] or "",
    )
