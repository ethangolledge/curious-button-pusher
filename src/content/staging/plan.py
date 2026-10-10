"""From a storyboard's staged scene to a render job, and the check that a storyboard's staging
can be built: the bridge between the Visual Director's plan and the Blender toolkit."""

from collections.abc import Mapping, Sequence
from typing import TypeVar

from content.blender.job import NEUTRAL, ActorCall, BlockCall, Grade, Job, Quality
from content.schemas.staging import BlockChoice, Setting, StagedScene, StagedVisualPackage
from content.schemas.visuals import VisualPackage
from content.staging.catalogue import Catalogue, check, with_models
from content.theme import MovePreset, Theme

Package = TypeVar("Package", bound=VisualPackage)

# How long a scene is taken to be when its staging is checked before the narration is timed.
CHECK_SECONDS = 6.0


def _settings(given: Sequence[Setting]) -> dict[str, str]:
    return {setting.name: setting.value for setting in given}


def _call(choice: BlockChoice, presets: Mapping[str, MovePreset] | None = None) -> BlockCall:
    """A block call; a camera move may be one of the theme's moves, whose settings the plan's
    own settings refine."""
    preset = (presets or {}).get(choice.block)
    if preset is None:
        return BlockCall(choice.block, _settings(choice.settings))
    base = {name: _text(value) for name, value in preset.settings.items()}
    return BlockCall(preset.block, {**base, **_settings(choice.settings)})


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def job_for(
    scene: StagedScene,
    theme: Theme,
    catalogue: Catalogue,
    *,
    seconds: float,
    quality: Quality,
    frames: Sequence[int] = (),
    fps: int | None = None,
    scale: float = 1.0,
    grade: Grade = NEUTRAL,
    seed: int = 1,
) -> Job:
    """The render job for a staged scene, in the channel's look and frame. `scale` shrinks
    the frame (drafts); `fps` slows it (drafts are stretched back to the cut's rate)."""
    plan = scene.staging
    if plan is None:
        raise ValueError(f"{scene.scene_id} is not staged")
    spec = theme.spec
    staging = spec.staging
    job = Job(
        shot_id=scene.scene_id,
        seconds=seconds,
        layout=_call(plan.layout),
        camera=_call(plan.camera, staging.moves),
        look=BlockCall(staging.look, {k: _text(v) for k, v in staging.look_settings.items()}),
        actors=tuple(
            ActorCall(a.actor_id, a.block, a.model, _settings(a.settings)) for a in plan.actors
        ),
        actions=tuple(_call(choice) for choice in plan.actions),
        lights=tuple(_call(choice) for choice in plan.lights),
        palette=dict(spec.palette),
        grade=grade,
        width=_even(spec.format.width * scale),
        height=_even(spec.format.height * scale),
        fps=fps or spec.format.fps,
        quality=quality,
        frames=tuple(frames),
        seed=seed,
    )
    return with_models(job, catalogue)


def _even(pixels: float) -> int:
    return max(2, int(pixels) // 2 * 2)


def staged(scene: object) -> StagedScene | None:
    """The scene, if it is staged."""
    return scene if isinstance(scene, StagedScene) and scene.staging is not None else None


def staging_issues(visuals: VisualPackage, theme: Theme, catalogue: Catalogue) -> list[str]:
    """Every problem with a storyboard's staging that can be found without Blender."""
    if not isinstance(visuals, StagedVisualPackage):
        return []
    issues = []
    for scene in visuals.scenes:
        if (shot := staged(scene)) is None:
            continue
        try:
            job = job_for(shot, theme, catalogue, seconds=CHECK_SECONDS, quality="still")
        except KeyError as exc:
            issues.append(f"{scene.scene_id} staging: {str(exc).strip(chr(39))}")
            continue
        issues += [f"{scene.scene_id} staging: {issue}" for issue in check(job, catalogue)]
    return issues


def unstage(visuals: Package, scene_ids: set[str], reason: str) -> Package:
    """The storyboard with these scenes drawn as keyframes instead, saying why."""
    if not isinstance(visuals, StagedVisualPackage):
        return visuals
    scenes = [
        scene.model_copy(update={"staging": None, "missing": f"{reason}"})
        if scene.scene_id in scene_ids
        else scene
        for scene in visuals.scenes
    ]
    return visuals.model_copy(update={"scenes": scenes})
