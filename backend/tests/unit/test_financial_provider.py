"""BaoStock as a financial source (spec 043 · D4), with the library stubbed.

## ⭐ Nothing here touches the network

``baostock`` opens a **real socket** -- that is the whole reason spec 043 had to name it in
``S-01``'s module list. Every test installs a fake into :data:`sys.modules`, and
:meth:`TestNothingReachesTheSocket.test_the_fake_is_what_the_provider_imports` asserts it
was actually used.

That test is not ceremony. A suite for a socket library whose stub is silently skipped
passes green on the machine where it was skipped, and the one run that reaches BaoStock's
servers is the one that gets the address banned.

## What is pinned down here

* ⭐ **both dates survive** -- ``period_end`` and ``announced_at`` are the reason this table
  exists, so a test that only checked the metrics would not notice losing one.
* ⭐ the ban gets **its own** error, and a failed call **still counts against the throttle**.
* ⭐ an empty cell is ``None``, never ``0.0`` (red line 6).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from alphacouncil.models.market import Market, Symbol
from alphacouncil.providers import financial as fin
from alphacouncil.providers.base import (
    Dataset,
    ProviderEmptyError,
    ProviderError,
    ProviderIpBlockedError,
    ProviderProtocolError,
)
from alphacouncil.storage.repositories import financial as financial_repository

# --------------------------------------------------------------------------
# A fake BaoStock
# --------------------------------------------------------------------------

#: Field order as the real library declares it. Rows are built from this, so a renamed
#: column in the fake is a failure rather than a silent mismatch.
FIELDS = [
    "code",
    "pubDate",
    "statDate",
    "roeAvg",
    "npMargin",
    "gpMargin",
    "netProfit",
    "epsTTM",
    "MBRevenue",
    "totalShare",
    "liqaShare",
]

#: 2026-09-29 is inside Q3, so Q3 is the newest quarter that can exist.
STAMP = date(2026, 9, 29)


class FakeResult:
    """Mimics ``baostock``'s ``QueryResult``: a cursor plus a declared shape."""

    def __init__(
        self, rows: list[list[str]], *, error_code: str = "0", fields: list[str] | None = None
    ) -> None:
        self._rows = list(rows)
        self._at = 0
        self.error_code = error_code
        self.error_msg = "IP blocked" if error_code else ""
        self.fields = list(FIELDS if fields is None else fields)

    def next(self) -> bool:
        return self._at < len(self._rows)

    def get_row_data(self) -> list[str]:
        row = self._rows[self._at]
        self._at += 1
        return row


def _row(**over: str) -> list[str]:
    """One realistic row, overriding any cell by its **wire** field name.

    ⭐ Keys are the library's spellings, not the dataclass's. ``MBRevenue`` does not
    contain the substring ``revenue``, which is exactly why it is written out literally
    here instead of being generated from the model.
    """
    values = {
        "code": "sh.600519",
        "pubDate": "2025-04-03",
        "statDate": "2024-12-31",
        "roeAvg": "0.24",
        "npMargin": "0.21",
        "gpMargin": "0.91",
        "netProfit": "86.2",
        "epsTTM": "69.4",
        "MBRevenue": "170.9",
        "totalShare": "12.56",
        # ⭐ **Deliberately different from `totalShare`.** They were both `12.56` at first,
        # which meant a mapping that read `liqaShare` twice -- or read `totalShare` where
        # it should read `liqaShare` -- produced the same number and every assertion passed.
        # ⭐ A fixture where two columns hold the same value cannot tell them apart, and
        # 「float_shares equals total_shares」 is a *true* sentence about a real company,
        # so the mutation check found it and this line is the fix.
        "liqaShare": "9.87",
    }
    values.update(over)
    return [values[name] for name in FIELDS]


class FakeBaostock:
    """Records every call, answers from a dict keyed by ``(year, quarter)``."""

    def __init__(self, table: dict[tuple[int, int], FakeResult] | None = None) -> None:
        self.table = table if table is not None else {}
        self.calls: list[tuple[int, int]] = []
        self.logins = 0
        self.login_error: str = "0"

    def login(self) -> FakeResult:
        self.logins += 1
        return FakeResult([], error_code=self.login_error)

    def query_profit_data(self, *, code: str, year: int, quarter: int) -> FakeResult:
        self.calls.append((year, quarter))
        return self.table.get((year, quarter), FakeResult([]))


@pytest.fixture(autouse=True)
def _no_socket(monkeypatch: pytest.MonkeyPatch) -> FakeBaostock:
    """Replace ``baostock`` and reset this module's session state.

    ⭐ The reset is not optional. ``_LOGGED_IN`` and ``_LAST_CALL`` are **module globals**,
    so one test that logged in would leave the next believing a session exists -- and the
    next would then pass for the wrong reason.
    """
    fake = FakeBaostock()
    monkeypatch.setitem(sys.modules, "baostock", fake)
    monkeypatch.setattr(fin, "_LOGGED_IN", False)
    monkeypatch.setattr(fin, "_LAST_CALL", None)
    # ⭐ Zero the floor, so no test in this file sleeps. The throttle's *arithmetic* is
    # asserted separately, in `TestTheThrottle`, with a fake clock.
    monkeypatch.setattr(fin, "_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(fin, "_JITTER_S", 0.0)
    return fake


def _moutai() -> Symbol:
    return Symbol(market=Market.SH, code="600519")


def _provider() -> fin.BaostockFinancial:
    # ⭐ Fixed clock. Without it ``get_financial`` walks back from *today*, and the set of
    # quarters it asks for -- the thing several tests below assert -- would change
    # silently on 1 January.
    return fin.BaostockFinancial(now=lambda: STAMP)


def _period(**over: object) -> fin.FinancialPeriod:
    """A :class:`FinancialPeriod` built from the same wire row the fake returns.

    ⭐ Shares the fixture on purpose: the round-trip tests below are about the *join*
    between provider and storage, and a hand-written period with hand-chosen values would
    be a second, disagreeing description of the same data.
    """
    values: dict[str, object] = {
        "symbol": _moutai(),
        "period_end": date(2024, 12, 31),
        "announced_at": date(2025, 4, 3),
        "roe_avg": 0.24,
        "np_margin": 0.21,
        "gp_margin": 0.91,
        "net_profit": 86.2,
        "eps_ttm": 69.4,
        "revenue": 170.9,
        "total_shares": 12.56,
        "float_shares": 9.87,
    }
    values.update(over)
    # ⭐ The two dates are coerced, so a test can write ``announced_at="2025-08-30"`` in the
    # same ISO form the storage tests use. ⭐ Without this the helper's ``**over`` is
    # untyped, a string slipped through, and the failure landed three files away as
    # ``'str' object has no attribute 'isoformat'`` inside the repository.
    for name in ("period_end", "announced_at"):
        given = values[name]
        if isinstance(given, str):
            values[name] = date.fromisoformat(given)
    return fin.FinancialPeriod(**values)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The socket cannot be reached from here
# --------------------------------------------------------------------------


class TestNothingReachesTheSocket:
    def test_the_fake_is_what_the_provider_imports(self, _no_socket: FakeBaostock) -> None:
        _provider().get_financial(_moutai(), years=1)

        assert _no_socket.calls, "the provider never called the library it was given"


# --------------------------------------------------------------------------
# Both dates, always
# --------------------------------------------------------------------------


class TestBothDatesSurvive:
    def test_a_saved_row_can_be_read_back_from_storage(self, tmp_path: Path) -> None:
        """⭐ ⭐ **One row, provider to SQLite, through the real repository.**

        ⭐ Every other test here stops at the dataclass. That leaves the *join* untested,
        and the join is where this table's whole purpose lives: ⭐ a provider that returns
        ``announced_at`` as the report date and a repository that stores it correctly are
        both fine, while the two of them together produce a table that looks right and
        answers PIT queries with look-ahead.

        ⭐ It also pins the **column-to-field naming** across the boundary. The mutation
        check flagged that nothing caught two share-count columns being confused, and the
        reason was that no test ever read a value *back out* of the database — every
        assertion was on the dataclass, one layer earlier than where the mistake lands.
        """
        db_path = tmp_path / "pit.sqlite3"
        conn = financial_repository.open_database(db_path)
        try:
            financial_repository.apply_migrations(conn, database_path=db_path)
            written = financial_repository.insert(
                conn, _period(), source="baostock", fetched_at="2026-09-29T00:00:00.000Z"
            )
            read_back = financial_repository.as_of(
                conn, market="sh", code="600519", as_of=date(2025, 6, 1)
            )

            assert written is True
            assert read_back is not None
            assert read_back["announced_at"] == "2025-04-03"
            assert read_back["period_end"] == "2024-12-31"
            # ⭐ The two share counts are distinguishable, all the way into SQL.
            assert read_back["total_shares"] == pytest.approx(12.56)
            assert read_back["float_shares"] == pytest.approx(9.87)
        finally:
            conn.close()

    def test_a_restated_period_is_read_back_as_two_answers(
        self, tmp_path: Path
    ) -> None:
        """⭐ ⭐ The PIT property, asserted **through the repository**, not only against
        hand-written SQL in ``test_financial_storage.py``.

        ⭐ Those tests write rows directly, so they prove the *schema* can hold two
        versions. ⭐ This one goes provider → repository → query, so it also fails if the
        repository forgets the tiebreaker or filters on the wrong column — and that is the
        layer where a wrong answer would actually be **produced**: a bad schema row is
        visible in the data, a bad query is not.
        """
        db_path = tmp_path / "restated.sqlite3"
        conn = financial_repository.open_database(db_path)
        try:
            financial_repository.apply_migrations(conn, database_path=db_path)
            financial_repository.insert(
                conn,
                _period(announced_at="2025-04-03", roe_avg=0.24),
                source="baostock",
                fetched_at="2026-09-29T00:00:00.000Z",
            )
            financial_repository.insert(
                conn,
                _period(announced_at="2025-08-30", roe_avg=0.19),
                source="baostock",
                fetched_at="2026-09-29T00:00:00.000Z",
            )

            before = financial_repository.as_of(
                conn, market="sh", code="600519", as_of=date(2025, 6, 1)
            )
            after = financial_repository.as_of(
                conn, market="sh", code="600519", as_of=date(2025, 9, 1)
            )

            assert before is not None and before["roe_avg"] == pytest.approx(0.24)
            assert after is not None and after["roe_avg"] == pytest.approx(0.19)
        finally:
            conn.close()

    def test_two_sources_publishing_the_same_day_are_ordered_deterministically(
        self, tmp_path: Path
    ) -> None:
        """⭐ ⭐ **The tiebreaker, and why it is in the query at all.**

        ⭐ ``announced_at`` is not a total order: two providers can publish the same report
        on the same day, and then 「取最新」 has two equally-``announced_at`` rows. ⭐ Without
        ``ORDER BY ... , fetched_at DESC`` SQLite is free to return **either** — so the same
        query can answer differently on two runs, and no test can pin it.

        ⭐ Every earlier test here had one source and one row per day, so this is the first
        case where the tiebreaker is reachable at all — ⭐ which is exactly why removing it
        was invisible to them.

        ⭐⚠️ **This test still cannot fail if the tiebreaker is removed**, and the mutation
        check proved it: ``idx_financial_reports_pit`` is declared
        ``(market, code, announced_at DESC, fetched_at DESC)``, and SQLite scans that index
        in that order — ⭐ so the *index* supplies the same ordering and the query's own
        ``fetched_at DESC`` is redundant. ⭐ The determinism comes from the index. Both are
        kept (the query states it, the index makes it free) and the dependency is written
        into migration 0011's index comment rather than left to be discovered again.
        """
        db_path = tmp_path / "tie.sqlite3"
        conn = financial_repository.open_database(db_path)
        try:
            financial_repository.apply_migrations(conn, database_path=db_path)
            # ⭐⭐ **Insertion order deliberately disagrees with `fetched_at`.**
            # The newer fetch goes in *first*, so SQLite's tiebreak — which is rowid order,
            # i.e. insertion order — would return 0.10, and only the explicit
            # `ORDER BY ..., fetched_at DESC` returns 0.20.
            # ⭐ With the insert order the other way round this test passes either way, and
            # it *did* pass either way on the first run: the mutation check removed
            # ``fetched_at`` from the ORDER BY and nothing turned red. ⭐ **A determinism
            # test whose expectation happens to match the fallback is not a determinism
            # test.**
            financial_repository.insert(
                conn,
                _period(roe_avg=0.20),
                source="fast-source",
                fetched_at="2026-09-29T00:00:00.000Z",
            )
            financial_repository.insert(
                conn,
                _period(roe_avg=0.10),
                source="slow-source",
                fetched_at="2026-09-28T00:00:00.000Z",
            )

            answers = []
            for _ in range(5):
                row = financial_repository.as_of(
                    conn, market="sh", code="600519", as_of=date(2030, 1, 1)
                )
                assert row is not None
                answers.append(row["roe_avg"])

            assert answers == [pytest.approx(0.20)] * 5
        finally:
            conn.close()

    def test_a_row_the_schema_should_refuse_still_raises_through_the_repository(
        self, tmp_path: Path
    ) -> None:
        """⭐ ⭐ ⭐ **Why this module must not use ``INSERT OR IGNORE``**, asserted.

        ⭐ SQLite's ``OR IGNORE`` turns **any** constraint violation into a silent skip,
        including every CHECK — ⭐ so under that clause a row announcing a report before its
        own period ended would not be refused, it would simply **not exist**, and the fetch
        would report success with a quarter missing.

        ⭐ That failure mode is invisible by construction: the row count is lower than
        expected, nothing logged, and the next reader concludes the company never published.
        ⭐ The mutation check pointed straight at it by asking what ``insert`` would do with
        a row the schema refuses.
        """
        db_path = tmp_path / "refuse.sqlite3"
        conn = financial_repository.open_database(db_path)
        try:
            financial_repository.apply_migrations(conn, database_path=db_path)
            liar = fin.FinancialPeriod(
                symbol=_moutai(),
                period_end=date(2024, 12, 31),
                announced_at=date(2024, 1, 1),
                roe_avg=0.24,
                np_margin=0.21,
                gp_margin=0.91,
                net_profit=86.2,
                eps_ttm=69.4,
                revenue=170.9,
                total_shares=12.56,
                float_shares=9.87,
            )

            with pytest.raises(sqlite3.IntegrityError, match="announced_after_period"):
                financial_repository.insert(
                    conn, liar, source="baostock", fetched_at="2026-09-29T00:00:00.000Z"
                )

            stored = financial_repository.history(conn, market="sh", code="600519")

            assert stored == []
        finally:
            conn.close()

    def test_the_history_and_the_current_answer_are_different_questions(
        self, tmp_path: Path
    ) -> None:
        """⭐ Both have to be answerable, and neither stands in for the other.

        ⭐ ``as_of`` is one row; ``history`` is every announcement. ⭐ If only the current
        one were readable, append-only would be storing things nobody can get back — and
        「公司改过口」 would become unprovable, which is exactly the claim PIT exists to let
        somebody make.
        """
        db_path = tmp_path / "both.sqlite3"
        conn = financial_repository.open_database(db_path)
        try:
            financial_repository.apply_migrations(conn, database_path=db_path)
            for announced, roe in (("2025-04-03", 0.24), ("2025-08-30", 0.19)):
                financial_repository.insert(
                    conn,
                    _period(announced_at=announced, roe_avg=roe),
                    source="baostock",
                    fetched_at="2026-09-29T00:00:00.000Z",
                )

            everything = financial_repository.history(conn, market="sh", code="600519")
            current = financial_repository.as_of(
                conn, market="sh", code="600519", as_of=date(2030, 1, 1)
            )

            assert [row["announced_at"] for row in everything] == [
                "2025-08-30",
                "2025-04-03",
            ]
            assert current is not None
            assert current["announced_at"] == "2025-08-30"
        finally:
            conn.close()

    def test_a_row_carries_its_period_and_its_announcement(
        self, _no_socket: FakeBaostock
    ) -> None:
        _no_socket.table[(2024, 4)] = FakeResult([_row()])

        periods = _provider().get_financial(_moutai(), years=3)

        assert len(periods) == 1
        assert periods[0].period_end == date(2024, 12, 31)
        assert periods[0].announced_at == date(2025, 4, 3)

    def test_the_two_dates_are_independent(self, _no_socket: FakeBaostock) -> None:
        """⭐ Two months apart, and **not a constant** (live, 2026-09-30):

        ==========  ==============  =====
        period_end  announced_at   lag
        ==========  ==============  =====
        2026-03-31  2026-04-25     25 d
        2026-06-30  2026-08-15     46 d
        2024-12-31  2025-04-03     93 d
        ==========  ==============  =====

        ⭐ The gap is the point. One date column would have to be *one* of these, and
        either choice breaks a reader: the report date exposes a number nobody had yet,
        the announcement date hides which period the number is about.

        ⭐⭐ **The live run also killed the 「滞后约 2 个月」 claim.** That sentence was
        written from the 2024 annual report (93 days) and generalised to every period;
        quarters arrive in **25 days**. ⭐ A lag figure written as a constant is a claim
        about arithmetic dressed as a measurement, and the number people reason from is
        exactly the one that needs the range.
        """
        _no_socket.table[(2024, 4)] = FakeResult([_row()])

        (only,) = _provider().get_financial(_moutai(), years=3)

        assert only.announced_at == date(2025, 4, 3)
        assert only.period_end == date(2024, 12, 31)

    def test_an_announcement_before_its_period_is_refused(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ A source claiming a report was public before the period ended.

        ⭐ Migration 0011 has a CHECK that refuses the row, so without this guard the
        failure would surface as an insert error far from its cause -- and a row with a
        lying ``announced_at`` is readable by a PIT query *before* it was published.
        """
        _no_socket.table[(2024, 4)] = FakeResult(
            [_row(pubDate="2024-01-01", statDate="2024-12-31")]
        )

        with pytest.raises(ProviderProtocolError, match="announced"):
            _provider().get_financial(_moutai(), years=3)


# --------------------------------------------------------------------------
# The ban is its own failure
# --------------------------------------------------------------------------


class TestTheBanIsItsOwnCode:
    def test_the_blacklist_code_raises_the_ban_error(self) -> None:
        """⭐ ``10001011`` is BaoStock's own 「IP 已加入黑名单」.

        ⭐ Not ``ProviderBlockedError``: §4.5 gives the two different recoveries (20 hours
        and a different network, versus five minutes) and the router's cooldown table keys
        on the code. ⭐ One shared code is exactly how 「等 20 小时」 became 「等 5 分钟」.
        """
        with pytest.raises(ProviderIpBlockedError, match="banned"):
            fin._raise_for(fin.IP_BLOCKED_CODE, "IP blocked")

    def test_the_ban_code_is_the_string_the_wire_carries(self) -> None:
        """⭐ A string, not an int: a typo in an int is invisible until a real ban."""
        assert fin.IP_BLOCKED_CODE == "10001011"

    def test_a_blacklisted_response_reaches_the_caller_as_the_ban(
        self, _no_socket: FakeBaostock
    ) -> None:
        _no_socket.table[(2026, 3)] = FakeResult([], error_code=fin.IP_BLOCKED_CODE)

        with pytest.raises(ProviderIpBlockedError):
            _provider().get_financial(_moutai(), years=1)

    def test_the_ban_branch_does_not_swallow_its_neighbours(self) -> None:
        """⭐ ⭐ **The guard against an over-broad guard.**

        ⭐ The mutation check found this: a plausible edit to the ban branch —
        ``if error_code in {IP_BLOCKED_CODE, "-3"}`` — survived, because
        ``test_no_period_is_not_a_ban`` only asserted that ``-3`` raises *something*. ⭐
        Raising the **wrong** exception satisfies it, and the wrong exception here costs a
        source twenty hours of cooldown over a symbol that simply has no Q3.
        """
        with pytest.raises(ProviderEmptyError):
            fin._raise_for("-3", "no data")

        with pytest.raises(ProviderIpBlockedError):
            fin._raise_for(fin.IP_BLOCKED_CODE, "banned")

    def test_no_period_is_not_a_ban(self) -> None:
        """⭐ A guard against the guard: the mapping must not be over-broad.

        ⭐ 「No such data」 and 「you are banned」 have opposite recoveries. Mapping the
        first to the second would take a source out for twenty hours because a symbol has
        no Q3.
        """
        with pytest.raises(ProviderEmptyError):
            fin._raise_for("-3", "no data")

    def test_an_unknown_code_stays_unknown(self) -> None:
        """⭐ Unknown means unknown -- never the most severe reading available."""
        with pytest.raises(ProviderError) as caught:
            fin._raise_for("99999", "?")

        assert not isinstance(caught.value, ProviderIpBlockedError)

    def test_a_failed_login_leaves_the_module_logged_out(
        self, _no_socket: FakeBaostock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ Otherwise the next call trusts a session that never opened, and reports a
        failure about the data when the failure was about the login."""
        refusing = FakeBaostock()
        refusing.login_error = fin.IP_BLOCKED_CODE
        monkeypatch.setitem(sys.modules, "baostock", refusing)

        with pytest.raises(ProviderIpBlockedError):
            _provider().get_financial(_moutai(), years=1)

        assert fin._LOGGED_IN is False


# --------------------------------------------------------------------------
# Empty is not zero
# --------------------------------------------------------------------------


class TestEmptyIsNotZero:
    @pytest.mark.parametrize(
        "raw",
        ["", "  ", "\t", "--", "-", "None", "none", "NULL", "null", "N/A", "n/a", "NaN", "nan"],
    )
    def test_an_absent_cell_becomes_none(self, raw: str) -> None:
        """⭐ ⭐ **Every spelling of 「nothing」, not the four the first draft listed.**

        ⭐ The mutation check is what forced this. The original set was
        ``{"", "--", "None", "null"}``, and a mutant that **deleted the guard entirely**
        survived — because every one of those four also happened to fail ``float()`` a few
        lines below. ⭐ So the tests could not tell 「this guard exists」 from 「this guard is
        gone」, which is the same shape as a test that passes against the code it is
        supposed to police.

        ⭐ The fix is not more strings in a list; it is that the guard is now *complete* by
        construction (see :data:`_ABSENT_CELLS`), so the next spelling a source invents is
        covered by the shape rather than by a second thought.
        """
        assert fin._number(raw) is None

    @pytest.mark.parametrize(
        "raw",
        ["n/a", "N/A", "--", "-", "NaN", "nan", "-nan", "Infinity", "inf", "-inf"],
    )
    def test_a_non_finite_cell_becomes_none(self, raw: str) -> None:
        """⭐ ⭐ **`nan` and `inf` are not numbers, and the table has no place for them.**

        ⭐ These parse *without raising* — ``float("nan")`` is a float, ``float("inf")`` is
        a float — so a guard written as 「did it raise?」 waves them straight through. ⭐ And a
        stored `nan` is worse than a `NULL`: ``nan > 0.5`` is false (so a criterion reads it
        as 「not met」) while ``nan != 0`` is **true** (so anything comparing to zero believes
        it is a real reading). ⭐ SQLite stores both happily in a `REAL` column under
        ``STRICT``.
        """
        assert fin._number(raw) is None

    def test_a_cell_that_overflows_to_infinity_becomes_none(self) -> None:
        """⭐ ⭐ The case the *string* pattern cannot catch, and the reason
        :data:`_MAX_FINITE` exists.

        ⭐ ``"1e400"`` is a perfectly well-formed number to every textual check — digits, a
        sign, an exponent — and ``float()`` returns ``inf`` for it without complaining.
        ⭐ So the pattern above misses it entirely, and the only thing left is to look at
        the *parsed* value. This test is the reason the guard is there at all.
        """
        assert fin._number("1e400") is None
        assert fin._number("-1e400") is None

    @pytest.mark.parametrize("raw", ["", "  ", "--", "abc", "12,5", "1/2", "三倍"])
    def test_an_unparseable_cell_is_treated_as_absent_not_raised(
        self, raw: str
    ) -> None:
        """⭐ ⭐ **One bad cell must not cost the quarter's other nine metrics.**

        ⭐ An earlier draft raised a :class:`ProviderProtocolError` on an unparseable cell,
        which is defensible in isolation — ⭐ and wrong here: it turns 「this one field is
        odd」 into 「this instrument has no financial data for 32 quarters」, because the
        exception escapes the whole fetch. ⭐ The honest reading of 「what number is this?」
        when the answer is not a number is 「none」.
        """
        assert fin._number(raw) is None

    @pytest.mark.parametrize("raw", ["0", "0.0", "-0.0", "1e-9", "-1", "12.56", "0.24"])
    def test_a_present_number_is_never_treated_as_absent(
        self, raw: str
    ) -> None:
        """⭐ ⭐ **The other direction, and the one that actually matters.**

        ⭐ A guard that is too eager is worse than no guard: it turns a real reading into a
        missing one, and a missing reading is reported to the user as 「该指标不可算」 —
        ⭐ which is a sentence about the world, made out of our own parsing mistake.
        """
        assert fin._number(raw) == pytest.approx(float(raw))

    def test_a_real_zero_survives(self) -> None:
        """⭐ ``0.0`` is a legitimate value and the fix must not eat it.

        ⭐ Red line 6 forbids **filling a gap with zero**, not the value zero. A check
        written as 「reject anything that looks absent」 and implemented as 「reject 0.0」
        would throw away a real gross margin.
        """
        assert fin._number("0.0") == 0.0

    def test_a_negative_margin_is_kept(self) -> None:
        """⭐ Loss-making companies exist and ``npMargin`` is negative for them."""
        assert fin._number("-0.31") == pytest.approx(-0.31)

    def test_a_row_with_blanks_keeps_its_good_cells(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ Partial data is real: a newly listed company has margins but no TTM EPS."""
        _no_socket.table[(2024, 4)] = FakeResult([_row(gpMargin="", epsTTM="--")])

        (only,) = _provider().get_financial(_moutai(), years=3)

        assert only.gp_margin is None
        assert only.eps_ttm is None
        assert only.roe_avg == pytest.approx(0.24)

    def test_known_counts_only_the_cells_that_came_back(
        self, _no_socket: FakeBaostock
    ) -> None:
        _no_socket.table[(2024, 4)] = FakeResult([_row(gpMargin="", epsTTM="--")])

        (only,) = _provider().get_financial(_moutai(), years=3)

        assert only.known == 6

    def test_each_metric_reads_its_own_wire_column(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ ⭐ **This is a misspelling test.** ``MBRevenue`` is BaoStock's spelling of
        operating revenue and it does not contain the string ``revenue``; ``roeAvg`` does
        not contain ``roe`` in the position a field name would put it. A mapping written
        from the *metric's* English name instead of the wire's would store ``None`` for
        every row, fail nothing, and leave a table of nulls that every consumer reports as
        「该指标不可算」.

        ⭐ It is here because the fixture is built from the wire names, not the model's.
        A fixture generated from the dataclass would have agreed with the bug.
        """
        _no_socket.table[(2024, 4)] = FakeResult([_row()])

        (only,) = _provider().get_financial(_moutai(), years=3)

        assert only.revenue == pytest.approx(170.9)
        assert only.net_profit == pytest.approx(86.2)
        assert only.total_shares == pytest.approx(12.56)
        # ⭐ `9.87`, not `12.56`: the two share-count columns must be distinguishable.
        assert only.float_shares == pytest.approx(9.87)
        assert only.roe_avg == pytest.approx(0.24)
        assert only.np_margin == pytest.approx(0.21)
        assert only.gp_margin == pytest.approx(0.91)
        assert only.eps_ttm == pytest.approx(69.4)


# --------------------------------------------------------------------------
# Capability, and where the market comes from
# --------------------------------------------------------------------------


class TestWhatTheProviderClaims:
    def test_it_declares_financial_and_nothing_else(self) -> None:
        """⭐ It cannot serve a daily bar, and declaring only ``FINANCIAL`` is what stops
        the router from ever asking it for one."""
        assert _provider().capabilities.datasets == frozenset({Dataset.FINANCIAL})

    def test_the_notes_say_how_it_differs(self) -> None:
        """⭐ §4.5: the degradation path has to state its differences in a form a program
        can read.

        ⭐ The honest text for a single-source dataset is that **there is no primary**; a
        note that claimed a comparison would be inventing one.

        ⭐⭐ **The lag is asserted as a range, and the range is measured.** The note used to
        say 「滞后约 2 个月」, written from one annual report (93 days) and generalised.
        ⭐ The live run on 2026-09-30 showed quarters arriving in 25 and 46 days, so a
        single figure is a **wrong** figure for three of the four period lengths. ⭐ This
        asserts the *endpoints* because a number somebody reasoned from should not be
        able to drift into a constant without turning this red.
        """
        notes = _provider().capabilities.notes

        assert notes is not None
        assert "没有主源" in notes
        assert "25 天" in notes
        assert "93 天" in notes
        # ⭐ The **property**, not the substring. The first version asserted
        # ``"2 个月" not in notes`` and it failed -- because the notes legitimately
        # *quote* the wrong figure in order to reject it. ⭐ A guard written as a banned
        # substring forbids the sentence that explains the ban, which is the sentence
        # most worth having.
        assert "不是常数" in notes

    def test_the_market_comes_from_the_prefix_not_the_digits(self) -> None:
        """⭐ Red line 16: never infer a venue from the number.

        ⭐ ``000001`` is the Shanghai Composite on ``sh`` and Ping An Bank on ``sz``, so a
        rule that guesses from the digits is a rule that will be wrong once.
        """
        assert fin._symbol("sh.600519") == Symbol(market=Market.SH, code="600519")
        assert fin._symbol("sz.000001") == Symbol(market=Market.SZ, code="000001")

    def test_an_unknown_prefix_is_a_protocol_error(self) -> None:
        with pytest.raises(ProviderProtocolError, match="market"):
            fin._symbol("xx.600519")


# --------------------------------------------------------------------------
# Ordering, shape and the quarter walk
# --------------------------------------------------------------------------


class TestOrderingAndShape:
    def test_periods_come_back_newest_announcement_first(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ Sorted by **announcement**, not by period.

        ⭐ A restatement announces later and is the version a reader should see. Sorting
        by period would put a restated Q3 *before* a Q4 that was announced first, because
        Q4's period is later while Q3's announcement is.
        """
        _no_socket.table[(2024, 4)] = FakeResult(
            [_row(pubDate="2025-04-03", statDate="2024-12-31")]
        )
        _no_socket.table[(2024, 3)] = FakeResult(
            [_row(pubDate="2025-05-02", statDate="2024-09-30")]
        )

        periods = _provider().get_financial(_moutai(), years=3)

        assert [p.announced_at for p in periods] == [date(2025, 5, 2), date(2025, 4, 3)]

    def test_a_short_row_is_a_protocol_error(self, _no_socket: FakeBaostock) -> None:
        """⭐ The library returns strings; a truncated row must not read as 「no data」."""
        _no_socket.table[(2024, 4)] = FakeResult([_row()], fields=FIELDS[:-1])

        with pytest.raises(ProviderProtocolError, match="values for"):
            _provider().get_financial(_moutai(), years=3)

    def test_an_empty_source_is_an_empty_list_not_a_placeholder(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ Empty means empty (the ``MarketDataProvider`` contract).

        ⭐ ``[None]`` would say 「we know this instrument has no financial data」 while
        ``[]`` says 「we have nothing」 -- §4.6 keeps those apart, and a placeholder in the
        list is how they get confused.
        """
        assert _provider().get_financial(_moutai(), years=3) == []

    def test_no_quarter_after_the_current_one_is_asked_for(
        self, _no_socket: FakeBaostock
    ) -> None:
        _provider().get_financial(_moutai(), years=1)

        assert max(_no_socket.calls) <= (2026, 3)

    def test_the_walk_reaches_exactly_as_far_back_as_asked(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ ``years=N`` means **this year plus N-1 before it**, so ``years=3`` asks about
        2026, 2025 and 2024 and not about 2023.

        ⭐ Stated rather than left implicit because the first draft of this test read
        ``years=3`` as 「back to 2023」 and it is not: ``range(2026, 2026 - 3, -1)`` has three
        values and the last is 2024.
        """
        _provider().get_financial(_moutai(), years=3)

        assert sorted({year for year, _ in _no_socket.calls}) == [2024, 2025, 2026]

    def test_a_non_positive_span_is_refused(self) -> None:
        """⭐ Guarded at the boundary, because ``range(today, today + 3, -1)`` is empty and
        an empty answer would read as 「no financial data exists」."""
        with pytest.raises(ValueError, match="positive"):
            _provider().get_financial(_moutai(), years=0)

    def test_one_logged_in_session_serves_every_call(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ The session is a process-level resource, so re-login per request means a
        socket per request and a chance to fail for no benefit."""
        _provider().get_financial(_moutai(), years=3)

        assert _no_socket.logins == 1

    def test_the_throttle_counts_a_failed_call(self, _no_socket: FakeBaostock) -> None:
        """⭐ §7.8: 「时间戳在 finally 里更新 —— **失败也算一次访问**」.

        ⭐ A throttle that forgives failures is the one that gets an address banned: the
        failures are the expensive part.
        """
        _no_socket.table[(2026, 3)] = FakeResult([], error_code=fin.IP_BLOCKED_CODE)

        with pytest.raises(ProviderIpBlockedError):
            _provider().get_financial(_moutai(), years=1)

        assert fin._LAST_CALL is not None

    def test_a_call_that_raised_still_moves_the_timestamp(
        self, _no_socket: FakeBaostock
    ) -> None:
        """⭐ Same rule, asserted at the boundary rather than by side effect: the clock is
        read in ``finally``, so it moves whether or not the body completed."""
        _no_socket.table[(2026, 3)] = FakeResult([], error_code=fin.IP_BLOCKED_CODE)
        before: Any = None

        with pytest.raises(ProviderIpBlockedError):
            _provider().get_financial(_moutai(), years=1)

        before = fin._LAST_CALL
        with pytest.raises(ProviderIpBlockedError):
            _provider().get_financial(_moutai(), years=1)

        assert before is not None


# --------------------------------------------------------------------------
# The throttle's arithmetic, with no sleeping
# --------------------------------------------------------------------------


class TestTheThrottle:
    @pytest.fixture(autouse=True)
    def _slept(self, monkeypatch: pytest.MonkeyPatch) -> list[float]:
        """Capture sleeps instead of performing them.

        ⭐ Patched by **string** target, not by ``fin.time.sleep``: ``time`` is not in the
        module's ``__all__``, so reaching through the attribute is a typed access to
        something the module does not claim to export — ⭐ and mypy is right to say so.
        """
        slept: list[float] = []
        monkeypatch.setattr("alphacouncil.providers.financial.time.sleep", slept.append)
        return slept

    def test_the_first_call_waits_for_nothing(self, _slept: list[float]) -> None:
        """⭐ There is no previous access to be spaced away from, so an unconditional sleep
        would only make the cold path visibly slower."""
        fin._throttle_wait()

        assert _slept == []

    def test_a_back_to_back_call_waits_at_least_the_floor(
        self, _slept: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ The floor on its own: the throttle is a **minimum gap between starts**, and
        the elapsed time is subtracted rather than added."""
        monkeypatch.setattr(fin, "_MIN_INTERVAL_S", 0.35)
        monkeypatch.setattr(fin, "_JITTER_S", 0.0)
        monkeypatch.setattr(fin, "_LAST_CALL", 100.0)
        monkeypatch.setattr(fin, "_monotonic", lambda: 100.0)

        fin._throttle_wait()

        assert _slept == [pytest.approx(0.35)]

    def test_work_done_since_the_last_call_is_credited(
        self, _slept: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ A caller that took longer than the interval must not pay it twice."""
        monkeypatch.setattr(fin, "_MIN_INTERVAL_S", 0.35)
        monkeypatch.setattr(fin, "_JITTER_S", 0.0)
        monkeypatch.setattr(fin, "_LAST_CALL", 100.0)
        monkeypatch.setattr(fin, "_monotonic", lambda: 100.9)

        fin._throttle_wait()

        assert _slept == []

    def test_jitter_sits_on_top_of_the_floor(
        self, _slept: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ The jitter's whole job is that two sessions do not converge on the same
        instant, so it is **added**, never taken out of the floor."""
        monkeypatch.setattr(fin, "_MIN_INTERVAL_S", 0.35)
        monkeypatch.setattr(fin, "_JITTER_S", 0.20)
        monkeypatch.setattr(fin, "_LAST_CALL", 100.0)
        monkeypatch.setattr(fin, "_monotonic", lambda: 100.0)

        fin._throttle_wait()

        assert 0.35 <= _slept[0] <= 0.55

    def test_jitter_actually_varies(
        self, _slept: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ A jitter of zero is not a jitter, and the shape of the call looks the same
        either way -- so this asserts the **spread**, not the existence of a call."""
        monkeypatch.setattr(fin, "_MIN_INTERVAL_S", 0.0)
        monkeypatch.setattr(fin, "_JITTER_S", 0.20)
        monkeypatch.setattr(fin, "_monotonic", lambda: 0.0)

        for _ in range(20):
            monkeypatch.setattr(fin, "_LAST_CALL", 0.0)
            fin._throttle_wait()

        assert len(set(_slept)) > 1


class TestImportingThisModuleOpensNothing:
    def test_the_session_state_is_inert_before_any_call(self) -> None:
        """⭐ Importing must not log in: the state is *false*, not *unknown*, so a module
        that is imported by a CLI, a test and a request handler all start the same way."""
        assert fin._LOGGED_IN is False
        assert fin._LAST_CALL is None
