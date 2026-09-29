"""PIT financial storage (migration 0011, spec 043 · D4).

## The one sentence this file exists to defend

⭐ **A company restating a quarter is a *later announcement of the same period*, not an
edit of the old row.** Everything below is that sentence, checked from both ends: the
schema lets the two versions coexist, and it refuses every operation that would collapse
them into one.

## Why 「it would still parse」 is not enough here

A table whose primary key were ``(market, code, period_end)`` would accept a restatement by
overwriting. Nothing would raise. A query would return a plausible number. ⭐ And the
plausible number would be **wrong for everyone who looked before the restatement** — which
is precisely the reader the PIT table was built for: 「我当时看到的是多少」.

So the tests here are about *refusal* (UPDATE, DELETE, an announcement before its period)
as much as about storage. A test that only proved 「a row can be inserted」 would pass
against a schema that had quietly thrown the whole point away.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from alphacouncil.storage import migrate

pytestmark = pytest.mark.unit

_INSERT = """
INSERT INTO financial_reports (
    market, code, period_end, announced_at, source, fetched_at,
    roe_avg, np_margin, gp_margin, net_profit, eps_ttm, revenue,
    total_shares, float_shares
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_FIELDS = (
    "market",
    "code",
    "period_end",
    "announced_at",
    "source",
    "fetched_at",
    "roe_avg",
    "np_margin",
    "gp_margin",
    "net_profit",
    "eps_ttm",
    "revenue",
    "total_shares",
    "float_shares",
)


def _row(
    market: str = "sh",
    code: str = "600519",
    period_end: str = "2024-12-31",
    announced_at: str = "2025-04-03",
    source: str = "baostock",
    fetched_at: str = "2026-09-29T00:00:00.000Z",
    metrics: dict[str, float | None] | None = None,
) -> tuple[object, ...]:
    """One insert, in column order.

    ⭐ The identity fields are named parameters and the metrics go in a **dict**, not in
    ``**metrics``. That split is what keeps the type honest: ``**metrics`` would have to be
    typed ``float | None`` to satisfy every metric column *and* ``str`` to satisfy
    ``market``/``code``, so one of the two groups would be a lie -- ⭐ and mypy caught it
    when the malformed-field tests started passing strings through it.
    """
    cells: dict[str, float | None] = {
        "roe_avg": 0.24,
        "np_margin": 0.21,
        "gp_margin": 0.91,
        "net_profit": 86.2,
        "eps_ttm": 69.4,
        "revenue": 170.9,
        "total_shares": 12.56,
        "float_shares": 12.56,
    }
    cells.update(metrics or {})
    identity: dict[str, str] = {
        "market": market,
        "code": code,
        "period_end": period_end,
        "announced_at": announced_at,
        "source": source,
        "fetched_at": fetched_at,
    }
    return tuple(identity.get(name, cells.get(name)) for name in _FIELDS)


#: The eight metrics a ``query_profit_data`` row carries. ⭐ Named once so
#: :func:`TestMissingIsNotZero.test_every_metric_column_accepts_a_missing_value` can
#: iterate **all** of them: the first draft sampled three and a fourth-column default
#: slipped past, which is the whole reason this list exists.
METRIC_COLUMNS = (
    "roe_avg",
    "np_margin",
    "gp_margin",
    "net_profit",
    "eps_ttm",
    "revenue",
    "total_shares",
    "float_shares",
)


def _row_with(column: str, value: str | None) -> tuple[object, ...]:
    """A row with **one** field replaced by a deliberately wrong value.

    ⭐ Puts the bad value straight into the tuple instead of through :func:`_row`: the point
    of these cases is to feed the table something the *provider* would never produce, and
    routing it through a helper that type-checks its arguments would be the wrong layer to
    be strict in.
    """
    row = list(_row())
    row[_FIELDS.index(column)] = value
    return tuple(row)


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """The whole shipped chain, in memory — a fresh install's schema."""
    script = "\n".join(item.up.read_text(encoding="utf-8") for item in migrate.load_migrations())
    connection = sqlite3.connect(":memory:")
    for statement in migrate.split_statements(script):
        connection.execute(statement)
    try:
        yield connection
    finally:
        # ⭐ Closed explicitly: pytest's unraisable-exception collector turns an unclosed
        # :class:`sqlite3.Connection` into a `ResourceWarning`, and a warning raised during
        # a *later* test's teardown is attributed to the wrong test — which is how a real
        # failure gets reported three tests below the one that caused it.
        connection.close()


def _latest(
    connection: sqlite3.Connection, *, market: str, code: str, as_of: str
) -> tuple[object, ...] | None:
    """⭐ **The PIT read**: the newest announcement at or before ``as_of``, or ``None``.

    ⭐ ``LIMIT 1`` is not an optimisation here, it is the **definition**. The first version
    of this helper returned every qualifying row and the 「reader before the restatement」
    test still passed -- because only one row qualified. ⭐ That is a test that would pass
    against a query with no ``ORDER BY`` at all, so the ordering would have been untested
    until a second row happened to exist. Hence one row, and
    :func:`TestARestatementIsANewRow.test_the_full_history_is_still_reachable` for the
    other question.
    """
    row = connection.execute(
        "SELECT announced_at, roe_avg FROM financial_reports "
        "WHERE market = ? AND code = ? AND announced_at <= ? "
        "ORDER BY announced_at DESC, fetched_at DESC LIMIT 1",
        (market, code, as_of),
    ).fetchone()
    return None if row is None else (row[0], row[1])


def _history(
    connection: sqlite3.Connection, *, market: str, code: str
) -> list[str]:
    """Every announcement we hold, oldest first. A **different question** from :func:`_latest`."""
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT announced_at FROM financial_reports "
            "WHERE market = ? AND code = ? ORDER BY announced_at",
            (market, code),
        )
    ]


# --------------------------------------------------------------------------
# The restatement
# --------------------------------------------------------------------------


class TestARestatementIsANewRow:
    def test_two_announcements_of_one_period_both_survive(self, db: sqlite3.Connection) -> None:
        """⭐ **The feature.** Same `period_end`, later `announced_at`, both present."""
        db.execute(_INSERT, _row(announced_at="2025-04-03", metrics={"roe_avg": 0.24}))
        db.execute(_INSERT, _row(announced_at="2025-08-30", metrics={"roe_avg": 0.19}))

        stored = db.execute(
            "SELECT announced_at, roe_avg FROM financial_reports ORDER BY announced_at"
        ).fetchall()

        assert stored == [("2025-04-03", 0.24), ("2025-08-30", 0.19)]

    def test_a_reader_before_the_restatement_sees_the_original(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ ⭐ **This is the sentence the whole table exists for.**

        ⭐ A read with ``as_of`` in June 2025 must return the **April** figure, even
        though a row with a *different* value for the same period now exists. Returning
        the August number would be look-ahead: the reader would be told what the company
        said four months after they asked.
        """
        db.execute(_INSERT, _row(announced_at="2025-04-03", metrics={"roe_avg": 0.24}))
        db.execute(_INSERT, _row(announced_at="2025-08-30", metrics={"roe_avg": 0.19}))

        before = _latest(db, market="sh", code="600519", as_of="2025-06-01")

        assert before == ("2025-04-03", pytest.approx(0.24))

    def test_a_reader_after_the_restatement_sees_the_restatement(
        self, db: sqlite3.Connection
    ) -> None:
        db.execute(_INSERT, _row(announced_at="2025-04-03", metrics={"roe_avg": 0.24}))
        db.execute(_INSERT, _row(announced_at="2025-08-30", metrics={"roe_avg": 0.19}))

        after = _latest(db, market="sh", code="600519", as_of="2025-09-01")

        assert after == ("2025-08-30", pytest.approx(0.19))

    def test_the_full_history_is_still_reachable(self, db: sqlite3.Connection) -> None:
        """⭐ 「它当时报过什么，以及后来改成了什么」 is a **different question** from 「它现在
        报的是什么」, and it needs a different query.

        ⭐ Both answers have to be obtainable: ``append-only`` would be a liability if the
        only readable state were the current one.
        """
        db.execute(_INSERT, _row(announced_at="2025-04-03"))
        db.execute(_INSERT, _row(announced_at="2025-08-30"))

        assert _history(db, market="sh", code="600519") == ["2025-04-03", "2025-08-30"]

    def test_a_reader_before_any_announcement_sees_nothing(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ ``None`` means 「we do not know yet」, and that is a real answer — not an
        error, and not a row of zeros (red line 6)."""
        db.execute(_INSERT, _row(announced_at="2025-04-03"))

        assert _latest(db, market="sh", code="600519", as_of="2025-01-01") is None

    def test_the_announced_at_today_is_inclusive(self, db: sqlite3.Connection) -> None:
        """⭐ **`<=` and not `<`.** On the announcement date itself the report *was* public,
        so a criterion written that evening must be able to see it.

        ⭐ The exclusive reading is the one that looks careful and is wrong here: it would
        hide a report from anyone who wrote their criterion on the day they read it, which
        is the most common way anyone writes one.
        """
        db.execute(_INSERT, _row(announced_at="2025-04-03"))

        assert _latest(db, market="sh", code="600519", as_of="2025-04-03") is not None

    def test_re_fetching_the_same_announcement_is_not_a_conflict(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ Same period, same announcement, **newer fetch** — a second look, not a new
        version. Replacing on that key would mean the newer fetch wins, which is the same
        silent-overwrite problem one level down."""
        db.execute(_INSERT, _row(announced_at="2025-04-03", fetched_at="2026-09-28T00:00:00.000Z"))
        db.execute(_INSERT, _row(announced_at="2025-04-03", fetched_at="2026-09-29T00:00:00.000Z"))

        assert db.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 2

    def test_two_sources_agreeing_on_one_announcement_both_land(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ ``source`` is part of the key, so 「which one do we believe」 is a consumer's
        decision — not something the table decides by silently keeping the first write."""
        db.execute(_INSERT, _row(source="baostock"))
        db.execute(_INSERT, _row(source="other"))

        assert db.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 2


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


class TestTheTableRefusesToLie:
    def test_updating_a_row_is_refused(self, db: sqlite3.Connection) -> None:
        """⭐ The append-only trigger, and the reason it is not optional.

        ⭐ An ``UPDATE`` would not raise anywhere else in the system: the row count is
        unchanged, every constraint still holds, and a query returns a confident number.
        ⭐ It rewrites history **without leaving a mark**, which is the only kind of
        rewriting that matters here.
        """
        db.execute(_INSERT, _row())

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE financial_reports SET roe_avg = 0.99")

    def test_the_refused_update_changed_nothing(self, db: sqlite3.Connection) -> None:
        """⭐ A trigger that raises but still writes is not a guard."""
        db.execute(_INSERT, _row(metrics={"roe_avg": 0.24}))

        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE financial_reports SET roe_avg = 0.99")

        (value,) = db.execute("SELECT roe_avg FROM financial_reports").fetchone()
        assert value == pytest.approx(0.24)

    def test_deleting_a_row_is_refused(self, db: sqlite3.Connection) -> None:
        """⭐ 「The basis a judgement was made on disappears with it.」"""
        db.execute(_INSERT, _row())

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM financial_reports")

    def test_an_announcement_before_its_period_is_refused(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ A claim that a report was public before the period it describes ended.

        ⭐ A row like this is not merely nonsense — it is **readable by a PIT query before
        the report was public**, because the query compares ``announced_at``, and this
        row lies about exactly that column.
        """
        with pytest.raises(sqlite3.IntegrityError, match="announced_after_period"):
            db.execute(_INSERT, _row(period_end="2024-12-31", announced_at="2024-01-01"))

    def test_an_announcement_on_the_period_boundary_is_allowed(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ ``>=`` is what the CHECK says, so equality is legal — the rule is about
        ordering, and a same-day announcement is the fastest legal case, not a violation."""
        db.execute(_INSERT, _row(period_end="2024-12-31", announced_at="2024-12-31"))

        assert db.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 1

    def test_a_row_fetched_before_it_was_announced_is_refused(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ ⭐ **Not** because source lag is a problem — measured at ~2 months — but
        because *we* cannot have read it yet.

        ⭐ The lag is the source's business and is fine. Fetching a thing before it
        existed is not, and it is the shape a backfilled or mis-stamped row takes.
        """
        with pytest.raises(sqlite3.IntegrityError, match="fetched_after_announced"):
            db.execute(
                _INSERT,
                _row(announced_at="2025-04-03", fetched_at="2025-04-01T00:00:00.000Z"),
            )

    def test_fetching_the_same_day_is_allowed(self, db: sqlite3.Connection) -> None:
        """⭐ The CHECK compares **dates**, not timestamps, so an evening fetch of a
        morning announcement is legal. A timestamp comparison would reject it."""
        db.execute(
            _INSERT, _row(announced_at="2025-04-03", fetched_at="2025-04-03T23:59:00.000Z")
        )

        assert db.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 1

    @pytest.mark.parametrize(
        ("column", "value", "constraint"),
        [
            ("market", "hk", "symbol_check"),
            ("market", "", "symbol_check"),
            ("code", "   ", "code_check"),
            ("period_end", "2024-13-45", "period_end_check"),
            ("period_end", "Q4 2024", "period_end_check"),
            ("announced_at", "2025/04/03", "announced_at_check"),
            ("fetched_at", "2025-04-03", "fetched_at_check"),
        ],
    )
    def test_a_malformed_field_is_refused(
        self, db: sqlite3.Connection, column: str, value: str, constraint: str
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError, match=constraint):
            db.execute(_INSERT, _row_with(column, value))

    def test_omitting_the_venue_is_refused(self, db: sqlite3.Connection) -> None:
        """⭐ ⭐ The mutation check found that **nothing** tested what happens when the
        venue is left out.

        ⭐ Giving ``market`` a ``DEFAULT 'sh'`` is a plausible-looking edit — it keeps the
        column and its CHECK — and it survives every other test here, because every one of
        them *supplies* a venue. ⭐ And the result is the worst kind of wrong: a row whose
        venue was never stated becomes **Shanghai** because Shanghai was the default, so
        a Shenzhen instrument is filed under Shanghai and `000001` collides with the index.

        ⭐ 红线 16 is 「市场标识必须来自**显式输入或数据源返回**」. A default is neither.

        ⭐ The statement is assembled from :data:`_FIELDS`, a module constant, not from
        test input — hence the ``noqa`` rather than an ``allowlist``: the string is a
        constant, and the two other places in this file that build SQL from a name say so
        in the same words.
        """
        columns = _FIELDS[1:]
        row = list(_row())
        del row[_FIELDS.index("market")]
        statement = (
            f"INSERT INTO financial_reports ({', '.join(columns)}) "  # noqa: S608
            f"VALUES ({', '.join('?' * len(columns))})"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(statement, row)

    def test_a_venue_outside_the_three_we_trade_is_refused(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ An open ``market`` column would accept a Hong Kong or a US ticker, and every
        later query would treat it as a Shanghai one."""
        with pytest.raises(sqlite3.IntegrityError, match="symbol_check"):
            db.execute(_INSERT, _row(market="us"))


# --------------------------------------------------------------------------
# 红线 15: the venue is part of the identity
# --------------------------------------------------------------------------


class TestTheVenueIsPartOfTheIdentity:
    def test_the_same_code_on_two_venues_coexists(self, db: sqlite3.Connection) -> None:
        """⭐ 红线 15, and the reason it is a constraint rather than a convention.

        ⭐ ``000001`` is the Shanghai Composite on ``sh`` and Ping An Bank on ``sz``. A key
        of ``code`` alone would make the second insert collide with the first — so the
        table would silently hold one of them, and which one depends on fetch order.
        """
        db.execute(_INSERT, _row(market="sh", code="000001"))
        db.execute(_INSERT, _row(market="sz", code="000001"))

        stored = db.execute("SELECT market FROM financial_reports ORDER BY market").fetchall()

        assert stored == [("sh",), ("sz",)]

    def test_a_pit_query_never_crosses_venues(self, db: sqlite3.Connection) -> None:
        """⭐ The query carries the venue, so a Shanghai reader is never handed the
        Shenzhen row for the same digits."""
        db.execute(_INSERT, _row(market="sh", code="000001", metrics={"roe_avg": 0.10}))
        db.execute(_INSERT, _row(market="sz", code="000001", metrics={"roe_avg": 0.90}))

        answer = _latest(db, market="sh", code="000001", as_of="2030-01-01")

        assert answer == ("2025-04-03", pytest.approx(0.10))


# --------------------------------------------------------------------------
# Missing is not zero
# --------------------------------------------------------------------------


class TestMissingIsNotZero:
    @pytest.mark.parametrize("column", METRIC_COLUMNS)
    def test_every_metric_column_accepts_a_missing_value(
        self, db: sqlite3.Connection, column: str
    ) -> None:
        """⭐ ⭐ **All eight, not the three the first draft checked.**

        ⭐ The mutation check made ``roe_avg`` into ``NOT NULL DEFAULT 0.0`` and nothing
        failed — because every missing-metric test happened to blank a *different* column
        than the one that was mutated. ⭐ Three columns sampled out of eight is not a
        property of the schema, it is a coincidence about the schema.

        ⭐ The point is not that ``NULL`` is legal (it obviously is) but that **no** metric
        column can quietly acquire a default: a default of ``0.0`` would be 红线 6's exact
        failure, and it would apply to whichever column nobody happened to think about.
        """
        row = list(_row_with(column, None))
        # ⭐ `None` for a REAL column under STRICT is a NULL, not a coerced value.
        db.execute(_INSERT, tuple(row))

        stored = db.execute(
            f"SELECT {column} FROM financial_reports"  # noqa: S608 -- constant, from a parametrize list
        ).fetchone()

        assert stored[0] is None

    def test_a_new_listing_may_have_no_ttm_eps(self, db: sqlite3.Connection) -> None:
        """⭐ 红线 6 at the storage layer: an absent metric is ``NULL``, and ``0.0`` would
        say 「its earnings per share is zero」 — which is a fact, and a false one.

        ⭐ The ``None`` here is the provider's ``_number()`` output, not an empty string: the
        wire sends ``""`` and ``"--"``, and converting those is
        :meth:`providers.financial.BaostockFinancial` 's job, not the table's. The first
        draft of this test passed ``""`` straight through, which a ``STRICT`` table rightly
        refused — ⭐ the refusal was correct and the test was the thing that was wrong.
        """
        db.execute(
            _INSERT,
            _row(metrics={"gp_margin": None, "eps_ttm": None, "revenue": None, "roe_avg": 0.24}),
        )
        stored = db.execute(
            "SELECT gp_margin, eps_ttm, revenue, roe_avg FROM financial_reports"
        ).fetchone()

        assert stored == (None, None, None, pytest.approx(0.24))

    def test_a_loss_making_company_keeps_its_negative_margin(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ Negative values are data. ⭐ A ``NOT NULL``/``> 0`` house rule would have
        deleted every loss-making company from the table, and those are exactly the ones a
        judgement most needs evidence about."""
        db.execute(_INSERT, _row(metrics={"np_margin": -0.31}))

        (value,) = db.execute("SELECT np_margin FROM financial_reports").fetchone()
        assert value == pytest.approx(-0.31)

    def test_float_shares_may_not_exceed_total_shares(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ Physically impossible, and the kind of impossibility a CHECK is for."""
        with pytest.raises(sqlite3.IntegrityError, match="shares_positive"):
            db.execute(_INSERT, _row(metrics={"total_shares": 12.0, "float_shares": 20.0}))

    def test_one_shares_column_missing_is_not_a_violation(
        self, db: sqlite3.Connection
    ) -> None:
        """⭐ The comparison is guarded on both sides being present, so a half-known share
        count is stored rather than rejected."""
        db.execute(_INSERT, _row(metrics={"total_shares": 12.0, "float_shares": None}))

        assert db.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 1


# --------------------------------------------------------------------------
# The index serves the query it exists for
# --------------------------------------------------------------------------


class TestTheIndexMatchesTheQuery:
    @pytest.fixture
    def indexes(self, db: sqlite3.Connection) -> dict[str, str]:
        return {
            name: sql
            for name, sql in db.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
            )
            if name.startswith("idx_financial_reports")
        }

    def test_the_pit_index_exists_in_the_ordering_the_query_wants(
        self, indexes: dict[str, str]
    ) -> None:
        """⭐ ``(market, code, announced_at DESC, fetched_at DESC)``.

        ⭐ The two leading columns are the equality filters, so they must come **first** --
        an index led by ``announced_at`` would make every single-instrument query scan the
        whole table. ⭐ And the trailing ``fetched_at`` exists because ``announced_at``
        alone is not a total order: two sources can publish the same report on the same
        day, and 「取最新」 needs a deterministic answer.
        """
        pit = indexes["idx_financial_reports_pit"].replace("\n", " ")

        assert "market, code, announced_at DESC, fetched_at DESC" in pit

    def test_the_period_index_answers_a_different_question(
        self, indexes: dict[str, str]
    ) -> None:
        """⭐ 「这个票最近一期是哪一期」 is not the PIT query, and it wants its own index:
        it filters on the venue and orders by **period**, not by announcement."""
        period = indexes["idx_financial_reports_period"].replace("\n", " ")

        assert "market, code, period_end DESC" in period

    def test_the_down_migration_is_declared_destructive(self) -> None:
        """⭐ ⭐ This table is the one whose ``down`` is worth hesitating over.

        ⭐ Its contents are *refetchable* — unlike a note, nobody typed them — but
        refetching does not promise the **same values**: if the source has since corrected
        its history, a refetch yields a different set of rows and every PIT answer moves.
        ⭐ So the down loses 「我们当时看到的是什么」, which is evidence, not cache.
        """
        entry = next(
            item for item in migrate.load_migrations() if item.version == 11
        )

        assert entry.destructive_down is True


def test_the_primary_key_carries_the_announcement_date(db: sqlite3.Connection) -> None:
    """⭐ The schema states it, read from the created table rather than from the file.

    ⭐ If ``announced_at`` ever dropped out of the key, a restatement would become an
    overwrite and **most of the tests above would still pass** -- they insert, they query,
    they check refusals; only ``test_two_announcements_of_one_period_both_survive`` would
    fail, and it would fail with an opaque ``UNIQUE constraint`` error rather than with
    anything that names the cause.
    """
    (ddl,) = db.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'financial_reports'"
    ).fetchone()

    key = ddl.replace("\n", " ").split("PRIMARY KEY")[-1]

    assert "market, code, period_end, announced_at, source, fetched_at" in key


def test_the_migration_files_are_both_listed() -> None:
    """⭐ A ``.sql`` on disk that the manifest does not name is a migration that will never
    run, and it is the quietest kind of unfinished."""
    entries = {item.up.name for item in migrate.load_migrations()}

    assert "0011_financial_reports.up.sql" in entries
    assert Path("src/alphacouncil/storage/migrations/0011_financial_reports.down.sql").exists()
