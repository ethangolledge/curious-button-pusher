"""Production: from an approved storyboard to the finished cut, in five stages
(`production/stages/`) sharing one workbench (`production/studio.py`)."""

from collections.abc import Sequence
from typing import Any

from content.config import ProductionConfig
from content.judging.judge import Judge
from content.production.media import MediaProvider
from content.production.stages.assembly import Assembly
from content.production.stages.keyframes import Keyframes
from content.production.stages.narration import Narration
from content.production.stages.references import References
from content.production.stages.segments import Segments
from content.providers.images import ImageSource
from content.theme import Theme


class Producer:
    """Every production stage, each sharing the run's configuration, media provider, judge
    and cache. The graph wires each stage's steps (`workflow/graph.py`)."""

    def __init__(
        self,
        *,
        config: ProductionConfig,
        theme: Theme,
        media: MediaProvider,
        judge: Judge,
        image_sources: Sequence[ImageSource],
    ) -> None:
        parts: dict[str, Any] = {
            "config": config,
            "theme": theme,
            "media": media,
            "judge": judge,
            "image_sources": image_sources,
        }
        self.references = References(**parts)
        self.narration = Narration(**parts)
        self.keyframes = Keyframes(**parts)
        self.segments = Segments(**parts)
        self.assembly = Assembly(**parts)
