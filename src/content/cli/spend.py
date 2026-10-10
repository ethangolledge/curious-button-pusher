"""`content spend`: what has been spent and what is left, on every service, from the channel's
ledger (`themes/<name>/spend.sqlite`) and each provider's own figures; and what the person said
they have (`content spend budget`). Also the helpers every command uses to record its spend."""

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

from content.cli.storage import keep_theme
from content.config import ContentConfig, load_config
from content.errors import ConfigurationError
from content.production.budget import NARRATION_TAKE_USD
from content.spend import Balance, Budget, BudgetKind, Ledger, Service
from content.state import CallRecord

# Google Cloud Storage, Standard class in a US region (checked 2026-10-09; docs/google-cloud.md).
GCS_FREE_GB = 5.0
GCS_USD_PER_GB_MONTH = 0.020
# Warn this long before the OpenRouter key stops working.
EXPIRY_WARNING_DAYS = 30


def ledger_for(config: ContentConfig) -> Ledger | None:
    """The channel's ledger; None for an offline configuration, which spends nothing."""
    if all(model.provider == "fake" for model in config.models.models.values()):
        return None
    return Ledger(config.theme.root / "spend.sqlite")


def record_spend(
    config: ContentConfig,
    calls: list[CallRecord],
    *,
    source: str,
    session: str,
    stage: str | None = None,
) -> None:
    """Every paid call, into the channel's ledger. A tool's calls count under `tools`."""
    ledger = ledger_for(config)
    if ledger is not None and calls:
        ledger.record(calls, source=source, session=session, stage=stage)


def read_openrouter(ledger: Ledger) -> Balance | str:
    """OpenRouter's own figures, recorded in the ledger; the reason if they could not be read."""
    from content.providers.openrouter import account_balance

    try:
        account = account_balance()
    except Exception as exc:
        return f"could not be read ({type(exc).__name__})"
    return ledger.record_balance(
        "openrouter",
        credits_usd=account.credits_usd,
        used_usd=account.used_usd,
        remaining_usd=account.remaining_usd,
        limit_usd=account.key_limit_usd,
        expires=account.key_expires,
    )


def read_bucket(ledger: Ledger, bucket: str) -> Balance | str:
    """What the bucket holds, and this month's cost beyond the free tier, recorded."""
    from content.storage import GcsStore

    try:
        stored = GcsStore(bucket).size("") / 1e9
    except Exception as exc:
        return f"could not be read ({type(exc).__name__})"
    return ledger.record_balance(
        "google-cloud",
        used_usd=round(max(0.0, stored - GCS_FREE_GB) * GCS_USD_PER_GB_MONTH, 4),
        stored_gb=round(stored, 3),
        note=bucket,
    )


def _spend(arguments: list[str]) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="The channel's config.json")
    parser = argparse.ArgumentParser(
        prog="content spend",
        description="What has been spent and what is left, on every service.",
        parents=[common],
    )
    actions = parser.add_subparsers(dest="action")
    budget = actions.add_parser(
        "budget", parents=[common], help="Record what you have on a service"
    )
    budget.add_argument("service", choices=get_args(Service))
    budget.add_argument("amount", type=float, help="In US dollars")
    budget.add_argument(
        "--kind",
        choices=get_args(BudgetKind),
        default="credit",
        help="credit: added to the account; limit: a key's cap; monthly: an alert or allowance",
    )
    budget.add_argument("--note", default="", help="Anything worth remembering about it")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    ledger = ledger_for(config)
    if ledger is None:
        parser.error(
            "This configuration is offline and spends nothing: pass your channel's --config"
        )
    if args.action == "budget":
        ledger.set_budget(args.service, args.amount, args.kind, args.note)
        print(f"Recorded: {args.service}, ${args.amount:.2f} ({args.kind}).")
        keep_theme(config)
        return 0
    print("\n".join(_report(config, ledger)))
    return 0


def _report(config: ContentConfig, ledger: Ledger) -> list[str]:
    lines = [
        f"Spending for {config.theme.spec.name}, kept in {ledger.path}",
        "Every paid call this project makes (videos, channel tools, training) is recorded there: "
        "what made it, "
        "the model, tokens and cost. OpenRouter's own figures are read at the start of every run "
        "and each time this runs.",
        "",
    ]
    budgets = ledger.budgets()
    warnings: list[str] = []
    lines += _openrouter(config, ledger, budgets.get("openrouter"), warnings)
    lines += _google_cloud(config, ledger, budgets.get("google-cloud"), warnings)
    lines += ["", "Not tracked here: your Claude subscription (Claude Code itself)."]
    if warnings:
        lines += ["", "Worth knowing:", *(f"  - {warning}" for warning in warnings)]
    return lines


def _openrouter(
    config: ContentConfig, ledger: Ledger, said: Budget | None, warnings: list[str]
) -> list[str]:
    lines = ["OpenRouter (one key pays for every model)"]
    reading = read_openrouter(ledger)
    if isinstance(reading, str):
        lines.append(f"  Left in total:  {reading}")
    else:
        assert reading.credits_usd is not None and reading.used_usd is not None
        lines.append(
            f"  Left in total:  ${reading.remaining_usd:.2f}, for every project on this account "
            f"(${reading.used_usd:.2f} of ${reading.credits_usd:.2f} credit used"
            + (f"; key limit ${reading.limit_usd:.2f}" if reading.limit_usd is not None else "")
            + ")"
        )
        warnings += _openrouter_warnings(config, reading)
    spent = ledger.spent()
    takes = spent.unpriced_takes
    reconciled = ledger.reconcile()
    take_usd = (reconciled.take_usd if reconciled else None) or NARRATION_TAKE_USD
    calibrated = "calibrated" if reconciled and reconciled.take_usd else "estimated"
    lines.append(
        f"  This project:   ${spent.priced_usd:.2f} priced, in {spent.calls} calls"
        + (
            f"; {takes} narration takes unpriced (about ${takes * take_usd:.2f} at "
            f"${take_usd:.2f} each, {calibrated})"
            if takes
            else ""
        )
    )
    if reconciled is not None:
        lines.append(
            f"  Since {reconciled.since[:16].replace('T', ' ')}: OpenRouter counted "
            f"${reconciled.provider_usd:.2f}, the ledger priced ${reconciled.recorded_usd:.2f}"
            + (
                f" (${reconciled.unexplained_usd:.2f} not priced here: unpriced takes, or spend "
                "from another machine or the website)"
                if abs(reconciled.unexplained_usd) >= 0.01
                else ": all of it seen"
            )
        )
    else:
        lines.append("  Calibration:    starts with the next reading (each run reads OpenRouter)")
    stages = ", ".join(f"{s} ${v:.2f}" for s, v in spent.by_stage.items() if v >= 0.005)
    sources = ", ".join(f"{s} ${v:.2f}" for s, v in sorted(spent.by_source.items()))
    lines += [
        f"  By stage:       {stages or 'nothing yet'}",
        f"  By video or tool: {sources or 'nothing yet'}",
    ]
    if said is not None:
        lines.append(f"  Your budget:    {_budget(said)}")
    return lines


def _openrouter_warnings(config: ContentConfig, reading: Balance) -> list[str]:
    warnings = []
    cap = config.production.max_usd if config.production else None
    if reading.remaining_usd is not None and cap is not None and reading.remaining_usd < cap:
        warnings.append(
            f"OpenRouter has ${reading.remaining_usd:.2f} left, under a video's ${cap:.2f} cap: "
            "the next run lowers its cap to fit (fewer scenes). Add credit at openrouter.ai."
        )
    if reading.expires:
        left = (
            datetime.fromisoformat(reading.expires.replace("Z", "+00:00")) - datetime.now(UTC)
        ).days
        if left <= EXPIRY_WARNING_DAYS:
            warnings.append(
                f"The OpenRouter key stops working on {reading.expires[:10]} ({left} days): "
                "make a new one at openrouter.ai (Settings → Keys) and put it in .env."
            )
    return warnings


def _google_cloud(
    config: ContentConfig, ledger: Ledger, said: Budget | None, warnings: list[str]
) -> list[str]:
    lines = ["", "Google Cloud (the bucket)"]
    if config.storage is None:
        return [*lines, "  No bucket: nothing is stored or spent there (docs/google-cloud.md)."]
    if said is not None:
        lines.append(f"  Your budget:    {_budget(said)}")
    reading = read_bucket(ledger, config.storage.bucket)
    if isinstance(reading, str):
        return [*lines, f"  {config.storage.bucket}: {reading}"]
    assert reading.stored_gb is not None and reading.used_usd is not None
    lines.append(
        f"  {config.storage.bucket}: {reading.stored_gb:.2f} GB of {GCS_FREE_GB:.0f} GB free; "
        f"about ${reading.used_usd:.2f} this month (beyond the free tier, "
        f"${GCS_USD_PER_GB_MONTH:.3f} per GB a month)"
    )
    if reading.stored_gb > GCS_FREE_GB * 0.8:
        warnings.append(
            f"The bucket holds {reading.stored_gb:.1f} GB, near the free {GCS_FREE_GB:.0f} GB: "
            "beyond it, storage costs a little (docs/google-cloud.md)."
        )
    return lines


def _budget(said: Budget) -> str:
    note = f": {said.note}" if said.note else ""
    return f"${said.amount_usd:.2f} ({said.kind}, {said.set_at[:10]}){note}"


COMMANDS = {"spend": _spend}
