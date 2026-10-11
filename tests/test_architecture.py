"""The package's shape: dependencies run one way, from the data types up to the command
line, so a change to one part never loops back into it."""

import ast
from collections import defaultdict
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src"
# Bottom to top: a part may import only from the parts below it (or from itself).
LAYERS: list[set[str]] = [
    {"blender"},  # what runs inside Blender: imports nothing else (it has none of it there)
    {"schemas"},  # the data every part passes around
    {"errors", "models"},
    {"providers"},  # the paid models and the stand-ins for them
    {"state"},  # the run's state, and the record of every call
    {"spend"},  # what has been spent, and what is left
    {"judging"},  # Jev: the questions, the outcomes, the judge
    {"theme"},
    {"config"},
    {"staging"},  # 3D shots: the catalogue, the model library, checks
    {"choices"},
    {"story"},  # the story's maths and checks, in code
    {"agents"},  # the roles that write
    {"production"},
    {"learning"},
    {"review", "storage"},
    {"workflow"},  # the graph and the run
    {"cli"},  # one module per command group
    {"__main__"},  # dispatch only
]


def _imports() -> dict[str, set[str]]:
    """Every module and the package modules it imports, wherever in the file."""
    modules = {
        ".".join(path.with_suffix("").relative_to(SOURCE).parts).removesuffix(".__init__"): path
        for path in (SOURCE / "content").rglob("*.py")
    }
    graph: dict[str, set[str]] = defaultdict(set)
    for name, path in modules.items():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                targets = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            else:
                continue
            graph[name] |= {target for target in targets if target in modules} - {name}
    return graph


def test_no_import_cycles() -> None:
    graph = _imports()
    cycles: list[list[str]] = []
    state: dict[str, int] = {}  # 1: on the current path, 2: finished

    def visit(module: str, path: list[str]) -> None:
        state[module] = 1
        for target in sorted(graph[module]):
            if state.get(target) == 1:
                cycles.append([*path[path.index(target) :], target])
            elif target not in state:
                visit(target, [*path, target])
        state[module] = 2

    for module in sorted(graph):
        if module not in state:
            visit(module, [module])

    assert not cycles, "\n".join(" → ".join(cycle) for cycle in cycles)


def _part(module: str) -> str:
    """The package (or root module) a module belongs to: `content.story.pace` → `story`."""
    return module.split(".")[1]


def test_dependencies_run_one_way_from_the_data_up_to_the_command_line() -> None:
    layer = {part: index for index, parts in enumerate(LAYERS) for part in parts}
    graph = _imports()
    unplaced = {_part(module) for module in graph} - layer.keys()
    upward = [
        f"{module} imports {target}"
        for module, targets in sorted(graph.items())
        for target in sorted(targets)
        if _part(module) != _part(target) and layer[_part(target)] >= layer[_part(module)]
    ]

    assert not unplaced, f"Give these a layer: {sorted(unplaced)}"
    assert not upward, "\n".join(upward)


# Inside `content.blender`, only these use Blender's own API; everything else there is plain
# Python, so the rest of the project (and the tests) can build shots without Blender.
USES_BLENDER = (
    "content.blender.stage", "content.blender.canvas", "content.blender.worker",
    "content.blender.audit", "content.blender.ingest", "content.blender.imports",
    "content.blender.person", "content.blender.generate",
    "content.blender.blocks.looks.",
)  # fmt: skip


def _is_blender_module(module: str) -> bool:
    return any(module == m or (m.endswith(".") and module.startswith(m)) for m in USES_BLENDER)


def _uses_blender(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    return any(name.split(".")[0] in ("bpy", "bmesh", "mathutils") for name in names)


def test_only_the_foundation_and_looks_touch_blender_and_nothing_outside_imports_them() -> None:
    graph = _imports()
    blender = SOURCE / "content" / "blender"
    touching = sorted(
        ".".join(path.with_suffix("").relative_to(SOURCE).parts)
        for path in blender.rglob("*.py")
        if _uses_blender(path)
    )
    reaching_in = [
        f"{module} imports {target}"
        for module, targets in graph.items()
        if not module.startswith("content.blender")
        for target in targets
        if _is_blender_module(target)
    ]
    assert [m for m in touching if not _is_blender_module(m)] == [], (
        "blocks use Stage verbs, never Blender's API (only looks may)"
    )
    assert not reaching_in, "\n".join(reaching_in)
