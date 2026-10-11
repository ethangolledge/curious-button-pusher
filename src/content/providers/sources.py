"""Every source of models a missing thing is looked for in, in order: what is made on this
computer first (Infinigen), then the free collections (Objaverse, searched locally, first).
A source that needs a key is used once its key is in `.env`; one that needs installing,
once it is installed."""

from content.providers.assets import AssetSource, Fuel, PolyPizza, Sketchfab, Smithsonian
from content.providers.infinigen import Infinigen
from content.providers.objaverse import Objaverse

SOURCES: tuple[type[Infinigen | Objaverse | Sketchfab | PolyPizza | Fuel | Smithsonian], ...] = (
    Infinigen, Objaverse, Sketchfab, PolyPizza, Fuel, Smithsonian,
)  # fmt: skip


def ready_sources() -> list[AssetSource]:
    """Every source that can be used now."""
    return [source() for source in SOURCES if source.ready()]
