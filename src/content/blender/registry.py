"""Finds every block by folder: the engine's in `blocks/<kind>/`, a channel's in
`themes/<name>/blender/<kind>/`. One block per file; a new file is all it takes to add one.

Looks are found the same way but only inside Blender (they shape materials with Blender's own
API), so the catalogue the storyboard is checked against leaves them out."""

import hashlib
import importlib
import importlib.util
import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from content.blender.blocks.base import Block, Prop

ENGINE = Path(__file__).parent / "blocks"
KINDS = ("layouts", "actors", "actions", "moves", "lights", "props")
# Only inside Blender: looks import its API.
LOOKS = ("looks",)


class RegistryError(ValueError):
    pass


@dataclass
class Registry:
    blocks: dict[str, dict[str, type[Block]]] = field(default_factory=dict)

    def get(self, kind: str, name: str) -> type[Block]:
        found = self.blocks[kind].get(name)
        if found is None:
            known = ", ".join(sorted(self.blocks[kind])) or "none"
            raise RegistryError(f"no {kind[:-1]} called '{name}' (known: {known})")
        return found

    def props(self) -> dict[str, type[Prop]]:
        return {n: b for n, b in self.blocks.get("props", {}).items() if issubclass(b, Prop)}

    def add(self, block: type[Block], origin: Path) -> None:
        if block.name in self.blocks[block.kind]:
            raise RegistryError(
                f"two {block.kind} are called '{block.name}' (the second in {origin}): "
                "names must be unique, a channel cannot replace an engine block"
            )
        self.blocks[block.kind][block.name] = block


def discover(channel_folders: Sequence[Path] = (), kinds: Sequence[str] = KINDS) -> Registry:
    registry = Registry(blocks={kind: {} for kind in kinds})
    for folder in (ENGINE, *channel_folders):
        for kind in kinds:
            for path in sorted((folder / kind).glob("*.py")):
                if path.name.startswith("_"):
                    continue
                registry.add(_one_block(_load(path, folder), path, kind), path)
    return registry


def _load(path: Path, folder: Path) -> ModuleType:
    if folder == ENGINE:
        return importlib.import_module(f"content.blender.blocks.{path.parent.name}.{path.stem}")
    unique = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(f"channel_block_{unique}", path)
    if spec is None or spec.loader is None:
        raise RegistryError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _one_block(module: ModuleType, path: Path, kind: str) -> type[Block]:
    defined = [
        value
        for value in vars(module).values()
        if inspect.isclass(value)
        and issubclass(value, Block)
        and value.__module__ == module.__name__
    ]
    if len(defined) != 1:
        raise RegistryError(f"{path} must define exactly one block, found {len(defined)}")
    block = defined[0]
    if block.kind != kind:
        raise RegistryError(f"{path} is in {kind}/ but defines a {block.kind[:-1]}")
    return block
