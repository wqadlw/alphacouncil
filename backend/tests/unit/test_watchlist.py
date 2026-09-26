"""Watchlist rules: what makes an event one the user could actually have written.

Marked ``unit`` — no database. The two cross-checks at the bottom do read the
migration's SQL, which is the point: the rules are stated in three places (this
module, the request schema, the CHECK constraints) and three copies of a limit
is three places to get it wrong. Those tests make the copies prove they agree.

The append-only guarantee itself is *not* tested here — it lives in triggers and
belongs with the storage tests. Testing it here would assert that Python
behaves, which is not where the guarantee is.
"""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError

import pytest

from alphacouncil.core.error_codes import ErrorCode
from alphacouncil.domain.watchlist import (
    MAX_REASON_CHARS,
    WatchlistError,
    WatchlistEvent,
    WatchlistEventKind,
    WatchlistReasonRequiredError,
    WatchlistReasonTooLongError,
    added,
    reason_revised,
    removed,
)
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage import migrate

pytestmark = pytest.mark.unit

SYMBOL = Symbol(market=Market.SH, code="600519")
REASON = "估值到了我算得出来的区间"


class TestAReasonIsRequired:
    """The rule the whole feature rests on: no reason, no entry."""

    def test_a_blank_reason_is_refused(self) -> None:
        for blank in ("", " ", "\t\n  "):
            with pytest.raises(WatchlistReasonRequiredError) as caught:
                added(SYMBOL, blank)
            assert caught.value.code is ErrorCode.WATCHLIST_REASON_REQUIRED

    def test_a_blank_reason_on_a_revision_is_refused(self) -> None:
        with pytest.raises(WatchlistReasonRequiredError):
            reason_revised(SYMBOL, "   ", supersedes_id=1)

    def test_leaving_needs_no_reason(self) -> None:
        """The asymmetry is deliberate: joining is a claim, leaving is not."""
        assert removed(SYMBOL).reason is None

    def test_a_blank_reason_when_leaving_is_still_refused(self) -> None:
        """Optional is not the same as "any string, including nothing"."""
        with pytest.raises(WatchlistReasonRequiredError):
            removed(SYMBOL, reason="   ")

    def test_the_error_is_catchable_as_a_watchlist_error(self) -> None:
        with pytest.raises(WatchlistError):
            added(SYMBOL, "")


class TestReasonNormalisation:
    def test_surrounding_whitespace_is_trimmed(self) -> None:
        assert added(SYMBOL, f"  {REASON}  ").reason == REASON

    def test_a_reason_of_exactly_the_ceiling_is_accepted(self) -> None:
        assert len(added(SYMBOL, "x" * MAX_REASON_CHARS).reason or "") == MAX_REASON_CHARS

    def test_one_character_over_the_ceiling_is_refused(self) -> None:
        with pytest.raises(WatchlistReasonTooLongError) as caught:
            added(SYMBOL, "x" * (MAX_REASON_CHARS + 1))
        assert caught.value.code is ErrorCode.WATCHLIST_REASON_TOO_LONG

    def test_the_ceiling_is_measured_after_trimming(self) -> None:
        """Otherwise the domain would accept what the database then rejects.

        The CHECK measures the stored value, and the stored value is trimmed —
        so a reason padded past the ceiling has to be judged on its real length.
        """
        padded = " " * 500 + "x" * MAX_REASON_CHARS + " " * 500
        assert added(SYMBOL, padded).reason == "x" * MAX_REASON_CHARS


class TestWhichRulesAreSignatures:
    """Two of the three rules are enforced by the type system, not by a check."""

    def test_adding_without_a_reason_is_a_type_error(self) -> None:
        """Not a runtime validation — the argument does not exist to omit."""
        with pytest.raises(TypeError):
            added(SYMBOL)  # type: ignore[call-arg]

    def test_a_revision_without_a_predecessor_is_a_type_error(self) -> None:
        with pytest.raises(TypeError):
            reason_revised(SYMBOL, REASON)  # type: ignore[call-arg]

    def test_adding_cannot_supersede_anything(self) -> None:
        with pytest.raises(TypeError):
            added(SYMBOL, REASON, supersedes_id=1)  # type: ignore[call-arg]

    def test_leaving_cannot_supersede_anything(self) -> None:
        with pytest.raises(TypeError):
            removed(SYMBOL, supersedes_id=1)  # type: ignore[call-arg]


class TestDirectConstruction:
    """The dataclass is public, so it has to defend itself."""

    def test_constructing_without_a_reason_is_refused(self) -> None:
        with pytest.raises(WatchlistReasonRequiredError):
            WatchlistEvent(WatchlistEventKind.ADDED, SYMBOL)

    def test_constructing_a_revision_without_a_reason_is_refused(self) -> None:
        with pytest.raises(WatchlistReasonRequiredError):
            WatchlistEvent(WatchlistEventKind.REASON_REVISED, SYMBOL, supersedes_id=1)

    def test_constructing_still_normalises(self) -> None:
        event = WatchlistEvent(WatchlistEventKind.ADDED, SYMBOL, reason=f"  {REASON}  ")
        assert event.reason == REASON

    def test_the_result_is_immutable(self) -> None:
        event = added(SYMBOL, REASON)
        with pytest.raises(FrozenInstanceError):
            event.reason = "something else"  # type: ignore[misc]


class TestTheEventCarriesAValidatedInstrument:
    def test_the_symbol_is_carried_whole(self) -> None:
        """Taking a ``Symbol`` rather than a market and a code means an event
        cannot exist without an instrument that already passed validation."""
        event = added(SYMBOL, REASON)
        assert event.symbol == SYMBOL
        assert event.symbol.market is Market.SH


# ---------------------------------------------------------------------------
# Cross-checks: the Python constants must match the SQL that actually ships.
# ---------------------------------------------------------------------------


def _initial_migration_sql() -> str:
    """The shipped schema, read from the migration the manifest names."""
    migrations = {item.version: item for item in migrate.load_migrations()}
    return migrations[1].up.read_text(encoding="utf-8")


def _sql_values(constraint: str, sql: str) -> list[str]:
    """The quoted literals inside one named CHECK constraint.

    The body is found by counting parentheses rather than with a lazy regex.
    These bodies nest — the supersedes check is ``((a) = (b))`` — so a pattern
    written to stop at ``))`` skips the single-paren constraints and then spans
    *two* of them, reporting a union of both. That failure is silent and
    plausible, which is exactly what these cross-checks exist to prevent, so the
    reader has to be exact too.
    """
    start = sql.index(f"CONSTRAINT {constraint}")
    cursor = sql.index("CHECK (", start) + len("CHECK (")
    depth = 1
    end = cursor
    while depth:
        depth += (sql[end] == "(") - (sql[end] == ")")
        end += 1
    return re.findall(r"'([a-z_]+)'", sql[cursor:end])


class TestTheConstantsMatchTheSchema:
    """A limit stated twice must be stated the same way twice."""

    def test_the_kind_enum_matches_the_kind_constraint(self) -> None:
        declared = _sql_values("watchlist_events_kind_check", _initial_migration_sql())
        assert set(declared) == {kind.value for kind in WatchlistEventKind}

    def test_the_reason_ceiling_matches_the_length_constraint(self) -> None:
        sql = _initial_migration_sql()
        match = re.search(r"length\(reason\) <= (\d+)", sql)
        assert match is not None, "the reason length constraint is missing"
        assert int(match.group(1)) == MAX_REASON_CHARS

    def test_only_a_revision_supersedes_in_the_schema_too(self) -> None:
        """The Python side enforces this with signatures; SQL enforces it with
        an equivalence. If they ever disagreed, one of them would be lying."""
        declared = _sql_values("watchlist_events_supersedes_check", _initial_migration_sql())
        assert set(declared) == {WatchlistEventKind.REASON_REVISED.value}

    def test_only_leaving_may_omit_a_reason_in_the_schema_too(self) -> None:
        declared = _sql_values("watchlist_events_reason_required_check", _initial_migration_sql())
        assert set(declared) == {WatchlistEventKind.REMOVED.value}

    def test_the_reason_is_required_for_exactly_the_kinds_python_requires(self) -> None:
        """Computed from the schema, compared against the enum — so adding a
        fourth kind without deciding its reason rule fails here rather than in
        a user's hands."""
        sql = _initial_migration_sql()
        optional = set(_sql_values("watchlist_events_reason_required_check", sql))
        required = {kind.value for kind in WatchlistEventKind} - optional
        assert required == {
            WatchlistEventKind.ADDED.value,
            WatchlistEventKind.REASON_REVISED.value,
        }
