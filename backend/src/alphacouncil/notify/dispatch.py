"""What is worth telling the reader, and saying it once (spec 044).

## ⭐ Where the boundary between this and `webhook.py` is, and why it is here

`notify/webhook.py` takes a rendered title and body. ⭐ This module is the only thing that
decides **which** rendered title and body — ⭐ and it holds exactly one decision, so there
is one place where it can be wrong.

`spec 033` §一 drew the same line: 「本 spec 只建通道,不建决策」.

## ⭐ 红线 8 is enforced by omission, not by a word list

Every notification this module can produce is the sentence
:mod:`alphacouncil.domain.criterion_sentence` already renders for the today page, prefixed
with the instrument. ⭐ The banned shapes are the ones whose **subject is the product** —
「值得关注」「今日精选」「异动」 — ⭐ and they cannot be formed here, because the only
text available is a clause about **the reader's own criterion**.

⭐ The structural part is narrower and worth stating exactly: ⭐ **this module cannot
render**, so it has no vocabulary for a recommendation. ⭐ It reads ``verdict`` off the
payload and prefixes it with an instrument code, ⭐ and nothing else.

## ⭐ The three 「we don't know」 states produce nothing at all

`warming` / `undetermined` / `no_bars` are not interceptions. ⭐ They are **our** gap, not
news about the reader's judgement, ⭐ and a notification that says 「we could not check」
every day is the thing red line 11 calls 催促.

Skipping them has a consequence worth stating, because it looks like a bug and is not:
⭐ **if the data source breaks, the reader hears nothing.** ⭐ We chose silence over a
daily repetition of 「取不到日线」 — ⭐ and if that trade is wrong it is wrong for a reason
somebody can argue with, which is the point of writing it down.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import structlog

from alphacouncil.core.time import utc_millis
from alphacouncil.domain.criterion_eval import CriterionVerdict
from alphacouncil.notify.webhook import ChannelConfig, Delivery, send_webhook
from alphacouncil.storage.repositories import notifications as repository

log = structlog.get_logger(__name__)

__all__ = ["CHANNEL", "Kind", "Notice", "SendReport", "send_due_criteria"]

#: ⭐ One channel name for now. ⭐ It is a **column** rather than a table-per-channel
#: because the same fact sent by email and by webhook is two different facts — ⭐ the reader
#: may have configured one and not the other.
CHANNEL = "webhook"

#: The one kind this dispatcher knows. ⭐ Not a general enum: ⭐ adding a member is a
#: decision about what deserves interrupting somebody, ⭐ and that decision should come
#: with its own argument rather than by appending to a list.
Kind = str
_KIND = "kill_criterion_due"


@dataclass(frozen=True, slots=True)
class Notice:
    """One thing worth saying, already rendered."""

    kind: Kind
    subject: str
    body: str
    #: ⭐ The identity used for 「关于这件事我说过没有」. ⭐ Absent for a notice that must be
    #: re-sayable — ⭐ but every kind here has one, ⭐ so this is ``str`` and not optional.
    key: str


@dataclass(frozen=True, slots=True)
class SendReport:
    """What this run did, so a human reading the output knows."""

    considered: int
    sent: int
    skipped_not_actionable: int
    skipped_already_sent: int
    failed: int

    def summary(self) -> str:
        """One line, in the reader's language."""
        return (
            f"考虑了 {self.considered} 条 · 发了 {self.sent} 条 · "
            f"无法判断 {self.skipped_not_actionable} 条 · "
            f"已经说过 {self.skipped_already_sent} 条 · 失败 {self.failed} 条"
        )


def _is_actionable(verdict: CriterionVerdict) -> bool:
    """Whether this verdict is a fact about the reader's criterion rather than about us.

    ⭐ Read off the enum's own :attr:`~CriterionVerdict.answerable` rather than restating
    the two members: ⭐ a second list here is a second definition, ⭐ and it is the same
    mistake the sentence module made in its first draft.
    """
    return verdict.answerable


def notices_for_due_criteria(
    attention: list[dict[str, object]],
) -> list[Notice]:
    """Turn today's attention items into the notices worth sending.

    ⭐ Takes the **API-shaped** attention rows rather than reaching into the database,
    because ⭐ ``/api/v1/today`` already computed the sentences and ⭐ recomputing them here
    would be a second implementation of 「什么状态可以据此行动」.

    ⭐ The three 「我们不知道」 states are dropped here, not in the channel — ⭐ so the
    channel never has to know what a criterion is.
    """
    out: list[Notice] = []
    for item in attention:
        metric = item.get("metric")
        verdict_text = str(item.get("verdict") or "").strip()
        inner = item.get("item")
        criterion = inner.get("criterion") if isinstance(inner, dict) else None
        if not verdict_text or not isinstance(criterion, dict) or not isinstance(inner, dict):
            continue
        if isinstance(metric, dict) and not _is_actionable(
            CriterionVerdict(str(metric.get("state") or ""))
        ):
            continue
        if not bool(item.get("adjudicable")):
            # ⭐ `metric` is absent (we could not read any bars) **and** the flag says the
            # comparison did not run — ⭐ both mean the same thing here, and the flag is
            # the one the server derived.
            continue
        key = repository.fingerprint(
            kind=_KIND,
            decision_id=str(inner.get("decision_id") or ""),
            metric=str(criterion.get("metric") or ""),
            operator=str(criterion.get("operator") or ""),
            threshold=float(criterion.get("threshold") or 0.0),
            as_of=str(criterion.get("as_of") or ""),
        )
        subject = str(inner.get("display") or "")
        out.append(
            Notice(
                kind=_KIND,
                subject=subject,
                body=f"{subject} 你写的失效条件{verdict_text}",
                key=key,
            )
        )
    return out


def send_due_criteria(
    connection: sqlite3.Connection,
    attention: list[dict[str, object]],
    *,
    config: ChannelConfig | None,
    now: str | None = None,
    channel: str = CHANNEL,
) -> SendReport:
    """Say each actionable thing once, and say what happened either way."""
    notices = notices_for_due_criteria(attention)
    stamp = now or utc_millis()

    not_actionable = sum(
        1
        for item in attention
        if not isinstance(item.get("metric"), dict) or not bool(item.get("adjudicable"))
    )
    already = 0
    sent = 0
    failed = 0

    for notice in notices:
        if repository.already_sent(connection, channel=channel, key=notice.key):
            already += 1
            continue
        outcome: Delivery = send_webhook(config, notice.subject, notice.body)
        if outcome.delivered:
            repository.record(
                connection,
                channel=channel,
                key=notice.key,
                kind=notice.kind,
                subject=notice.subject,
                body=notice.body,
                sent_at=stamp,
            )
            sent += 1
        else:
            # ⭐ ⭐ **Not recorded, on purpose.** ⭐ If we wrote the row for a failed
            # delivery, the next run would skip it — ⭐ and the reader would never hear
            # about a thing we were one retry short of telling them. ⭐ That is the
            # difference between this table and a cache, and it is the whole reason the
            # failure branch is a `continue` rather than a `record`.
            failed += 1
            log.warning(
                "notify.notice_failed",
                subject=notice.subject,
                detail=outcome.detail,
            )

    report = SendReport(
        considered=len(attention),
        sent=sent,
        skipped_not_actionable=not_actionable,
        skipped_already_sent=already,
        failed=failed,
    )
    # ⭐ ⭐ **Not `vars(report)`.** ⭐ A `slots=True` dataclass has no `__dict__`, ⭐ so
    # `vars()` raises `TypeError` — ⭐ and it raised **inside** the one line that is
    # supposed to record what happened, ⭐ which means the run's outcome would be lost
    # exactly when something went wrong.
    log.info(
        "notify.due_criteria",
        considered=report.considered,
        sent=report.sent,
        not_actionable=report.skipped_not_actionable,
        already_sent=report.skipped_already_sent,
        failed=report.failed,
    )
    return report
