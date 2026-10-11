"""What a staged shot can be made of (the blocks and the models), and checking a shot before
anything is rendered: every block and model exists, every setting reads, every name a block
refers to is in the shot, and every actor can do what its actions need. The check builds the
whole shot without Blender, so it is fast and free."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from content.blender.blocks.base import SettingError, read, refs, settings, summary
from content.blender.direct import build
from content.blender.job import BlockCall, Job, ModelFile
from content.blender.registry import KINDS, Registry, RegistryError, discover
from content.blender.rehearsal import RehearsalStage
from content.staging.library import MADE_IN_CODE, Library, load_library
from content.theme import BlockPreset


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


def describe(
    catalogue: Catalogue,
    kinds: Sequence[str] = KINDS[:-1],
    presets: Mapping[str, BlockPreset] | None = None,
    joins: Mapping[Any, BlockPreset] | None = None,
) -> str:
    """The catalogue in words, for a person or a model choosing from it; a theme's camera
    moves (`presets`) are listed with the move blocks they use."""
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
        if kind == "moves" and presets:
            lines.append(
                "- the theme's own moves (used like the blocks; your settings refine them):"
            )
            for name, preset in sorted(presets.items()):
                fixed = ", ".join(f"{k} {v}" for k, v in preset.settings.items())
                lines.append(f"  - {name}: {preset.block}" + (f" with {fixed}" if fixed else ""))
        if kind == "transitions" and joins:
            usual = "; ".join(f"{speed} changes: {preset.block}" for speed, preset in joins.items())
            lines.append(f"- the theme's usual joins, when a scene names none: {usual}")
        lines.append("")
    lines.append("## models")
    for model in sorted(catalogue.library.models.values(), key=lambda m: m.model_id):
        able = f" [{', '.join(model.capabilities)}]" if model.capabilities else ""
        offers = (
            f" (a set for the set layout; parts: {', '.join(p['name'] for p in model.parts)})"
            if model.parts
            else ""
        )
        lines.append(f"- {model.model_id}{able}: {model.describe}{offers}")
    return "\n".join(lines)


def _calls(job: Job) -> list[tuple[str, BlockCall]]:
    """Every block a shot uses, with its kind."""
    calls = [("layouts", job.layout), ("moves", job.camera)]
    calls += [("actions", call) for call in job.actions] + [("lights", call) for call in job.lights]
    return calls + [("actors", BlockCall(a.block, a.settings)) for a in job.actors]


def models_named(job: Job, registry: Registry) -> set[str]:
    """Every model a shot uses: its actors', and any block setting that names one."""
    wanted = {actor.model for actor in job.actors}
    for kind, call in _calls(job):
        try:
            block = registry.get(kind, call.block)
        except RegistryError:
            continue
        wanted |= {
            str(call.settings[s.name])
            for s in settings(block)
            if s.type == "model" and call.settings.get(s.name)
        }
    return wanted


def with_models(job: Job, catalogue: Catalogue) -> Job:
    """The job with its library models (their files, sizes and paint) and the channel's own
    blocks. A version of a model goes as the model it is made from, repainted and resized."""
    library = catalogue.library
    files = []
    for model_id in sorted(models_named(job, catalogue.registry)):
        model = library.get(model_id)
        root, paint = library.root(model)
        path = library.path(root)
        made_in_code = root.source == MADE_IN_CODE
        if path is None and not model.base:
            continue  # a prop made in code: Blender builds it from its own file
        files.append(
            ModelFile(
                model_id,
                str(path or ""),
                model.size,
                prop=root.model_id if made_in_code else "",
                paint=paint,
                height=model.size[2] if model.base else 0.0,
            )
        )
    folders = tuple(str(folder) for folder in catalogue.channel_blocks)
    return replace(job, models=tuple(files), channel_blocks=folders)


def check(job: Job, catalogue: Catalogue) -> list[str]:
    """Every problem with a shot that can be found without rendering it."""
    issues: list[str] = []
    library = catalogue.library
    for model_id in sorted(models_named(job, catalogue.registry)):
        if model_id not in library.models:
            issues.append(f"no model '{model_id}' (content staging models)")
    models = {actor.actor_id: actor.model for actor in job.actors}
    for kind, call in _calls(job):
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
        model_sizes={m.model_id: m.size for m in library.models.values() if m.file or m.base},
        model_parts={m.model_id: m.parts for m in library.models.values() if m.parts},
    )
    try:
        build(stage, job, catalogue.registry)
    except (KeyError, ValueError) as exc:
        issues.append(str(exc).strip("'\""))
    return issues
