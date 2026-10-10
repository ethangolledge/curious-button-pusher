"""The morphs: each a short AI video from one keyframe into the next, judged from sampled
frames."""

from pathlib import Path

from langgraph.types import Send

from content.production import assemble, checks
from content.production.media import GenerationRefused
from content.production.studio import (
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
    RenderedAsset,
)
from content.state import ContentState
from content.story.field import (
    field_slots,
    look,
    shift_phrase,
)

SEGMENT_SAMPLE_POINTS = (0.1, 0.5, 0.9)


class Segments(Studio):
    def segment_tasks(self, state: ContentState) -> list[Send] | str:
        """One AI morph per transition the budget chose: from this scene's keyframe into
        the next scene's, shaped by the storyboard's bridge and the shift in feeling."""
        visuals = required(state.get("visual_package"), "a storyboard")
        timeline = required(state.get("timeline"), "a timeline")
        keyframes = {asset.scene_id: asset for asset in self.current(state, "keyframes")}
        scenes = {scene.scene_id: scene for scene in visuals.scenes}
        existing = state.get("segments", {})
        fields = self.fields(state)
        spec = self.theme.spec.visual.field
        seconds = self.config.transition_seconds
        tasks = []
        for transition in timeline.transitions:
            scene, following = scenes[transition.from_scene_id], scenes[transition.to_scene_id]
            first = keyframes[scene.scene_id].path
            last = keyframes[following.scene_id].path
            silhouette = keyframes[scene.scene_id].silhouette
            here = fields.get(scene.scene_id)
            # The space changes as the next line will land: tunnelling in, blooming out.
            shift = shift_phrase(here, fields.get(following.scene_id), spec)
            prompt = self.theme.segment_prompt(
                scene.anchor,
                camera=scene.camera,
                motion=scene.motion,
                morph_bridge=scene.morph_bridge,
                next_anchor=following.anchor,
                silhouette=silhouette,
                field=field_slots(here, spec),
                shift=shift,
            )
            signature = render_signature(
                self.config.video_model,
                self.config.video_resolution,
                prompt,
                str(seconds),
                file_digest(Path(first)),
                file_digest(Path(last)),
            )
            attempt = next_attempt(
                existing.get(scene.scene_id), signature, self.config.segment_attempts
            )
            if attempt is not None:
                tasks.append(
                    Send(
                        "produce_segment",
                        RenderTask(
                            scene_id=scene.scene_id,
                            attempt=attempt,
                            prompt=prompt,
                            signature=signature,
                            anchor=anchor_text(scene.anchor),
                            next_anchor=anchor_text(following.anchor),
                            first_frame=first,
                            last_frame=last,
                            clip_seconds=seconds,
                            silhouette=silhouette,
                            references=[],
                            expected_framing=look(here, spec).framing,
                            expected_temperature=None,
                            field_point=None,
                            expected_shift=shift,
                        ),
                    )
                )
        return tasks or "segment_verdict"

    def produce_segment(self, state: RenderTask) -> ContentState:
        task = state
        first = Path(required(task["first_frame"], "a first frame"))
        last = Path(task["last_frame"]) if task["last_frame"] else None
        try:
            video, calls = self.fetch(
                "segment",
                {"signature": task["signature"], "attempt": task["attempt"]},
                ".mp4",
                "segment",
                lambda: self.media.video(
                    model=self.config.video_model,
                    prompt=task["prompt"],
                    first_frame=first,
                    last_frame=last,
                    duration=task["clip_seconds"],
                    resolution=self.config.video_resolution,
                    aspect_ratio=self.theme.spec.format.aspect_ratio,
                    seed=self.config.seed + task["attempt"],
                ),
                about=f"{task['scene_id']} morph, attempt {task['attempt']}: {task['prompt']}",
            )
        except GenerationRefused as refusal:
            return {"segments": {task["scene_id"]: refused(task, refusal)}}
        issues = [
            f"{task['scene_id']}: {issue}"
            for issue in checks.segment_issues(
                video, hard_cut_threshold=self.config.hard_cut_threshold
            )
        ]
        frames = assemble.sample_frames(video, SEGMENT_SAMPLE_POINTS, self.cache.root / "frames")
        observations, perception_calls = self.perceive(frames)
        judgements, judge_call = self.judge.evaluate(
            {
                "stage": "segments",
                "revision": task["attempt"],
                "target": "segment",
                "target_id": task["scene_id"],
                "state": {
                    "anchor": task["anchor"],
                    "theme_look": self.theme_look(),
                    "next_anchor": task["next_anchor"] or "the image settling into shadow",
                    "expected_shift": task["expected_shift"] or "the space settles and fades",
                    "observations": {
                        moment: observation.model_dump()
                        for moment, observation in zip(
                            ("start", "middle", "end"), observations, strict=True
                        )
                    },
                },
                "expected": None,
            }
        )
        asset = RenderedAsset(
            scene_id=task["scene_id"],
            attempt=task["attempt"],
            prompt=task["prompt"],
            signature=task["signature"],
            path=str(video),
            observations=observations,
            judgements=judgements,
            issues=issues,
        )
        return {
            "segments": {task["scene_id"]: asset},
            "judgements": judgements,
            "call_log": [*calls, *perception_calls, judge_call],
        }

    def segment_verdict(self, state: ContentState) -> ContentState:
        """Retry failed segments within their allowance; remaining doubts go to the final
        review, where a person sees the finished cut."""
        assets = self.video_segments(state)
        if self.retry_possible(assets, self.config.segment_attempts):
            return decision("segments", "retry", [], structural=False)
        if not all(asset.rendered for asset in assets):
            # Nothing to assemble: the storyboard has to change around the refused scenes.
            return decision("storyboard", "review", corrections(assets), structural=True)
        return decision("segments", "assemble", corrections(assets), structural=False)
