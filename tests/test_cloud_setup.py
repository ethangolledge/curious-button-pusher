"""`content cloud setup` makes the bucket exactly as docs/google-cloud.md says, corrects one that
is set up differently, never makes anything twice, and stops at the first step only the person
can do, without touching anything after it. gcloud is stood in for: nothing reaches Google."""

import json
import shutil
from pathlib import Path

import pytest

from content.cli.cloud import Result, setup

PROJECT_ROOT = Path(__file__).parents[1]
CORRECT = {
    "location": "US-EAST1",
    "default_storage_class": "STANDARD",
    "uniform_bucket_level_access": True,
    "public_access_prevention": "enforced",
    "soft_delete_policy": {"retentionDurationSeconds": "0"},
}


class FakeGcloud:
    """Answers gcloud commands by their first words, and records every command asked."""

    def __init__(self, **overrides: Result) -> None:
        self.asked: list[tuple[str, ...]] = []
        self.answers = {
            "auth list": Result(True, "someone@example.com", ""),
            "config get-value": Result(True, "my-project", ""),
            "billing projects": Result(True, "True", ""),
            "services enable": Result(True, "", ""),
            "storage buckets describe": Result(False, "", "ERROR: gs://b not found: 404."),
            "storage buckets create": Result(True, "", ""),
            "storage buckets update": Result(True, "", ""),
            **{key.replace("_", " "): value for key, value in overrides.items()},
        }

    def __call__(self, *arguments: str) -> Result:
        self.asked.append(arguments)
        for words, answer in self.answers.items():
            if " ".join(arguments).startswith(words):
                return answer
        raise AssertionError(f"unexpected gcloud {arguments}")

    def ran(self, words: str) -> list[tuple[str, ...]]:
        return [asked for asked in self.asked if " ".join(asked).startswith(words)]


@pytest.fixture
def channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("content.cli.cloud.shutil.which", lambda _: "/usr/bin/gcloud")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "signed-in")
    config = tmp_path / "config.json"
    shutil.copyfile(PROJECT_ROOT / "config/config.example.json", config)
    return config


def _kept(_: Path) -> str:
    return "my-channel: 9 files"


def test_a_new_bucket_is_made_private_free_tier_and_without_soft_delete(channel: Path) -> None:
    gcloud = FakeGcloud()

    done = setup("my-videos", channel, gcloud=gcloud, keep=_kept)

    assert [check.status for check in done] == ["ready"] * len(done)
    assert gcloud.ran("storage buckets create") == [
        (
            "storage", "buckets", "create", "gs://my-videos", "--project=my-project",
            "--location=us-east1", "--default-storage-class=STANDARD",
            "--uniform-bucket-level-access", "--public-access-prevention",
            "--soft-delete-duration=0",
        )
    ]  # fmt: skip
    assert json.loads(channel.read_text())["storage"] == {"bucket": "my-videos"}
    assert done[-1].detail == "kept my-channel: 9 files"


def test_an_existing_bucket_is_corrected_not_made_again(channel: Path) -> None:
    drifted = {**CORRECT, "soft_delete_policy": {"retentionDurationSeconds": "604800"}}
    gcloud = FakeGcloud(storage_buckets_describe=Result(True, json.dumps(drifted), ""))

    setup("my-videos", channel, gcloud=gcloud, keep=_kept)

    assert gcloud.ran("storage buckets create") == []
    assert gcloud.ran("storage buckets update") == [
        ("storage", "buckets", "update", "gs://my-videos", "--soft-delete-duration=0")
    ]


def test_running_it_again_changes_nothing(channel: Path) -> None:
    gcloud = FakeGcloud(storage_buckets_describe=Result(True, json.dumps(CORRECT), ""))
    setup("my-videos", channel, gcloud=gcloud, keep=_kept)
    before = channel.read_text()

    done = setup("my-videos", channel, gcloud=gcloud, keep=_kept)

    assert gcloud.ran("storage buckets create") == gcloud.ran("storage buckets update") == []
    assert channel.read_text() == before
    assert "already" in done[-2].detail


@pytest.mark.parametrize(
    ("gcloud", "stops_at", "fix"),
    [
        (FakeGcloud(auth_list=Result(True, "", "")), "Signed in", "gcloud auth login"),
        (FakeGcloud(billing_projects=Result(True, "False", "")), "Billing", "step 4"),
        (
            FakeGcloud(storage_buckets_create=Result(False, "", "HTTPError 409: not available")),
            "Bucket",
            "taken",
        ),
    ],
    ids=["not signed in", "billing off", "name taken"],
)
def test_it_stops_at_the_first_step_the_person_must_do(
    channel: Path, gcloud: FakeGcloud, stops_at: str, fix: str
) -> None:
    before = channel.read_text()

    done = setup("my-videos", channel, gcloud=gcloud, keep=_kept)

    assert (done[-1].name, done[-1].status) == (stops_at, "missing")
    assert fix in done[-1].fix
    assert channel.read_text() == before  # the channel is connected only once the bucket exists
