"""From a storyboard's staged scene to a render job, and the check that a storyboard's staging
can be built: the bridge between the Visual Director's plan and the Blender toolkit."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, TypeVar

from content.blender.blocks.base import SettingError, read
from content.blender.job import NEUTRAL, ActorCall, BlockCall, Grade, Job, Join, Quality
from content.blender.registry import RegistryError
from content.schemas.staging import BlockChoice, Setting, StagedScene, StagedVisualPackage
from content.schemas.visuals import Scene, VisualPackage
from content.staging.catalogue import Catalogue, check, with_models
from content.theme import BlockPreset, Theme

Package = TypeVar("Package", bound=VisualPackage)

# How long a scene is taken to be when its staging is checked before the narration is timed.
CHECK_SECONDS = 6.0


def _settings(given: Sequence[Setting]) -> dict[str, str]:
    return {setting.name: setting.value for setting in given}


def _call(choice: BlockChoice, presets: Mapping[Any, BlockPreset] | None = None) -> BlockCall:
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


def join_for(
    scene: Scene,
    theme: Theme,
    *,
    speed: str,
    first: str,
    last: str,
    seconds: float,
) -> Join:
    """The rendered transition out of a scene: the one its storyboard chose, or the theme's
    for how swiftly the feeling changes into the next scene."""
    chosen = scene.transition if isinstance(scene, StagedScene) else None
    presets = theme.spec.staging.joins
    call = _call(chosen, presets) if chosen else _call(BlockChoice(block=speed), presets)
    spec = theme.spec.format
    folder = theme.root / "blender"
    return Join(
        join_id=scene.scene_id,
        seconds=seconds,
        transition=call,
        first=first,
        last=last,
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
        channel_blocks=(str(folder),) if folder.is_dir() else (),
    )


def themed(job: Job, theme: Theme) -> Job:
    """A shot drawn the channel's way: its look and palette, and its camera named by one of
    the theme's moves turned into the move block."""
    staging = theme.spec.staging
    camera = job.camera
    preset = staging.moves.get(camera.block)
    if preset is not None:
        base = {name: _text(value) for name, value in preset.settings.items()}
        camera = BlockCall(preset.block, {**base, **camera.settings})
    return replace(
        job,
        camera=camera,
        look=BlockCall(staging.look, {k: _text(v) for k, v in staging.look_settings.items()}),
        palette=dict(theme.spec.palette),
    )


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
    for scene in visuals.scenes:
        chosen = scene.transition if isinstance(scene, StagedScene) else None
        if chosen is None:
            continue
        try:
            block = catalogue.registry.get("transitions", chosen.block)
            read(block, _settings(chosen.settings))
        except (RegistryError, SettingError) as exc:
            issues.append(f"{scene.scene_id} transition: {exc}")
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
