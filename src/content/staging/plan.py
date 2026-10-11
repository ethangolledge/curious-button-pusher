"""From a storyboard's staged scene to a render job, and the check that a storyboard's staging
can be built: the bridge between the Visual Director's plan and the Blender toolkit."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, TypeVar

from content.blender.blocks.base import SettingError, read
from content.blender.job import NEUTRAL, BlockCall, Grade, Job, Join, Quality
from content.blender.registry import RegistryError
from content.schemas.staging import (
    BlockChoice,
    Setting,
    StagedScene,
    StagedVisualPackage,
    StagePlan,
)
from content.schemas.visuals import Scene, VisualPackage
from content.staging.catalogue import Catalogue, check, with_models
from content.staging.compose import Resolve, compose
from content.staging.resolve import from_library
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


class StagingError(ValueError):
    """A staged scene that cannot be composed: what is missing, in a few words each."""

    def __init__(self, missing: Sequence[str]) -> None:
        super().__init__("; ".join(missing))
        self.missing = list(missing)


def job_for(
    shot_id: str,
    plan: StagePlan,
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
    resolve: Resolve | None = None,
) -> Job:
    """The render job for a staged scene's plan, in the channel's look and frame: its things
    resolved (from the library unless `resolve` says otherwise) and placed. `scale` shrinks
    the frame (drafts); `fps` slows it (drafts are stretched back to the cut's rate)."""
    shot = compose(
        plan,
        catalogue.registry,
        resolve or from_library(catalogue.library),
        seed=f"{seed}:{shot_id}",
    )
    if shot.missing:
        raise StagingError(shot.missing)
    spec = theme.spec
    staging = spec.staging
    job = Job(
        shot_id=shot_id,
        seconds=seconds,
        layout=_call(plan.layout),
        camera=_call(plan.camera, staging.moves),
        look=BlockCall(staging.look, {k: _text(v) for k, v in staging.look_settings.items()}),
        actors=tuple(shot.actors),
        groups=dict(shot.groups),
        models=tuple(shot.models),
        actions=tuple(shot.actions),
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


def staging_issues(
    visuals: VisualPackage, theme: Theme, catalogue: Catalogue, *, finds_models: bool = False
) -> list[str]:
    """Every problem with a storyboard's staging that can be found without Blender. When
    the run finds models online, a thing the library lacks is not a problem yet: it is
    looked for before the shot is rendered (and the scene drawn if nothing fits)."""
    if not isinstance(visuals, StagedVisualPackage):
        return []
    issues = []
    for scene in visuals.scenes:
        if (shot := staged(scene)) is None or shot.staging is None:
            continue
        try:
            job = job_for(
                scene.scene_id, shot.staging, theme, catalogue, seconds=CHECK_SECONDS,
                quality="still",
            )  # fmt: skip
        except StagingError as exc:
            if not (finds_models and all(m.startswith("model:") for m in exc.missing)):
                issues += [f"{scene.scene_id} staging: {missing}" for missing in exc.missing]
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
