"""What every stage keeps the same way, whatever draws the shot (Blender, or the rehearsal
that only keeps track): the shot's length, rate and shape, its seeded randomness, and the
layout's vocabulary of marks, paths and actors, each found by name."""

import random
from collections.abc import Sequence
from typing import Any

from content.blender.api import Mark
from content.blender.maths import Vec


class Bookkeeping:
    def __init__(self, *, frames: int, fps: int, aspect: float, seed: int) -> None:
        self._frames, self._fps, self._aspect, self._seed = frames, fps, aspect, seed
        self._marks: dict[str, Mark] = {}
        self._paths: dict[str, list[Vec]] = {}
        self._actors: dict[str, Any] = {}

    @property
    def fps(self) -> int:
        return self._fps

    @property
    def frames(self) -> int:
        return self._frames

    @property
    def aspect(self) -> float:
        return self._aspect

    def random(self, purpose: str) -> random.Random:
        return random.Random(f"{self._seed}:{purpose}")

    def mark(self, mark: Mark) -> None:
        self._marks[mark.name] = mark

    def find_mark(self, name: str) -> Mark:
        if name not in self._marks:
            raise KeyError(f"the layout has no mark '{name}' (marks: {', '.join(self._marks)})")
        return self._marks[name]

    def marks(self) -> list[Mark]:
        return list(self._marks.values())

    def path(self, name: str, points: Sequence[Vec]) -> None:
        self._paths[name] = list(points)

    def find_path(self, name: str) -> list[Vec]:
        if name not in self._paths:
            raise KeyError(f"the layout has no path '{name}' (paths: {', '.join(self._paths)})")
        return self._paths[name]

    def cast(self, actor_id: str, thing: Any) -> None:
        if actor_id in self._actors:
            raise ValueError(f"two actors are called '{actor_id}'")
        self._actors[actor_id] = thing

    def actor(self, actor_id: str) -> Any:
        if actor_id not in self._actors:
            raise KeyError(f"no actor '{actor_id}' (actors: {', '.join(self._actors)})")
        return self._actors[actor_id]
