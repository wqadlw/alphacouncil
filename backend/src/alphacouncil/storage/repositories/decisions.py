"""Appending to, and reading, the decision journal (J1).

Append-only, and this module offers no way to break that: there is no ``update``
and no ``delete``. Changing your mind is another decision, which is the only
correct model for a record whose entire value is that it cannot be revised once
the outcome is known. The database enforces the same thing with triggers, so the
rule survives a caller that reaches past this module with raw SQL — which is why
the triggers exist instead of a comment here.

**The id is the timestamp.** ``decisions.id`` is the primary key *and* the
moment of writing, in the one spelling the schema accepts
(:func:`alphacouncil.core.time.utc_millis`). It is generated here, never taken
from the caller, because "this was written before the price moved" is a claim
about a moment and a caller who supplies the moment is a caller who can move it.

Ordering is by ``id`` ascending for the same reason it is in the watchlist: the
id *is* the write order, so two decisions in the same millisecond still have a
defined sequence, and the sequence is the record.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.decision import Decision, DecisionAction, KillCriterion
from alphacouncil.models.market import Market, Symbol
from alphacouncil.storage.repositories import instruments

__all__ = [
    "DecisionRow",
    "ScratchVerb",
    "append",
    "for_symbol",
    "get_by_id",
    "list_all",
    "mark_scratch",
    "recent",
    "scratch_ids",
]

#: The column list is written out in each statement rather than built from a
#: shared constant. Two reasons, and the second is the real one: a constructed
#: query reads to a linter — and to a reviewer — exactly like an injectable one,
#: and "the values are still parameterised" is a claim the reader then has to
#: verify by hand. Spelling it out costs three lines and needs no verification.
_INSERT = (
    "INSERT INTO decisions "
    "(id, market, code, action, rationale, counter_evidence, kill_criteria, thesis_id) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_SELECT_FOR_SYMBOL = (
    "SELECT id, market, code, action, rationale, counter_evidence, kill_criteria, thesis_id "
    "FROM decisions WHERE market = ? AND code = ? ORDER BY id ASC"
)
_SELECT_RECENT = (
    "SELECT id, market, code, action, rationale, counter_evidence, kill_criteria, thesis_id "
    "FROM decisions ORDER BY id DESC LIMIT ?"
)
_SELECT_ALL = (
    "SELECT id, market, code, action, rationale, counter_evidence, kill_criteria, thesis_id "
    "FROM decisions ORDER BY id ASC"
)


@dataclass(frozen=True, slots=True)
class DecisionRow:
    """One row of ``decisions``, with the enums and the predicates already decoded."""

    id: str
    market: Market
    code: str
    action: DecisionAction
    rationale: str
    counter_evidence: str
    kill_criteria: tuple[KillCriterion, ...]
    thesis_id: str | None


def append(
    connection: sqlite3.Connection,
    decision: Decision,
    *,
    now: str | None = None,
) -> DecisionRow:
    """Record one decision, creating the instrument first if necessary.

    The instrument is ensured here rather than by the caller so that "the
    instrument exists, then the decision refers to it" is one operation —
    ``decisions`` carries a foreign key, and splitting this would leave a
    constraint failure one forgotten call away.

    Must run inside a transaction: this performs two statements.

    Args:
        connection: An open application connection.
        decision: A validated decision, built by
            :func:`alphacouncil.domain.decision.record`.
        now: Timestamp override, for tests. **Not reachable from the API** — the
            route does not expose it, because a caller-supplied moment is
            precisely what the id is supposed to prove.

    Returns:
        The row as written.

    Raises:
        AssetTypeConflictError: The instrument is on file with another type.
        sqlite3.IntegrityError: A schema constraint refused the row. Every one
            of them is also checked in the domain, so reaching this means the two
            have drifted — which is a bug, not a user error.
    """
    instruments.ensure(connection, decision.symbol, now=now)
    stamp = now if now is not None else utc_millis()
    connection.execute(
        _INSERT,
        (
            stamp,
            decision.symbol.market.value,
            decision.symbol.code,
            decision.action.value,
            decision.rationale,
            decision.counter_evidence,
            decision.kill_criteria_json(),
            decision.thesis_id,
        ),
    )
    return DecisionRow(
        id=stamp,
        market=decision.symbol.market,
        code=decision.symbol.code,
        action=decision.action,
        rationale=decision.rationale,
        counter_evidence=decision.counter_evidence,
        kill_criteria=decision.kill_criteria,
        thesis_id=decision.thesis_id,
    )


def get_by_id(connection: sqlite3.Connection, decision_id: str) -> DecisionRow | None:
    """One decision by its id, or ``None``.

    A ``decisions`` primary key is the moment the decision was written, so this
    lookup is exact rather than fuzzy — which is what makes it safe for the
    retrospective page, where the text and the review of that text must be the
    same row and not two rows that happen to be adjacent.
    """
    row = connection.execute(
        "SELECT id, market, code, action, rationale, counter_evidence, kill_criteria, thesis_id "
        "FROM decisions WHERE id = ?",
        (decision_id,),
    ).fetchone()
    return None if row is None else _to_row(row)


def for_symbol(connection: sqlite3.Connection, symbol: Symbol) -> tuple[DecisionRow, ...]:
    """Every decision recorded about ``symbol``, oldest first.

    An instrument nobody has decided about returns an empty tuple rather than
    raising. Whether that is worth saying anything about is the caller's
    question — "no decisions yet" is a fact, not a failure.
    """
    return tuple(
        _to_row(row)
        for row in connection.execute(_SELECT_FOR_SYMBOL, (symbol.market.value, symbol.code))
    )


def recent(connection: sqlite3.Connection, *, limit: int = 50) -> tuple[DecisionRow, ...]:
    """The most recent decisions across every instrument, newest first.

    Newest first here, unlike :func:`for_symbol`. The two are read for different
    reasons: this one answers "what have I been doing lately", where the latest
    is the point, while a single instrument's log is read as a story and only
    works in order.
    """
    return tuple(_to_row(row) for row in connection.execute(_SELECT_RECENT, (limit,)))


def list_all(connection: sqlite3.Connection) -> tuple[DecisionRow, ...]:
    """Every decision ever recorded, oldest first — deliberately untruncated.

    Exists because a rule that scans for "is there anything I should look at
    today" cannot afford a window: a predicate written on a decision three
    years ago is exactly the one that comes due today, and a ``LIMIT`` —
    however generous — silently drops precisely those. Personal-scale data
    (thousands of rows, not millions) is what makes the untruncated read the
    honest choice rather than the naive one.
    """
    return tuple(_to_row(row) for row in connection.execute(_SELECT_ALL))


# ---------------------------------------------------------------------------
# 「这条是试验记录」—— spec 060 §一之补
# ---------------------------------------------------------------------------
#
# ⭐⭐ **本段只有一处读法推导状态,⭐⭐ 那就是 :func:`scratch_ids`。** ⭐⭐
#
# ⭐⭐ **为什么只能有一处:** ⭐⭐ 读法一旦在两个地方重复,⭐⭐ 总会有一处重复错
# ⭐⭐ —— ⭐⭐ 而这**已经发生过**:⭐⭐ `D-25` 的第一版把复合键
# ⭐⭐ `(market, code)` 当成两个独立引用,⭐⭐ 因为「取最后一行」
# ⭐⭐ 在那里也是现写的。⭐⭐ 同一个形状:⭐⭐ **读法一重复,
# ⭐⭐ 就会走样一次。** ⭐⭐


class ScratchVerb(StrEnum):
    """The two things a reader can say about a decision, and nothing else.

    ⭐ **An enum, not a free string, and not a boolean.** ⭐ S-02's threshold is two:
    ⭐ one boolean is a genuine binary, ⭐ two booleans about the same object is a state
    ⭐ machine wearing a disguise. ⭐⭐ ``marked`` / ``unmarked`` **is** that state
    ⭐⭐ machine — ⭐⭐ and both members of it are the *absence* of a column, ⭐⭐ so a
    ⭐⭐ boolean on the decision row would have been exactly the shape S-02 forbids.

    ⭐⭐ **And not a third member.** ⭐⭐ A general tagger would invite 「好判断 /
    ⭐⭐ 坏判断 / 被打脸」 ⭐⭐ — ⭐⭐ **that is self-scoring**, ⭐⭐ and red line
    ⭐⭐ 11 and this product's own argument both refuse it. ⭐⭐ ⇒ **one
    ⭐⭐ purpose-limited mark, ⭐⭐ not a category system.**
    """

    MARKED = "marked"
    UNMARKED = "unmarked"

    @property
    def is_scratch(self) -> bool:
        """Whether the latest verb puts this decision outside the retrospective.

        ⭐⭐ The whole product surface of this table is this one predicate. ⭐⭐
        ⭐⭐ **It lives on the verb, ⭐⭐ not on the row, ⭐⭐ — ⭐⭐
        ⭐⭐ because 「最后一行是不是 marked」 ⭐⭐ is a question
        ⭐⭐ about the log, ⭐⭐ and answering it in two places
        ⭐⭐ is how the two places come to disagree.
        """
        return self is ScratchVerb.MARKED


_INSERT_SCRATCH = (
    "INSERT INTO decision_scratch_events (decision_id, verb, recorded_at) VALUES (?, ?, ?)"
)
#: ⭐⭐ 「最后一行」 = **最大 id**,⭐⭐ 而不是最大 `recorded_at`。⭐⭐
#: ⭐⭐ `AUTOINCREMENT` 保证 id 单调,⭐⭐ 而 `recorded_at` 是调用方给的
#: ⭐⭐ —— ⭐⭐ 同一毫秒里两次写入会给出相同的
#: ⭐⭐ `recorded_at`,⭐⭐ **按时间排会分不出「谁在后」。** ⭐⭐
#: ⭐⭐ **`decisions.id` 与 `card_reviews.id` 同毫秒碰撞的同一个形状**
#: ⭐⭐(`F-233` 家族)。⭐⭐
_SCRATCH_STATES = """
SELECT decision_id, verb
FROM decision_scratch_events AS newer
WHERE newer.id = (
  SELECT MAX(id) FROM decision_scratch_events AS older
  WHERE older.decision_id = newer.decision_id
)
"""


def mark_scratch(
    connection: sqlite3.Connection, decision_id: str, *, marked: bool
) -> ScratchVerb:
    """Record one 「this is / is not a scratch decision」 and return the verb written.

    ⭐⭐ **Appends a row. ⭐⭐ Never edits and never deletes** ⭐⭐ — ⭐⭐
    ⭐⭐ the table has ``BEFORE UPDATE`` / ``BEFORE DELETE`` triggers ⭐⭐
    ⭐⭐ and the repository is not the thing that enforces them ⭐⭐.
    ⭐⭐

    ⭐⭐ **And 「取消」 is a second row, ⭐⭐ not the removal of the first.**
    ⭐⭐ Overwriting the verb would make the state unreadable ⭐⭐
    ⭐⭐ and deleting the row would remove the record that he
    ⭐⭐ once pressed it. ⭐⭐

    ⭐⭐ **This is the reader's own act (红线 15).** ⭐⭐
    ⭐⭐ The route checks the decision exists ⭐⭐
    ⭐⭐ and nothing else decides *whether* ⭐⭐ — ⭐⭐
    ⭐⭐ **nothing here decides *which* decisions deserve it.**
    ⭐⭐
    """
    verb = ScratchVerb.MARKED if marked else ScratchVerb.UNMARKED
    connection.execute(
        _INSERT_SCRATCH, (decision_id, verb.value, utc_millis())
    )
    return verb


def scratch_ids(connection: sqlite3.Connection) -> frozenset[str]:
    """The ids of every decision currently marked as a scratch record.

    ⭐⭐ **One read, one place. ⭐⭐ Every caller filters through this
    ⭐⭐ function ⭐⭐ so that 「which decisions
    ⭐⭐ are scratch」 ⭐⭐ has exactly one answer
    ⭐⭐ in the codebase. ⭐⭐

    ⭐⭐ **Returns a set rather than a
    ⭐⭐ dict of verdicts.** ⭐⭐ Every caller
    ⭐⭐ needs a membership test, ⭐⭐ and a dict
    ⭐⭐ would hand each of them a reason to read the verb ⭐⭐
    ⭐⭐ and write their own comparison. ⭐⭐
    """
    return frozenset(
        str(row["decision_id"])
        for row in connection.execute(_SCRATCH_STATES)
        if ScratchVerb(row["verb"]).is_scratch
    )


def _to_row(row: sqlite3.Row) -> DecisionRow:
    """Decode a row. Unknown enums and malformed predicates are corruption, not defaults."""
    return DecisionRow(
        id=row["id"],
        market=Market(row["market"]),
        code=row["code"],
        action=DecisionAction(row["action"]),
        rationale=row["rationale"],
        counter_evidence=row["counter_evidence"],
        kill_criteria=tuple(
            KillCriterion.from_json(item) for item in json.loads(row["kill_criteria"])
        ),
        thesis_id=row["thesis_id"],
    )
