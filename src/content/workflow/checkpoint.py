"""Saving every step of a run, so it can stop at a review, a crash or a closed terminal and
carry on later without paying again. Only validated record types are restored."""

import base64
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from content.schemas.audience import AudienceFlag, AudienceReport
from content.schemas.base import ImmutableModel
from content.schemas.fact_check import ClaimFinding, FactCheckReport, UnitAudit
from content.schemas.judgement import Answer, Judgement
from content.schemas.media import (
    Arrangement,
    Budget,
    ColourCheck,
    NarrationClip,
    ProductionResult,
    RenderedAsset,
    SceneTiming,
    ScoreSpan,
    Timeline,
    TransitionTiming,
    Word,
)
from content.schemas.package import FinalContentPackage, ReviewHandoff, ScenePrompts
from content.schemas.perception import Observation, Perception
from content.schemas.plan import (
    ArcPhase,
    ClaimPlan,
    ClaimWeight,
    EditorialBrief,
    Explanation,
    LeftOut,
    StorySize,
)
from content.schemas.references import FoundImage, ReferenceImage, ReferenceRequest, ReferenceSet
from content.schemas.research import (
    CastMember,
    EventLink,
    ResearchClaim,
    ResearchPack,
    SourceComparison,
    SourceMaterial,
    SourceReference,
    TimelineEvent,
)
from content.schemas.review import HumanDecision, ReviewRequest, ReviewResponse
from content.schemas.script import (
    EditedLine,
    LineEdit,
    LineEditPackage,
    ScriptPackage,
    ScriptUnit,
    VoiceDirection,
)
from content.schemas.staging import (
    BlockChoice,
    Setting,
    StagedActor,
    StagedScene,
    StagedVisualPackage,
    StagePlan,
)
from content.schemas.story import Feeling
from content.schemas.visuals import PublicFigure, Scene, SceneAnchor, VisualPackage

CHECKPOINT_MODEL_TYPES = [
    SourceMaterial,
    SourceReference,
    VoiceDirection,
    ScriptUnit,
    PublicFigure,
    SceneAnchor,
    Scene,
    Observation,
    Perception,
    Word,
    NarrationClip,
    SceneTiming,
    TransitionTiming,
    Budget,
    ColourCheck,
    ScoreSpan,
    Arrangement,
    Timeline,
    RenderedAsset,
    ProductionResult,
    ReferenceRequest,
    FoundImage,
    ReferenceImage,
    ReferenceSet,
    Feeling,
    ScenePrompts,
    ResearchClaim,
    TimelineEvent,
    CastMember,
    EventLink,
    SourceComparison,
    ResearchPack,
    ArcPhase,
    ClaimPlan,
    Explanation,
    LeftOut,
    StorySize,
    ClaimWeight,
    EditorialBrief,
    AudienceFlag,
    AudienceReport,
    Answer,
    Judgement,
    ClaimFinding,
    FactCheckReport,
    UnitAudit,
    ScriptPackage,
    LineEdit,
    EditedLine,
    LineEditPackage,
    VisualPackage,
    Setting,
    BlockChoice,
    StagedActor,
    StagePlan,
    StagedScene,
    StagedVisualPackage,
    FinalContentPackage,
    ReviewHandoff,
    ReviewRequest,
    ReviewResponse,
    HumanDecision,
]


class ContentCheckpointSerializer:
    """Safely restores validated domain models from LangGraph checkpoints."""

    def __init__(self) -> None:
        self._serializer = JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_MODEL_TYPES)

    def dumps_typed(self, value: Any) -> tuple[str, bytes]:
        return self._serializer.dumps_typed(value)

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        return _restore_models(self._serializer.loads_typed(data))


class FileCheckpointer(InMemorySaver):
    """The in-memory checkpointer, with every step also appended to a file, so a run can
    carry on from its last step after the process ends: at a review, a crash, or a closed
    terminal. One run per file; the file is a log, read back in order."""

    def __init__(self, path: Path) -> None:
        super().__init__(serde=ContentCheckpointSerializer())
        self.path = path
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._replay(json.loads(line))

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        saved = super().put(config, checkpoint, metadata, new_versions)
        thread = saved["configurable"]["thread_id"]
        namespace = saved["configurable"]["checkpoint_ns"]
        records = [
            {
                "blob": [thread, namespace, channel, version],
                "value": _typed(self.blobs[(thread, namespace, channel, version)]),
            }
            for channel, version in new_versions.items()
        ]
        stored, meta, parent = self.storage[thread][namespace][checkpoint["id"]]
        records.append(
            {
                "checkpoint": [thread, namespace, checkpoint["id"]],
                "value": [_typed(stored), _typed(meta), parent],
            }
        )
        self._append(records)
        return saved

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path)
        configurable = config["configurable"]
        key = (
            configurable["thread_id"],
            configurable.get("checkpoint_ns", ""),
            configurable["checkpoint_id"],
        )
        self._append(
            [
                {"write": [*key, *inner], "value": [task, channel, _typed(value), path]}
                for inner, (task, channel, value, path) in self.writes.get(key, {}).items()
                if inner[0] == task_id
            ]
        )

    def _append(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(record) + "\n" for record in records))

    def _replay(self, record: dict[str, Any]) -> None:
        if "blob" in record:
            thread, namespace, channel, version = record["blob"]
            self.blobs[(thread, namespace, channel, version)] = _untyped(record["value"])
        elif "checkpoint" in record:
            thread, namespace, checkpoint_id = record["checkpoint"]
            stored, meta, parent = record["value"]
            self.storage[thread][namespace][checkpoint_id] = (
                _untyped(stored),
                _untyped(meta),
                parent,
            )
        else:
            thread, namespace, checkpoint_id, task_id, index = record["write"]
            task, channel, value, path = record["value"]
            self.writes[(thread, namespace, checkpoint_id)][(task_id, index)] = (
                task,
                channel,
                _untyped(value),
                path,
            )


def create_checkpointer(path: Path | None = None) -> InMemorySaver:
    """Steps kept in memory, or also in `path` so the run survives its process."""
    if path is None:
        return InMemorySaver(serde=ContentCheckpointSerializer())
    return FileCheckpointer(path)


def _typed(value: tuple[str, bytes]) -> list[str]:
    return [value[0], base64.b64encode(value[1]).decode("ascii")]


def _untyped(value: list[str]) -> tuple[str, bytes]:
    return value[0], base64.b64decode(value[1])


def _restore_models(value: Any) -> Any:
    if isinstance(value, ImmutableModel):
        model_type = type(value)
        field_values = {
            name: _restore_models(getattr(value, name)) for name in model_type.model_fields
        }
        return model_type.model_validate(field_values)
    if isinstance(value, list):
        return [_restore_models(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_restore_models(item) for item in value)
    if isinstance(value, dict):
        return {key: _restore_models(item) for key, item in value.items()}
    return value
