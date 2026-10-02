"""The sentence one due kill criterion makes (spec 044; moved from the frontend).

## ⭐ Why this module exists at all

The five sentences used to live in ``frontend/src/criterionVerdict.ts`` and **nowhere
else**. That was fine until a notification needed the same sentence in a place with no
browser in it, and the two available moves were both wrong:

* ⭐ rewrite it in Python — two homes, and they drift
* ⭐ send the bare state (``crossed``) — that is not a reminder, it is a debug line

So the sentence lives **here** now, and ``criterionVerdict.ts`` is left with
presentation only. ⭐ The pay-off is not tidiness: **the today page and the notification
can no longer say different things**, and that is structural rather than a convention
somebody has to remember.

⭐ The comments came along with the code. A reason that stays behind in the file it was
written for gets re-invented, and re-invented wrong.

## ⭐ Five sentences, and the last three are the feature

| state | who is speaking |
|---|---|
| ``crossed`` / ``not_crossed`` | the comparison, over the reader's own threshold |
| ``warming`` | ⭐ us — the metric is too young, and here is how many bars are missing |
| ``undetermined`` | ⭐ us — the catalogue has never heard of this metric |
| ``no_bars`` | ⭐ us — the source has nothing for this instrument |

⭐ **Collapsing the last three into 「条件没成立」 would be the most misleading thing this
product could do**, because the reader would take it as news about their own judgement.
The condition did not fail to hold — it was never tested. Red line 6 in constitution §4.6:
「把『无法判断』降级成『看起来合理』的默认值」.

## ⭐ `crossed` is the only state allowed to say 已越过

The old frontend test pinned 「已触发」 as a string that must **never** appear, and the
reason it recorded was 「the system has no metric source and has decided nothing」. ⭐ That
reason is gone (specs 037/038 gave it a real metric source), so the assertion is gone
with it — ⭐ **not because it became inconvenient, but because the fact it rested on
stopped being true.** A test whose reason has expired should be deleted, not preserved as
a superstition.

## 红线 13: `not_crossed` must not read as relief

「没有越过」 is a fact and stops there. It is not 「还好」, it is not a green tick, and it
says nothing about whether the reader's judgement was good. ⭐ Dressing it as comfort is
the same move as a 成绩 badge (红线 9), wearing a different hat.

## 红线 8: nothing here recommends

Every sentence has the **reader as its subject** — 「你写的判据」 is theirs, the threshold
is theirs, and we are reporting the comparison they asked for. ⭐ The banned shapes are the
ones whose subject is the product: 「值得关注」「今日精选」「异动」. ⭐ That is why
:func:`sentence_for` is a total function over states and states nothing else: it has no
vocabulary for 「机会」, so it cannot form one.
"""

from __future__ import annotations

from dataclasses import dataclass

from alphacouncil.domain.criterion_eval import CriterionVerdict

__all__ = ["MetricFacts", "Sentence", "sentence_for"]

#: ⭐ The five states live in :class:`~alphacouncil.domain.criterion_eval.CriterionVerdict`
#: and are **not** redeclared here.
#:
#: ⭐ The first draft of this module declared its own ``Literal[...]`` of the same five
#: strings, on the reasoning that the rendering layer 「must not drag the evaluator in」.
#: ⭐ `mypy` refused the assignment on sight — the two were structurally identical and
#: nominally different — and that was the right answer for a reason the draft had missed:
#: ⭐ the worry was about an *import*, and the actual cost was **a second home for five
#: names**, which is the exact thing this whole move existed to remove. ⭐ The evaluator is
#: pure functions over bars; importing it costs nothing at render time.
CriterionState = CriterionVerdict


@dataclass(frozen=True, slots=True)
class MetricFacts:
    """Everything a sentence may say. ⭐ Nothing else is available to it.

    ⭐ The field list **is** the red line 8 boundary made concrete: there is no field for
    a recommendation, so no sentence can contain one. ⭐ Adding a ``confidence`` here would
    be the first step towards 「值得关注」, and it should be argued for in a spec.
    """

    state: CriterionState
    label: str
    value: float | None = None
    as_of: str | None = None
    period: int | None = None
    bars_available: int | None = None
    #: ⭐ **The latest report period that *had* been announced on `as_of`**, for a criterion
    #: whose current period had not. ⇒ 这是**事实**,不是状态 ——
    #:   无布尔(`S-02 no_boolean_state` 会红)、不预测(实测公告滞后 25/46/93 天)。
    #: 无为 `None` 时句子退化为「还没公告」而不是「没拿到过任何一期」,
    #: 因为后者意味着我们从未开始记过这只股票。
    latest_announced_period_end: str | None = None


@dataclass(frozen=True, slots=True)
class Sentence:
    """One rendered clause, and the two facts the page needs for styling."""

    verdict: str
    #: ``True`` only when the comparison actually ran. Drives the row's accent colour.
    crossed: bool
    #: ⭐ Whether the reader is being told something they could act on today. ``False``
    #: for the three 「we don't know」 states, and the row is styled to say so.
    adjudicable: bool


def format_value(value: float) -> str:
    """A number with the precision a price needs and an indicator does not.

    ⭐ Integers print as integers. ``1235.5800000001`` in a sentence about the reader's own
    money reads as a precision the data does not have, and invites them to distrust the
    rest of the number.

    ⭐ Moved from TypeScript's ``Number.isInteger`` / ``toFixed(2)``, which is why the
    round-trip is asserted rather than assumed: ⭐ ``int`` in Python is unbounded, so
    ``1234.0`` is an ``int`` here and a ``float`` in JSON, ⭐ and a port that disagreed on
    that would print ``1,234`` on one page and ``1234.00`` on another.
    """
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:.2f}"


def _observed(facts: MetricFacts) -> str:
    """``现在 1,235（2026-09-29）`` — the reading, with the date when we have one."""
    value = facts.value if facts.value is not None else 0.0
    base = f"现在 {format_value(value)}"
    return f"{base}（{facts.as_of}）" if facts.as_of else base


def sentence_for(facts: MetricFacts) -> Sentence:
    """The sentence for one criterion. ⭐ Total: every state has an answer.

    ⭐ Total is not a style choice. ``spec 040``'s mutation run found that ``NO_BARS`` was
    **unreachable in production** (the router checked the bars first), so a state nobody
    could reach was never tested — ⭐ and then the only thing it was asserted to do was
    never checked. A rendering function that raises on an unknown state would turn that
    into a visible failure instead of a silently blank row.
    """
    match facts.state:
        case "crossed":
            # ⭐ 「已越过」 not 「已触发」, and the value is right there. The reader wrote the
            # threshold; we are reporting the comparison they asked for, not rendering a
            # verdict on their position.
            return Sentence(
                verdict=f"已越过 —— {facts.label} {_observed(facts)}。",
                crossed=True,
                adjudicable=True,
            )
        case "not_crossed":
            # ⭐ No adjective. 「没有越过」 and stops. Not relief, not a warning, and
            # emphatically not a comment on the decision.
            return Sentence(
                verdict=f"没有越过 —— {facts.label} {_observed(facts)}。",
                crossed=False,
                adjudicable=True,
            )
        case "warming":
            # ⭐ The count is the whole reason this sentence is worth having. 「还在预热」
            # alone is a dead end; 「还差 48 根」 tells the reader this resolves on its
            # own, which is the difference between a deferral and a shrug.
            #
            # ⭐ `bars_available` arrives from the server rather than being derived here.
            # The first draft counted calendar days minus weekends in TypeScript — ⭐
            # which is spec 038's mistake one layer down: a quantity the server knows
            # exactly, recomputed in a second language, wrong by the number of public
            # holidays. A promise of 「还差 N 根」 that is short by three days is a
            # promise the page does not keep.
            missing = (
                None
                if facts.bars_available is None
                else max(0, (facts.period or 0) - facts.bars_available)
            )
            if missing is None or missing == 0:
                return Sentence(
                    verdict=f"观察期已到 —— {facts.label} 还没有值，这条判据没有被求值过。",
                    crossed=False,
                    adjudicable=False,
                )
            # ⭐ Split for the line length, **not** to reword. The two halves concatenate
            # to exactly the sentence the frontend used to own, ⭐ and a reword here would
            # be a silent copy change on the one page the reader reads.
            head = f"观察期已到 —— {facts.label} 还差 {missing} 根日线才有值，"
            return Sentence(
                verdict=f"{head}这条判据暂时没有被求值。",
                crossed=False,
                adjudicable=False,
            )
        case "undetermined":
            # ⭐ The metric name is quoted back **as typed**, because the whole point is
            # that we do not recognise it. Rendering a catalogue label here would imply we
            # do.
            # ⭐ Split for the line length, **not** to reword — see `warming` above.
            head = f"观察期已到 —— 「{facts.label}」不在我们能算的指标里，"
            return Sentence(
                verdict=f"{head}这条判据没有被求值过。",
                crossed=False,
                adjudicable=False,
            )
        case "no_bars":
            return Sentence(
                verdict="观察期已到 —— 这个代码没有日线，这条判据没有被求值过。",
                crossed=False,
                adjudicable=False,
            )
        case "not_announced":
            # ⚠️ ⭐ **这一支不能说时间。**
            #
            # 「还差 N 根日线」是一个**会自己兑现**的承诺,而公告无并存在这种承诺 ——
            # `financial.py:372-377` 实测公告滞后 25 / 46 / 93 天,而 `spec 043:41-45` 已因为
            # 官方文档的「约 2 个月」推翻过一次。
            # ⇒ 这里只说**已经发生的事**:那一期在你的截止日之前没公告,你当时
            # 最新能看到的是哪一期。一个日期都不给。
            #
            # ⚠️ **分行只为了行长,不是为了换词** —— 同上面的 `warming`。
            # ⚠️ ⭐ **两个分支,而不是一个 f-string 直接插值。**
            # `latest_announced_period_end` 是 `None` 时,单行插值会把页面上的这句话写成
            # 「你当时最新能看到的是 None」 —— 一个缺失的事实被渲染成一个字面量。
            # ⚠️ **这正好是本产品存在要防的那一类缺陷**,而我是在写
            # 禁止它的那条规则的同一个改动里写的。`spec 051 §3.4` 已经写好了怎么办,我没实施。
            if facts.latest_announced_period_end is None:
                # 诚实地说我们从未开始记过这只股票 —— 而不是假造一个期。
                return Sentence(
                    verdict=(
                        f"观察期已到——{facts.label} 还没公告，"
                        "而这只股票我们从未记过报告，"
                        "这条判据暂时没有被求值"
                    ),
                    crossed=False,
                    adjudicable=False,
                )
            head = (
                f"观察期已到——{facts.label} 还没公告，"
                f"你当时最新能看到的是 {facts.latest_announced_period_end}，"
            )
            return Sentence(
                verdict=f"{head}这条判据暂时没有被求值",
                crossed=False,
                adjudicable=False,
            )
        case _:
            # ⭐ Unreachable through the `Literal`, and deliberately kept anyway: this
            # function is reachable from JSON, where the state is whatever the server sent.
            # ⭐ Raising here is the point — spec 040's mutation run showed that a state
            # nobody can reach is a state nobody has tested, ⭐ and a rendering function
            # that quietly returned nothing for an unknown state would turn a **server
            # bug** into a blank row on the one page the reader opens to find out what
            # went wrong.
            raise ValueError(f"unknown criterion state: {facts.state!r}")
