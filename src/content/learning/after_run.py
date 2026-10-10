"""Learning as we go: what every finished run adds to the store, and what it refits.

Free and local. Nothing here calls a paid model: the teacher only labels during
`python -m content train --budget`.
"""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from content.config import ContentConfig, LearningConfig
from content.learning.examples import Harvest, LearningStore, NarrationSample, harvest
from content.learning.model import FastEmbedder
from content.learning.provider import ModelRegistry
from content.learning.train import TrainingReport, train
from content.production import ffmpeg
from content.production.assemble import spoken_clip


@dataclass
class RunLearning:
    new: Harvest
    narration_clips: int
    training: TrainingReport | None
    note: str = ""

    def summary(self) -> str:
        sources: dict[str, int] = {}
        for label in self.new.labels:
            sources[label.source] = sources.get(label.source, 0) + 1
        parts = [
            f"{len(self.new.examples)} new examples",
            "labels: " + (", ".join(f"{n} {s}" for s, n in sorted(sources.items())) or "none"),
            f"{len(self.new.flags)} flagged for `label`",
            f"{len(self.new.keyframes)} keyframe colour records",
            f"{self.narration_clips} narration clips",
        ]
        if self.training is not None:
            promoted = [q.question_id for q in self.training.questions if q.promoted]
            parts.append("promoted: " + (", ".join(promoted) or "none yet"))
        if self.note:
            parts.append(self.note)
        return "Learning: " + "; ".join(parts)


def learn_from_run(
    config: ContentConfig, learning: LearningConfig, trace_path: Path
) -> RunLearning:
    store = LearningStore(learning.directory)
    new = store.add(harvest(json.loads(trace_path.read_text(encoding="utf-8"))))
    clips = 0
    if config.production is not None:
        clips = len(record_narration(config.production.cache_directory, store))
    training, note = None, ""
    # Models only change when labels do.
    if new.labels:
        try:
            training = train(
                store,
                ModelRegistry(learning.directory),
                FastEmbedder(learning.embedder, learning.directory / "embedder"),
                learning.local_questions,
                min_labels=learning.min_labels,
                min_gold=learning.min_gold,
            )
        except RuntimeError as exc:
            note = f"not retrained ({exc})"
    return RunLearning(new, clips, training, note)


def record_narration(cache_directory: Path, store: LearningStore) -> list[NarrationSample]:
    """Measure every cached clip the store has not seen yet, whatever voice spoke it."""
    known = {sample.clip for sample in store.narration()}
    samples = []
    for request_path in sorted((cache_directory / "speech").glob("*.request.json")):
        clip = request_path.with_name(request_path.name.replace(".request.json", ".audio"))
        name = clip.stem
        if name in known or not clip.is_file():
            continue
        request = json.loads(request_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            trimmed = spoken_clip(clip, Path(directory) / "clip.wav", tempo=1.0)
            seconds = ffmpeg.probe(trimmed).duration
        samples.append(
            NarrationSample(
                clip=name,
                model=request["model"],
                voice=request.get("voice"),
                reference=request.get("reference"),
                direction=request.get("direction"),
                text=request["text"],
                seconds=round(seconds, 3),
            )
        )
    return store.add_narration(samples)
