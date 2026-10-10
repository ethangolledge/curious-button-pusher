"""`content check` tells a newcomer exactly what is missing and how to fix it, without spending
anything or touching the network when a key is absent."""

import json
from pathlib import Path

import pytest

from content.cli.check import Check, checks

PROJECT_ROOT = Path(__file__).parents[1]


def _by_name(found: list[Check]) -> dict[str, Check]:
    return {check.name: check for check in found}


def test_a_missing_key_is_reported_with_where_to_get_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    key = _by_name(checks(PROJECT_ROOT / "config/config.example.json"))["OpenRouter key"]

    assert key.status == "missing"
    assert "openrouter.ai" in key.fix and ".env" in key.fix


def test_a_machine_with_no_channel_is_told_how_to_make_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    channel = _by_name(checks(None))["Channel"]

    assert channel.status == "missing"
    assert "content new-channel" in channel.fix


def test_a_channel_that_loads_and_has_no_bucket_is_ready_without_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    found = _by_name(checks(PROJECT_ROOT / "config/config.example.json"))

    assert found["Channel"].status == "ready"
    assert found["Storage"].status == "optional"
    assert "google-cloud.md" in found["Storage"].fix


def test_a_broken_configuration_is_reported_with_its_problem(tmp_path: Path) -> None:
    broken = tmp_path / "config.json"
    broken.write_text("{ not json", encoding="utf-8")

    channel = _by_name(checks(broken))["Channel"]

    assert channel.status == "missing"
    assert "Invalid JSON" in channel.detail


def test_a_folder_is_ready_before_its_first_save_and_counts_what_it_keeps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    data = json.loads((PROJECT_ROOT / "config/config.example.json").read_text(encoding="utf-8"))
    data["storage"] = {"folder": str(tmp_path / "archive")}
    config = tmp_path / "config.json"
    config.write_text(json.dumps(data), encoding="utf-8")

    before = _by_name(checks(config))["Storage"]
    (tmp_path / "archive/runs/finished/topic").mkdir(parents=True)
    (tmp_path / "archive/runs/finished/topic/manifest.json").write_text("{}", encoding="utf-8")
    after = _by_name(checks(config))["Storage"]

    assert (before.status, after.status) == ("ready", "ready")
    assert "first save" in before.detail and "1 kept" in after.detail
