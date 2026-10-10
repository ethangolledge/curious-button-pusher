"""The run's configuration, read from JSON: the models and which agent uses each, the judge's
thresholds, the workflow's limits, production, learning, storage and the theme. Everything
is checked on load, before any model is called."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from content.errors import ConfigurationError
from content.judging.outcomes import DecisionConfig
from content.judging.questions import QUESTIONS
from content.models import Effort, ModelConfig, ModelRegistry
from content.theme import Theme, ThemeError, load_theme, with_measured_voice

SUPPORTED_PROVIDERS = frozenset({"fake", "openrouter"})
SUPPORTED_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
REQUIRED_AGENTS = frozenset(
    {
        "fact_researcher",
        "editorial_director",
        "script_writer",
        "fact_checker",
        "visual_director",
    }
)


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    name: str
    output_directory: Path
    logging_level: str


@dataclass(frozen=True, slots=True)
class ContentDefaults:
    default_duration_seconds: int


@dataclass(frozen=True, slots=True)
class RevisionLimits:
    research: int
    script: int
    visuals: int


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    allow_provisional_research: bool
    review_plan: bool
    # The person signs off the fact-checked script before narration is paid for.
    review_script: bool
    max_revisions: RevisionLimits


@dataclass(frozen=True, slots=True)
class ProductionConfig:
    """Media generation: which models render the storyboard, and within what limits."""

    provider: str
    cache_directory: Path
    image_model: str
    image_resolution: str
    # The AI video model is used only for transitions: a morph from one scene's keyframe
    # to the next, `transition_seconds` long (one of the model's `video_durations`).
    video_model: str
    video_resolution: str
    video_durations: tuple[int, ...]
    transition_seconds: int
    # The most a whole run may cost, and the prices the budget guard projects with:
    # one keyframe, and one second of AI video at `video_resolution`.
    max_usd: float
    image_usd: float
    video_usd_per_second: float
    transcription_model: str
    music_model: str | None
    vision_model: str
    seed: int
    keyframe_attempts: int
    segment_attempts: int
    # ffmpeg scene-change score above which a frame counts as a hard cut.
    hard_cut_threshold: float
    # Reference images: candidates judged per request, and how many a keyframe uses.
    reference_candidates: int = 4
    references_per_request: int = 2
    # Shorter side, in pixels, below which a reference image is too small to draw from.
    min_reference_side: int = 480
    # How scenes are pictured: "keyframes" (an image model's still, moved by ffmpeg) or
    # "staged" (a 3D shot built in Blender, where the toolkit can show the scene; the rest
    # stay keyframes). Morphs, breathing, colour and texture are the same either way.
    pictures: Literal["keyframes", "staged"] = "keyframes"
    # How one scene turns into the next: "ai" (the video model morphs between the two
    # pictures, paid) or "rendered" (a transition drawn in Blender from them, free).
    joins: Literal["ai", "rendered"] = "ai"


@dataclass(frozen=True, slots=True)
class LearningConfig:
    """Our own trained decision models for taste questions (see `learning/`)."""

    directory: Path
    embedder: str
    # Questions a trained model may answer instead of Jev once it has earned it.
    # Factual and logical questions stay with Jev.
    local_questions: frozenset[str]
    # Model alias that labels examples during `train`.
    teacher: str
    min_labels: int
    # People's labels needed before a model can be compared with Jev.
    min_gold: int
    # The local inference model that checks no line contradicts its own claims before the
    # paid fact check; None skips the check.
    nli_model: str | None = None


@dataclass(frozen=True, slots=True)
class StorageConfig:
    """Where the channel and its runs are kept (see `storage.py`): a Google Cloud bucket, or a
    folder on this computer (or an external or synced drive). Exactly one is set."""

    bucket: str | None = None
    folder: Path | None = None

    @property
    def where(self) -> str:
        """In plain words, for messages."""
        return f"the bucket {self.bucket}" if self.bucket else f"the folder {self.folder}"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    model_alias: str
    # What the model is told: the agent's `prompt.md`. Its other jobs' prompts sit beside it
    # (`critic_prompt.md`, `listener_prompt.md`, `line_edit_prompt.md`).
    prompt: Path
    # The Editorial Director's cold viewer: the model that hears the narration as a
    # first-time listener. A different family from the writer, so it does not share the
    # writer's blind spots; unset, the agent's own model listens.
    listener_model_alias: str | None = None
    # The Script Writer's line edits: a small model for a bounded change to named lines.
    # Unset, the agent's own model edits.
    edit_model_alias: str | None = None
    # The Editorial Director's critic: reads a whole script or storyboard and returns
    # findings. Unset, the agent's own model critiques.
    critic_model_alias: str | None = None
    # The Fact Checker's audit of a few changed lines: the same model at lower effort.
    # Anything it does not pass is audited again on the agent's own model.
    light_model_alias: str | None = None


@dataclass(frozen=True, slots=True)
class ContentConfig:
    application: ApplicationConfig
    models: ModelRegistry
    content: ContentDefaults
    workflow: WorkflowConfig
    decisions: DecisionConfig
    agents: Mapping[str, AgentConfig]
    theme: Theme
    # None: stop at the text prompt package without generating media.
    production: ProductionConfig | None
    # None: every decision goes to Jev.
    learning: LearningConfig | None
    # None: nothing leaves this machine; finished runs stay in their run folders.
    storage: StorageConfig | None = None


def _required(mapping: Mapping[str, Any], key: str, section: str) -> Any:
    if key not in mapping:
        raise ConfigurationError(f"Missing required configuration: {section}.{key}")
    return mapping[key]


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = _required(data, name, "config")
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration section '{name}' must be an object")
    return value


def _agent_config(
    root: Path, name: str, raw: object, models: Mapping[str, ModelConfig]
) -> AgentConfig:
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Agent '{name}' must be an object")

    def alias(key: str, role: str) -> str | None:
        value = raw.get(key)
        if value is not None and str(value) not in models:
            raise ConfigurationError(f"Agent '{name}' references unknown {role}alias '{value}'")
        return None if value is None else str(value)

    model_alias = str(_required(raw, "model", f"agents.{name}"))
    if model_alias not in models:
        raise ConfigurationError(f"Agent '{name}' references unknown model alias '{model_alias}'")
    prompt = (root / str(_required(raw, "prompt", f"agents.{name}"))).resolve()
    if not prompt.is_relative_to(root):
        raise ConfigurationError(f"Prompt for agent '{name}' must be inside the project: {prompt}")
    if not prompt.is_file():
        raise ConfigurationError(f"Prompt for agent '{name}' does not exist: {prompt}")
    listener = alias("listener_model", "listener model ")
    if listener is not None and models[listener].provider != models[model_alias].provider:
        raise ConfigurationError(
            f"Agent '{name}': the listener model must use the same provider as the agent"
        )
    return AgentConfig(
        model_alias=model_alias,
        prompt=prompt,
        listener_model_alias=listener,
        edit_model_alias=alias("edit_model", "edit model "),
        critic_model_alias=alias("critic_model", "critic model "),
        light_model_alias=alias("light_model", "light model "),
    )


def _project_root(config_path: Path) -> Path:
    """The folder holding `src/content`: a configuration lives in `config/` or in its
    channel's folder (`themes/<name>/config.json`)."""
    parent = config_path.resolve().parent
    for candidate in (parent, *parent.parents):
        if (candidate / "src/content").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


def write_channel_config(
    template: Path, theme: Path, bucket: str | None = None, folder: str | None = None
) -> Path:
    """A new channel's own configuration, `<theme>/config.json`: the template pointed at
    the theme and its taste data, and at where it is kept (a bucket, or a folder) when one
    is given. `theme` is relative to the project root, like every path in a configuration."""
    data = json.loads(template.read_text(encoding="utf-8"))
    data["theme"] = theme.as_posix()
    if "learning" in data:
        data["learning"]["directory"] = (theme / "learning").as_posix()
    if bucket is not None:
        data["storage"] = {"bucket": bucket}
    elif folder is not None:
        data["storage"] = {"folder": folder}
    target = theme / "config.json"
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def load_config(config_path: Path | None = None) -> ContentConfig:
    data, root = _read(config_path)
    application_data = _section(data, "application")
    content_data = _section(data, "content")
    workflow_data = _section(data, "workflow")
    limits_data = _section(workflow_data, "max_revisions")
    model_data = _section(data, "models")
    agent_data = _section(data, "agents")
    decision_data = _section(data, "decisions")

    models: dict[str, ModelConfig] = {}
    for alias, raw_model in model_data.items():
        if not isinstance(raw_model, dict):
            raise ConfigurationError(f"Model '{alias}' must be an object")
        provider = str(_required(raw_model, "provider", f"models.{alias}"))
        if provider not in SUPPORTED_PROVIDERS:
            raise ConfigurationError(
                f"Unsupported provider '{provider}' for model alias '{alias}'. "
                f"Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        raw_effort = raw_model.get("effort")
        effort: Effort | None = None
        if raw_effort is not None:
            if raw_effort not in SUPPORTED_EFFORTS:
                raise ConfigurationError(
                    f"Unsupported effort '{raw_effort}' for model alias '{alias}'. "
                    f"Supported efforts: {', '.join(sorted(SUPPORTED_EFFORTS))}"
                )
            effort = raw_effort
        models[alias] = ModelConfig(
            provider=provider,
            model=str(_required(raw_model, "model", f"models.{alias}")),
            max_output_tokens=int(raw_model.get("max_output_tokens", 4000)),
            effort=effort,
        )

    limits = RevisionLimits(
        research=int(_required(limits_data, "research", "workflow.max_revisions")),
        script=int(_required(limits_data, "script", "workflow.max_revisions")),
        visuals=int(_required(limits_data, "visuals", "workflow.max_revisions")),
    )
    if min(limits.research, limits.script, limits.visuals) < 0:
        raise ConfigurationError("Revision limits cannot be negative")

    missing_agents = REQUIRED_AGENTS.difference(agent_data)
    if missing_agents:
        raise ConfigurationError(
            f"Missing required agent configuration: {', '.join(sorted(missing_agents))}"
        )

    agents = {name: _agent_config(root, name, agent_data[name], models) for name in REQUIRED_AGENTS}

    output_directory = Path(str(_required(application_data, "output_directory", "application")))
    if not output_directory.is_absolute():
        output_directory = root / output_directory

    theme = _theme(root, str(_required(data, "theme", "config")))
    learning = (
        _learning_config(root, _section(data, "learning"), models) if "learning" in data else None
    )
    return ContentConfig(
        application=ApplicationConfig(
            name=str(_required(application_data, "name", "application")),
            output_directory=output_directory,
            logging_level=str(_required(application_data, "logging_level", "application")),
        ),
        models=ModelRegistry.create(models),
        content=ContentDefaults(
            default_duration_seconds=int(
                _required(content_data, "default_duration_seconds", "content")
            ),
        ),
        workflow=WorkflowConfig(
            allow_provisional_research=bool(
                _required(workflow_data, "allow_provisional_research", "workflow")
            ),
            review_plan=bool(_required(workflow_data, "review_plan", "workflow")),
            review_script=bool(_required(workflow_data, "review_script", "workflow")),
            max_revisions=limits,
        ),
        decisions=_decision_config(decision_data),
        agents=MappingProxyType(agents),
        # The voice is sized at the pace its recorded takes show, when the learning store
        # holds them.
        theme=(
            with_measured_voice(theme, learning.directory / "narration.jsonl")
            if learning is not None
            else theme
        ),
        production=(
            _production_config(root, _section(data, "production")) if "production" in data else None
        ),
        learning=learning,
        storage=_storage_config(data, root),
    )


def load_storage(config_path: Path | None = None) -> tuple[StorageConfig, Path]:
    """The bucket and the theme folder, read without loading the theme: a fresh clone
    pulls the channel's theme from the bucket before the theme can load."""
    data, root = _read(config_path)
    storage = _storage_config(data, root)
    if storage is None:
        raise ConfigurationError("This configuration has no storage section")
    theme = (root / str(_required(data, "theme", "config"))).resolve()
    if not theme.is_relative_to(root):
        raise ConfigurationError(f"The theme must be inside the project: {theme}")
    return storage, theme


def _read(config_path: Path | None) -> tuple[dict[str, Any], Path]:
    path = (config_path or Path("config/config.json")).resolve()
    if not path.is_file():
        raise ConfigurationError(f"Configuration file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in configuration file {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("The configuration root must be an object")
    return data, _project_root(path)


def _storage_config(data: Mapping[str, Any], root: Path) -> StorageConfig | None:
    if "storage" not in data:
        return None
    section = _section(data, "storage")
    if ("bucket" in section) == ("folder" in section):
        raise ConfigurationError(
            "storage needs exactly one of bucket (Google Cloud) or folder (on this computer)"
        )
    if "bucket" in section:
        return StorageConfig(bucket=str(section["bucket"]))
    folder = Path(str(section["folder"])).expanduser()
    return StorageConfig(folder=folder if folder.is_absolute() else root / folder)


def _theme(root: Path, value: str) -> Theme:
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ConfigurationError(f"The theme must be inside the project: {path}")
    try:
        return load_theme(path)
    except ThemeError as exc:
        raise ConfigurationError(str(exc)) from exc


def _production_config(root: Path, data: Mapping[str, Any]) -> ProductionConfig:
    section = "production"
    provider = str(_required(data, "provider", section))
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigurationError(f"Unsupported production provider '{provider}'")
    cache_directory = Path(str(_required(data, "cache_directory", section)))
    durations = tuple(int(value) for value in _required(data, "video_durations", section))
    transition = int(_required(data, "transition_seconds", section))
    if transition not in durations:
        raise ConfigurationError(
            "production.transition_seconds must be one of production.video_durations"
        )
    music_model = data.get("music_model")
    if not cache_directory.is_absolute():
        cache_directory = root / cache_directory
    return ProductionConfig(
        provider=provider,
        cache_directory=cache_directory,
        image_model=str(_required(data, "image_model", section)),
        image_resolution=str(_required(data, "image_resolution", section)),
        video_model=str(_required(data, "video_model", section)),
        video_resolution=str(_required(data, "video_resolution", section)),
        video_durations=tuple(sorted(durations)),
        transition_seconds=transition,
        max_usd=float(_required(data, "max_usd", section)),
        image_usd=float(_required(data, "image_usd", section)),
        video_usd_per_second=float(_required(data, "video_usd_per_second", section)),
        transcription_model=str(_required(data, "transcription_model", section)),
        music_model=None if music_model is None else str(music_model),
        vision_model=str(_required(data, "vision_model", section)),
        seed=int(_required(data, "seed", section)),
        keyframe_attempts=int(_required(data, "keyframe_attempts", section)),
        segment_attempts=int(_required(data, "segment_attempts", section)),
        hard_cut_threshold=float(_required(data, "hard_cut_threshold", section)),
        reference_candidates=int(data.get("reference_candidates", 4)),
        references_per_request=int(data.get("references_per_request", 2)),
        min_reference_side=int(data.get("min_reference_side", 480)),
        pictures=_choice(data, "pictures", ("keyframes", "staged")),
        joins=_choice(data, "joins", ("ai", "rendered")),
    )


def _choice(data: Mapping[str, Any], key: str, options: tuple[str, ...]) -> Any:
    """A production setting that takes one of a few words; the first is its default."""
    value = data.get(key, options[0])
    if value not in options:
        raise ConfigurationError(
            f"production.{key} must be one of {', '.join(options)}, not {value!r}"
        )
    return value


def _learning_config(
    root: Path, data: Mapping[str, Any], models: Mapping[str, ModelConfig]
) -> LearningConfig:
    section = "learning"
    directory = Path(str(_required(data, "directory", section)))
    local_questions = frozenset(str(q) for q in _required(data, "local_questions", section))
    if unknown := local_questions - QUESTIONS.keys():
        raise ConfigurationError(f"Unknown local questions: {', '.join(sorted(unknown))}")
    teacher = str(_required(data, "teacher", section))
    if teacher not in models:
        raise ConfigurationError(f"learning.teacher references unknown model alias '{teacher}'")
    return LearningConfig(
        directory=directory if directory.is_absolute() else root / directory,
        embedder=str(_required(data, "embedder", section)),
        local_questions=local_questions,
        teacher=teacher,
        min_labels=int(_required(data, "min_labels", section)),
        min_gold=int(_required(data, "min_gold", section)),
        nli_model=str(data["nli_model"]) if data.get("nli_model") else None,
    )


def _decision_config(data: Mapping[str, Any]) -> DecisionConfig:
    provider = str(_required(data, "provider", "decisions"))
    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigurationError(f"Unsupported decision provider '{provider}'")
    thresholds = _section(data, "thresholds")
    config = DecisionConfig(
        provider=provider,
        model=str(_required(data, "model", "decisions")),
        yes_min=float(_required(thresholds, "yes_min", "decisions.thresholds")),
        no_max=float(_required(thresholds, "no_max", "decisions.thresholds")),
        act_min=float(_required(thresholds, "act_min", "decisions.thresholds")),
        blocking=frozenset(str(item) for item in _required(data, "blocking", "decisions")),
    )
    if not 0 <= config.no_max < config.yes_min <= 1 or not 0 <= config.act_min <= 1:
        raise ConfigurationError(
            "Decision thresholds must satisfy 0 <= no_max < yes_min <= 1 and 0 <= act_min <= 1"
        )
    if unknown := config.blocking - QUESTIONS.keys():
        raise ConfigurationError(f"Unknown blocking questions: {', '.join(sorted(unknown))}")
    if measures := sorted(q for q in config.blocking if QUESTIONS[q].measure):
        raise ConfigurationError(f"Measurements cannot block: {', '.join(measures)}")
    return config
