"""What has been spent, and what is left: one ledger per channel, `themes/<name>/spend.sqlite`
(a SQLite database, private and kept with the channel).

Three tables:

- `calls`: every paid call (a run's, a channel tool's, training's), with what made it, its
  stage, model, tokens and cost. A call the provider did not price (narration takes) has no
  cost, and is counted separately.
- `budgets`: what the person said they have on each service: credit added, a key's limit, a
  monthly alert.
- `balances`: each service's own figures whenever they are read (OpenRouter: credit added and
  used; Google Cloud: storage used). Comparing two readings with the calls recorded between them
  shows what the ledger could not see: unpriced takes, and spend from elsewhere.

Plain SQL in one small module; nothing here calls a provider.
"""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from content.state import CallRecord

Service = Literal["openrouter", "google-cloud"]
BudgetKind = Literal["credit", "limit", "monthly"]
# Where a call's spend counts, by what made it.
STAGES = ("writing", "checks", "narration", "pictures", "morphs", "music", "tools")

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    service TEXT NOT NULL,
    source TEXT NOT NULL,      -- the run folder, or the tool, that spent it
    session TEXT NOT NULL,     -- which session of that run, or when the tool ran
    stage TEXT NOT NULL,
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    cost_usd REAL,             -- NULL: the provider did not price it
    input_tokens INTEGER,
    output_tokens INTEGER,
    seconds REAL
);
CREATE TABLE IF NOT EXISTS budgets (
    service TEXT PRIMARY KEY,
    amount_usd REAL NOT NULL,
    kind TEXT NOT NULL,
    set_at TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    service TEXT NOT NULL,
    credits_usd REAL,          -- everything ever added (OpenRouter)
    used_usd REAL,             -- everything ever used, or this month's projected cost
    remaining_usd REAL,        -- what can still be spent: the account, or the key's limit
    limit_usd REAL,
    stored_gb REAL,            -- Google Cloud: what the bucket holds
    expires TEXT,              -- when the key stops working
    note TEXT NOT NULL
);
"""


def cost_stage(operation: str) -> str:
    """Which stage a call's spend counts under."""
    if operation.startswith("judge_") or operation == "perception":
        return "checks"
    return {
        "narration": "narration",
        "transcription": "narration",
        "reference_download": "pictures",
        "keyframe": "pictures",
        "segment": "morphs",
        "music": "music",
    }.get(operation, "writing")


@dataclass(frozen=True)
class Budget:
    service: str
    amount_usd: float
    kind: str
    set_at: str
    note: str


@dataclass(frozen=True)
class Balance:
    at: str
    service: str
    credits_usd: float | None
    used_usd: float | None
    remaining_usd: float | None
    limit_usd: float | None
    stored_gb: float | None
    expires: str | None
    note: str


@dataclass(frozen=True)
class Spent:
    """What the ledger recorded: priced spend, and the calls nobody priced."""

    priced_usd: float
    calls: int
    unpriced_calls: int
    unpriced_takes: int
    by_stage: dict[str, float]
    by_source: dict[str, float]


@dataclass(frozen=True)
class Reconciliation:
    """The provider's own used figure against the ledger, between two balance readings."""

    since: str
    provider_usd: float
    recorded_usd: float
    unpriced_takes: int

    @property
    def unexplained_usd(self) -> float:
        """Spent according to the provider, and not priced in the ledger."""
        return round(self.provider_usd - self.recorded_usd, 4)

    @property
    def take_usd(self) -> float | None:
        """What an unpriced narration take really cost, when takes explain the gap."""
        if self.unpriced_takes == 0 or self.unexplained_usd <= 0:
            return None
        return round(self.unexplained_usd / self.unpriced_takes, 4)


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(
        self,
        calls: Sequence[CallRecord],
        *,
        source: str,
        session: str,
        stage: str | None = None,
        service: Service = "openrouter",
    ) -> None:
        """Every paid call from one session of a run, or one use of a tool (`stage` "tools")."""
        at = now()
        with self._connect() as db:
            db.executemany(
                "INSERT INTO calls (at, service, source, session, stage, operation, model, "
                "cost_usd, input_tokens, output_tokens, seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        at,
                        service,
                        source,
                        session,
                        stage or cost_stage(call["operation"]),
                        call["operation"],
                        call["model"],
                        call["cost_usd"],
                        call["input_tokens"],
                        call["output_tokens"],
                        call["seconds"],
                    )
                    for call in calls
                ],
            )

    def set_budget(
        self, service: Service, amount_usd: float, kind: BudgetKind, note: str = ""
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO budgets (service, amount_usd, kind, set_at, note) VALUES (?,?,?,?,?) "
                "ON CONFLICT(service) DO UPDATE SET amount_usd=excluded.amount_usd, "
                "kind=excluded.kind, set_at=excluded.set_at, note=excluded.note",
                (service, amount_usd, kind, now(), note),
            )

    def budgets(self) -> dict[str, Budget]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT service, amount_usd, kind, set_at, note FROM budgets"
            ).fetchall()
        return {row[0]: Budget(*row) for row in rows}

    def record_balance(
        self,
        service: Service,
        *,
        credits_usd: float | None = None,
        used_usd: float | None = None,
        remaining_usd: float | None = None,
        limit_usd: float | None = None,
        stored_gb: float | None = None,
        expires: str | None = None,
        note: str = "",
    ) -> Balance:
        balance = Balance(
            now(),
            service,
            credits_usd,
            used_usd,
            remaining_usd,
            limit_usd,
            stored_gb,
            expires,
            note,
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO balances (at, service, credits_usd, used_usd, remaining_usd, "
                "limit_usd, stored_gb, expires, note) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    balance.at,
                    balance.service,
                    balance.credits_usd,
                    balance.used_usd,
                    balance.remaining_usd,
                    balance.limit_usd,
                    balance.stored_gb,
                    balance.expires,
                    balance.note,
                ),
            )
        return balance

    def balances(self, service: Service) -> list[Balance]:
        """Every reading of a service, oldest first."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT at, service, credits_usd, used_usd, remaining_usd, limit_usd, stored_gb, "
                "expires, note FROM balances WHERE service = ? ORDER BY id",
                (service,),
            ).fetchall()
        return [Balance(*row) for row in rows]

    def spent(self, service: Service = "openrouter", *, since: str = "", until: str = "~") -> Spent:
        """What the ledger recorded for a service: all of it, or between two moments."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT source, stage, operation, cost_usd FROM calls "
                "WHERE service = ? AND at > ? AND at <= ?",
                (service, since, until),
            ).fetchall()
        by_stage = dict.fromkeys(STAGES, 0.0)
        by_source: dict[str, float] = {}
        for source, stage, _, cost in rows:
            by_stage[stage] = by_stage.get(stage, 0.0) + (cost or 0.0)
            by_source[source] = by_source.get(source, 0.0) + (cost or 0.0)
        return Spent(
            priced_usd=round(sum(cost or 0.0 for *_, cost in rows), 4),
            calls=len(rows),
            unpriced_calls=sum(1 for *_, cost in rows if cost is None),
            unpriced_takes=sum(
                1 for _, _, operation, cost in rows if cost is None and operation == "narration"
            ),
            by_stage={stage: round(value, 4) for stage, value in by_stage.items()},
            by_source={source: round(value, 4) for source, value in by_source.items()},
        )

    def reconcile(self) -> Reconciliation | None:
        """OpenRouter's used figure, from its first reading here to its latest, against what
        the ledger priced in between. None until there are two readings."""
        readings = [b for b in self.balances("openrouter") if b.used_usd is not None]
        if len(readings) < 2:
            return None
        first, latest = readings[0], readings[-1]
        assert first.used_usd is not None and latest.used_usd is not None
        between = self.spent(since=first.at, until=latest.at)
        return Reconciliation(
            since=first.at,
            provider_usd=round(latest.used_usd - first.used_usd, 4),
            recorded_usd=between.priced_usd,
            unpriced_takes=between.unpriced_takes,
        )


def now() -> str:
    """The moment, as the ledger writes it: UTC, to the microsecond, so that calls and the
    balance readings around them always sort in the order they happened."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
