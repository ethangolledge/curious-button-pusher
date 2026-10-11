"""A book of any kind: a paperback, a hardback, a thick ledger, a large folio; bound in
leather, card or cloth."""

from dataclasses import dataclass
from typing import Literal

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

# Each kind: width, height (lying flat: its depth) and thickness, in metres.
KINDS = {
    "paperback": (0.11, 0.18, 0.025),
    "hardback": (0.16, 0.24, 0.035),
    "ledger": (0.24, 0.34, 0.06),
    "folio": (0.3, 0.42, 0.03),
}


@dataclass(frozen=True)
class Settings:
    kind: Literal["paperback", "hardback", "ledger", "folio"] = "hardback"
    binding: Literal["leather", "card", "fabric"] = "leather"


class Book(Prop):
    name = "book"
    names = ("hardback", "paperback", "ledger", "volume", "diary", "notebook", "folio")
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        wide, deep, thick = KINDS[p.kind]
        cover: Role = p.binding
        book = stage.group(name)
        stage.shape("box", Vec(wide, deep, thick), Vec(), role=cover, name=f"{name}.cover",
                    parent=book, bevel=0.003)  # fmt: skip
        stage.shape("box", Vec(wide - 0.008, deep - 0.008, thick - 0.004),
                    Vec(0.006, 0, 0.002), role="paper", name=f"{name}.pages",
                    parent=book)  # fmt: skip
        return book
