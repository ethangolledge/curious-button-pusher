"""Every dollar is accounted for: the ledger records what each run and tool spent, what the
person said they have, and each provider's own figures; it calibrates what nobody priced from
the difference, and the report says what is left and what to watch."""

from dataclasses import replace
from pathlib import Path

import pytest

import content.providers.openrouter as openrouter
from content.cli.spend import _report, ledger_for
from content.config import ContentConfig, load_config
from content.providers.base import Usage
from content.providers.openrouter import Account
from content.spend import Ledger
from content.state import CallRecord, call_record

PROJECT_ROOT = Path(__file__).parents[1]


def _call(operation: str, cost: float | None, model: str = "a-model") -> CallRecord:
    return call_record(operation, Usage(model=model, cost_usd=cost), 1.0)


def test_spend_is_recorded_by_stage_and_by_what_spent_it(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "spend.sqlite")

    ledger.record(
        [_call("research", 0.40), _call("keyframe", 0.05), _call("narration", None)],
        source="the-dam",
        session="session-1",
    )
    ledger.record(
        [_call("voice_audition", 0.02)], source="voice-audition", session="x", stage="tools"
    )

    spent = Ledger(tmp_path / "spend.sqlite").spent()  # a new process reads the same ledger
    assert spent.priced_usd == pytest.approx(0.47)
    assert (spent.calls, spent.unpriced_calls, spent.unpriced_takes) == (4, 1, 1)
    assert spent.by_stage["writing"] == pytest.approx(0.40)
    assert spent.by_stage["pictures"] == pytest.approx(0.05)
    assert spent.by_stage["tools"] == pytest.approx(0.02)
    assert spent.by_source == {
        "the-dam": pytest.approx(0.45),
        "voice-audition": pytest.approx(0.02),
    }


def test_what_the_provider_charged_calibrates_what_nobody_priced(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "spend.sqlite")
    ledger.record_balance("openrouter", credits_usd=20.0, used_usd=10.0, remaining_usd=10.0)
    ledger.record(
        [_call("keyframe", 0.50), *(_call("narration", None) for _ in range(4))],
        source="the-dam",
        session="session-1",
    )
    ledger.record_balance("openrouter", credits_usd=20.0, used_usd=10.90, remaining_usd=9.10)

    reconciled = ledger.reconcile()

    assert reconciled is not None
    assert reconciled.provider_usd == pytest.approx(0.90)
    assert reconciled.recorded_usd == pytest.approx(0.50)
    # The four unpriced takes explain the rest: each really cost $0.10.
    assert reconciled.unexplained_usd == pytest.approx(0.40)
    assert reconciled.take_usd == pytest.approx(0.10)


def test_what_the_person_said_they_have_is_kept_and_replaced(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "spend.sqlite")
    ledger.set_budget("openrouter", 10.0, "credit")
    ledger.set_budget("openrouter", 25.0, "credit", "topped up")
    ledger.set_budget("google-cloud", 1.0, "monthly")

    budgets = ledger.budgets()

    assert (budgets["openrouter"].amount_usd, budgets["openrouter"].note) == (25.0, "topped up")
    assert budgets["google-cloud"].kind == "monthly"


def test_an_offline_configuration_keeps_no_ledger(app_config: ContentConfig) -> None:
    assert ledger_for(app_config) is None


def test_the_report_says_what_is_left_and_warns_before_it_runs_out(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = load_config(PROJECT_ROOT / "config/config.example.json")
    config = replace(config, storage=None)
    ledger = Ledger(tmp_path / "spend.sqlite")
    ledger.set_budget("openrouter", 10.0, "credit")
    ledger.record([_call("research", 0.40)], source="the-dam", session="session-1")
    monkeypatch.setattr(
        openrouter,
        "account_balance",
        lambda: Account(
            credits_usd=10.0,
            used_usd=7.0,
            key_limit_usd=10.0,
            key_remaining_usd=3.0,
            key_expires="2026-10-20T00:00:00Z",
        ),
    )

    report = "\n".join(_report(config, ledger))

    assert "Your budget:    $10.00 (credit" in report
    assert "Left in total:  $3.00, for every project" in report
    assert "This project:   $0.40 priced" in report
    assert "under a video's $5.00 cap" in report  # warned before a run lowers its cap
    assert "stops working on 2026-10-20" in report
    assert "No bucket" in report
