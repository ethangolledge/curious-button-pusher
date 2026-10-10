"""What a staged shot can be made of (the blocks and the models), and checking a shot before
anything is rendered: every block and model exists, every setting reads, every name a block
refers to is in the shot, and every actor can do what its actions need. The check builds the
whole shot without Blender, so it is fast and free."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from content.blender.blocks.base import SettingError, read, refs, settings, summary
from content.blender.direct import build
from content.blender.job import BlockCall, Job, ModelFile
from content.blender.registry import KINDS, Registry, RegistryError, discover
from content.blender.rehearsal import RehearsalStage
from content.staging.library import Library, load_library


@dataclass
class Catalogue:
    registry: Registry
    library: Library
    channel_blocks: tuple[Path, ...] = ()


def load_catalogue(theme_root: Path | None) -> Catalogue:
    """The engine's blocks and props, and a channel's own blocks (`<theme>/blender/`) and
    models (`<theme>/assets/`) when a theme is given."""
    blocks = tuple(p for p in [theme_root / "blender"] if p.is_dir()) if theme_root else ()
    library = load_library(theme_root / "assets" if theme_root else None, blocks)
    return Catalogue(discover(blocks), library, blocks)


def describe(catalogue: Catalogue, kinds: Sequence[str] = KINDS[:-1]) -> str:
    """The catalogue in words, for a person or a model choosing from it."""
    lines: list[str] = []
    for kind in kinds:
        lines.append(f"## {kind}")
        for name, block in sorted(catalogue.registry.blocks[kind].items()):
            lines.append(f"- {name}: {summary(block)}")
            for setting in settings(block):
                limits = f" {setting.low:g} to {setting.high:g}" if setting.low is not None else ""
                options = f" one of {', '.join(setting.options)}" if setting.options else ""
                default = "required" if setting.default is None else f"default {setting.default}"
                about = f": {setting.about}" if setting.about else ""
                lines.append(
                    f"  - {setting.name} ({setting.type}{options}{limits}, {default}){about}"
                )
            if block.needs:
                needs = "; ".join(
                    f"{k} must be {', '.join(sorted(v))}" for k, v in block.needs.items()
                )
                lines.append(f"  - needs: {needs}")
        lines.append("")
    lines.append("## models")
    for model in sorted(catalogue.library.models.values(), key=lambda m: m.model_id):
        able = f" [{', '.join(model.capabilities)}]" if model.capabilities else ""
        lines.append(f"- {model.model_id}{able}: {model.describe}")
    return "\n".join(lines)


def with_models(job: Job, catalogue: Catalogue) -> Job:
    """The job with its library models' files and sizes, and the channel's own blocks."""
    wanted = {actor.model for actor in job.actors}
    wanted |= {call.settings.get("item", "") for call in job.actions} - {""}
    files = []
    for model_id in sorted(wanted):
        model = catalogue.library.get(model_id)
        path = catalogue.library.path(model)
        if path is not None:
            files.append(ModelFile(model_id, str(path), model.size))
    folders = tuple(str(folder) for folder in catalogue.channel_blocks)
    return replace(job, models=tuple(files), channel_blocks=folders)


def check(job: Job, catalogue: Catalogue) -> list[str]:
    """Every problem with a shot that can be found without rendering it."""
    issues: list[str] = []
    library = catalogue.library
    for actor in job.actors:
        if actor.model not in library.models:
            issues.append(f"actor {actor.actor_id}: no model '{actor.model}'")
    calls = [("layouts", job.layout), ("moves", job.camera)]
    calls += [("actions", call) for call in job.actions] + [("lights", call) for call in job.lights]
    calls += [("actors", BlockCall(a.block, a.settings)) for a in job.actors]
    models = {actor.actor_id: actor.model for actor in job.actors}
    for kind, call in calls:
        try:
            block = catalogue.registry.get(kind, call.block)
            chosen = read(block, call.settings)
        except (RegistryError, SettingError) as exc:
            issues.append(str(exc))
            continue
        named = refs(chosen)
        for setting, wanted in block.needs.items():
            model_id = models.get(named.get(setting, ""), "")
            if model_id not in library.models:
                continue
            missing = wanted - set(library.models[model_id].capabilities)
            if missing:
                issues.append(
                    f"{call.block}: {setting} '{named[setting]}' is a {model_id}, which is not "
                    f"{', '.join(sorted(missing))}"
                )
    if issues:
        return issues
    stage = RehearsalStage(
        frames=job.frame_count,
        fps=job.fps,
        aspect=job.width / job.height,
        seed=job.seed,
        props=catalogue.registry.props(),
        model_sizes={m.model_id: m.size for m in library.models.values() if m.file},
    )
    try:
        build(stage, job, catalogue.registry)
    except (KeyError, ValueError) as exc:
        issues.append(str(exc).strip("'\""))
    return issues
