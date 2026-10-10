import json
from pathlib import Path
from typing import Any

import pytest

from content.agents.base import load_prompt
from content.config import ContentConfig, load_config
from content.errors import ConfigurationError


def test_learning_settings_are_validated(tmp_path: Path, project_root: Path) -> None:
    data = json.loads((project_root / "config/config.example.json").read_text())
    data["learning"]["local_questions"].append("made_up_question")
    with pytest.raises(ConfigurationError, match="Unknown local questions: made_up_question"):
        load_config(_write_config(tmp_path, data))


def test_decision_settings_are_validated(tmp_path: Path, project_root: Path) -> None:
    data = _portable_config(project_root)
    data["decisions"]["blocking"].append("made_up_question")
    with pytest.raises(ConfigurationError, match="Unknown blocking questions: made_up_question"):
        load_config(_write_config(tmp_path, data))

    data = _portable_config(project_root)
    data["decisions"]["thresholds"]["no_max"] = 0.9
    with pytest.raises(ConfigurationError, match="Decision thresholds"):
        load_config(_write_config(tmp_path, data))


def test_every_agent_prompt_states_its_role_and_its_limits(app_config: ContentConfig) -> None:
    for agent in app_config.agents.values():
        instructions = load_prompt(agent.prompt)
        assert "# Role" in instructions
        assert "# Prohibited behaviour" in instructions


def test_invalid_model_alias_fails_clearly(tmp_path: Path, project_root: Path) -> None:
    data = _portable_config(project_root)
    data["agents"]["script_writer"]["model"] = "missing"
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigurationError, match="unknown model alias 'missing'"):
        load_config(path)


def test_unsupported_provider_and_negative_revision_limit_fail(
    tmp_path: Path, project_root: Path
) -> None:
    data = _portable_config(project_root)
    data["models"]["accurate"]["provider"] = "unknown"
    path = _write_config(tmp_path, data)
    with pytest.raises(ConfigurationError, match="Unsupported provider 'unknown'"):
        load_config(path)

    data = _portable_config(project_root)
    data["workflow"]["max_revisions"]["research"] = -1
    path = _write_config(tmp_path, data)
    with pytest.raises(ConfigurationError, match="cannot be negative"):
        load_config(path)


def test_unsupported_effort_fails_before_provider_use(tmp_path: Path, project_root: Path) -> None:
    data = _portable_config(project_root)
    data["models"]["accurate"]["effort"] = "maximum"

    with pytest.raises(ConfigurationError, match="Unsupported effort 'maximum'"):
        load_config(_write_config(tmp_path, data))


def test_a_prompt_cannot_come_from_outside_the_project(tmp_path: Path, project_root: Path) -> None:
    data = _portable_config(project_root)
    data["agents"]["fact_checker"]["prompt"] = "/tmp/outside-project/prompt.md"
    path = _write_config(tmp_path, data)

    with pytest.raises(ConfigurationError, match="must be inside the project"):
        load_config(path)


def _portable_config(project_root: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (project_root / "config/config.json").read_text(encoding="utf-8")
    )
    for agent in data["agents"].values():
        agent["prompt"] = str(project_root / agent["prompt"])
    return data


def _write_config(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
