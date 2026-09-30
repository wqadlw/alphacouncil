"""The sentence one due kill criterion makes (spec 044).

## ⭐ Why these tests moved from TypeScript

``criterionVerdict.test.ts`` used to own this. The sentence moved to the server because a
notification needs it in a place with no browser in it, ⭐ and the tests moved with it —
a test that stayed behind would have been testing a function the product no longer uses.

⭐ **The wording assertions are the load-bearing ones and they are unchanged.** If the
copy moved and drifted at the same time, the frontend tests would have gone green against
the old wording and nobody would have looked.

## ⭐ What is asserted here that was not asserted there

1. ⭐ **The state names are one home.** :mod:`criterion_sentence` imports
   :class:`CriterionVerdict` rather than redeclaring a ``Literal`` of the same five
   strings — ⭐ ``mypy`` caught that draft, and it was right: the cost of avoiding an
   import was **a second home for five names**.
2. ⭐ **Total over the states**, including one no fixture can produce.
3. ⭐ **红线 8, as an executable claim**: the module has no vocabulary for a
   recommendation, because it has no field for one.
"""

from __future__ import annotations

import pytest

from alphacouncil.domain.criterion_eval import CriterionVerdict
from alphacouncil.domain.criterion_sentence import MetricFacts, sentence_for

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# The five sentences, byte for byte
# --------------------------------------------------------------------------


class TestTheFiveSentences:
    def test_crossed_names_the_value_and_the_date(self) -> None:
        """⭐ 「已越过」 not 「已触发」, and the value is right there.

        ⭐ The reader wrote the threshold; this reports the comparison they asked for, not
        a verdict on their position.
        """
        got = sentence_for(
            MetricFacts(
                state=CriterionVerdict.CROSSED, label="gpMargin", value=0.97, as_of="2026-09-29"
            )
        )

        assert got.verdict == "已越过 —— gpMargin 现在 0.97（2026-09-29）。"
        assert got.crossed is True
        assert got.adjudicable is True

    def test_not_crossed_is_a_fact_and_nothing_else(self) -> None:
        """⭐ 红线 13: no adjective, no relief, no warning, no comment on the decision.

        ⭐ 「还好」 and 「没有越过」 are different sentences, ⭐ and dressing a market fact as
        comfort is the same move as a 成绩 badge wearing a different hat (红线 9).
        """
        got = sentence_for(
            MetricFacts(state=CriterionVerdict.NOT_CROSSED, label="ma20", value=1236.0)
        )

        assert got.verdict == "没有越过 —— ma20 现在 1,236。"
        assert got.crossed is False
        assert got.adjudicable is True

    def test_not_crossed_carries_no_relief_word(self) -> None:
        """⭐ The assertion the first spec recorded as 「已触发 must never appear」, in its
        current form. ⭐ 「已触发」 is now **allowed** — the comparison really did run — so
        what is banned is the *comfort* vocabulary, and the fact that changed is why.
        """
        sentence = sentence_for(
            MetricFacts(state=CriterionVerdict.NOT_CROSSED, label="ma20", value=1236.0)
        ).verdict

        for relief in ("还好", "幸好", "不错", "可喜"):
            assert relief not in sentence

    def test_warming_says_how_many_bars_are_missing(self) -> None:
        """⭐ The count is the whole reason this sentence is worth having.

        ⭐ 「还在预热」 alone is a dead end; 「还差 48 根」 says this resolves on its own,
        which is the difference between a deferral and a shrug.
        """
        got = sentence_for(
            MetricFacts(
                state=CriterionVerdict.WARMING,
                label="ma60",
                as_of="2026-09-29",
                period=60,
                bars_available=12,
            )
        )

        assert got.verdict == "观察期已到 —— ma60 还差 48 根日线才有值，这条判据暂时没有被求值。"
        assert got.crossed is False
        assert got.adjudicable is False

    def test_warming_says_the_count_never_goes_negative(self) -> None:
        """⭐ More bars than the period needs is not 「还差 -48 根」. ⭐ A negative count in a
        sentence about the reader's own data is the kind of thing that is obviously wrong
        and easy to ship."""
        got = sentence_for(
            MetricFacts(state=CriterionVerdict.WARMING, label="ma60", period=60, bars_available=99)
        )

        assert "还差" not in got.verdict
        assert "还没有值" in got.verdict

    def test_warming_without_a_count_does_not_invent_one(self) -> None:
        """⭐ No bars read means no count — a number there would be a fabrication."""
        got = sentence_for(
            MetricFacts(
                state=CriterionVerdict.WARMING,
                label="ma60",
                period=60,
                bars_available=None,
            )
        )

        assert got.verdict == "观察期已到 —— ma60 还没有值，这条判据没有被求值过。"

    def test_undetermined_quotes_the_name_as_typed(self) -> None:
        """⭐ Because the whole point is that we do not recognise it. ⭐ Rendering a
        catalogue label here would imply we do — and the reader would go looking for a
        metric that does not exist under that name.

        ⭐ The 「」 is load-bearing: it is what makes a token we do not recognise *look*
        unrecognised, and it is also what lets a reader who typed 「值得关注」 see their own
        word quoted back rather than read it as our opinion.
        """
        got = sentence_for(
            MetricFacts(state=CriterionVerdict.UNDETERMINED, label="revenue_yoy")
        )

        assert (
            got.verdict
            == "观察期已到 —— 「revenue_yoy」不在我们能算的指标里，这条判据没有被求值过。"
        )
        assert got.adjudicable is False

    def test_no_bars_is_about_the_source(self) -> None:
        got = sentence_for(MetricFacts(state=CriterionVerdict.NO_BARS, label="close"))

        assert got.verdict == "观察期已到 —— 这个代码没有日线，这条判据没有被求值过。"
        assert got.adjudicable is False


# --------------------------------------------------------------------------
# The three 「we don't know」 must not merge
# --------------------------------------------------------------------------


class TestTheThreeDontKnowsStayApart:
    @pytest.mark.parametrize(
        ("state", "label", "period", "bars"),
        [
            (CriterionVerdict.WARMING, "ma60", 60, 12),
            (CriterionVerdict.UNDETERMINED, "revenue_yoy", None, None),
            (CriterionVerdict.NO_BARS, "close", None, None),
        ],
    )
    def test_they_render_three_different_sentences(
        self, state: CriterionVerdict, label: str, period: int | None, bars: int | None
    ) -> None:
        """⭐ ⭐ **This is the whole feature.**

        ⭐ Collapsing them into 「条件没成立」 would be the most misleading thing this
        product could do: the reader would take it as news about their own judgement, when
        the condition was never tested at all. 红线 6 (§4.6): 「把『无法判断』降级成
        『看起来合理』的默认值」.
        """
        got = sentence_for(
            MetricFacts(
                state=state, label=label, period=period, bars_available=bars, as_of="2026-09-29"
            )
        )

        assert "条件没成立" not in got.verdict
        assert got.crossed is False
        assert got.adjudicable is False

    def test_all_three_are_distinct_from_each_other(self) -> None:
        """⭐ Asserted as **distinctness**, not as three literals: the mutation that made two
        of them share a sentence is the one worth catching, ⭐ and it needs a shape, not a
        string."""
        rendered = {
            sentence_for(
                MetricFacts(
                    state=state, label="ma60", period=60, bars_available=12, as_of="2026-09-29"
                )
            ).verdict
            for state in (
                CriterionVerdict.WARMING,
                CriterionVerdict.UNDETERMINED,
                CriterionVerdict.NO_BARS,
            )
        }

        assert len(rendered) == 3

    def test_only_a_comparison_is_adjudicable(self) -> None:
        """⭐ 「你今天就能据此行动」 is exactly two states, and the flag drives the styling —
        ⭐ so it must not be inferred from the sentence, or the two could disagree."""
        adjudicable = {
            state: sentence_for(
                MetricFacts(
                    state=state, label="ma60", value=1.0, period=60, bars_available=12
                )
            ).adjudicable
            for state in CriterionVerdict
        }

        assert adjudicable[CriterionVerdict.CROSSED] is True
        assert adjudicable[CriterionVerdict.NOT_CROSSED] is True
        assert adjudicable[CriterionVerdict.WARMING] is False
        assert adjudicable[CriterionVerdict.UNDETERMINED] is False
        assert adjudicable[CriterionVerdict.NO_BARS] is False

    def test_only_crossed_marks_the_accent(self) -> None:
        crossed = {
            state: sentence_for(MetricFacts(state=state, label="ma60", value=1.0)).crossed
            for state in CriterionVerdict
        }

        assert crossed[CriterionVerdict.CROSSED] is True
        assert sum(crossed.values()) == 1


# --------------------------------------------------------------------------
# Total, and the state that no fixture produces
# --------------------------------------------------------------------------


class TestItIsTotal:
    def test_every_state_has_an_answer(self) -> None:
        for state in CriterionVerdict:
            assert sentence_for(MetricFacts(state=state, label="x")).verdict

    def test_an_unknown_state_raises_instead_of_returning_nothing(self) -> None:
        """⭐ A rendering function that quietly returned ``None`` for an unrecognised state
        would turn a **server bug** into a blank row on the one page the reader opens to
        find out what went wrong.

        ⭐ Unreachable through the enum, and deliberately still handled: this function is
        reachable from JSON, where the state is whatever the server sent.
        """
        with pytest.raises(ValueError, match="unknown criterion state"):
            sentence_for(MetricFacts(state="typo", label="x"))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The state names have one home
# --------------------------------------------------------------------------


class TestTheStateNamesHaveOneHome:
    def test_the_rendering_layer_imports_the_evaluator_enum(self) -> None:
        """⭐ Spec 044's first draft declared its own ``Literal`` of the same five strings
        and ``mypy`` refused it. ⭐ The reason it was wrong is worth keeping executable:
        the stated worry was 「不要把求值器拖进渲染层」, ⭐ and the actual price was a second
        home for five names — the exact thing the whole move existed to remove.
        """
        from alphacouncil.domain import criterion_sentence

        assert criterion_sentence.CriterionState is CriterionVerdict


# --------------------------------------------------------------------------
# 红线 8, as an executable claim
# --------------------------------------------------------------------------


class TestNoRecommendationVocabularyExists:
    @pytest.mark.parametrize(
        "banned",
        ["推荐", "精选", "值得关注", "异动", "机会", "建议买入", "建议卖出"],
    )
    def test_no_state_can_produce_a_recommendation(self, banned: str) -> None:
        """⭐ 红线 8: 「功能是『拦截』不是『推荐』」.

        ⭐ The banned shapes are the ones whose **subject is the product**. ⭐ Every
        sentence here has the reader as its subject — 「你写的判据」 is theirs, the
        threshold is theirs — so the check is over all five states with several
        realistic metric names substituted in.

        ⭐ The real reason it holds is not the word list: ⭐ :class:`MetricFacts` has no
        field for a recommendation, ⭐ so :func:`sentence_for` has no vocabulary to build
        one from. This test is the tripwire on that, not the mechanism.
        """
        for state in CriterionVerdict:
            for label in ("gpMargin", "close", "revenue_yoy", "你的理由", ""):
                rendered = sentence_for(
                    MetricFacts(
                        state=state,
                        label=label,
                        value=1.0,
                        period=60,
                        bars_available=12,
                        as_of="2026-09-29",
                    )
                ).verdict
                assert banned not in rendered

    def test_a_metric_named_like_a_recommendation_is_still_a_metric(self) -> None:
        """⭐ ⭐ **The case the word list must not try to catch, and it is worth a test
        because the first draft got it wrong.**

        ⭐ A reader may write ``值得关注`` into a criterion, ⭐ and then the rendered
        sentence contains 「值得关注」 — ⭐ which would make a naive
        ``assert '值得关注' not in verdict`` fail on a legitimate row, ⭐ and tempt the
        next person into banning a substring instead of a shape.

        ⭐ The reason it is not a recommendation is **position and role**: it is the
        reader's own metric token, quoted back inside 「… 现在 1.00」, ⭐ not a claim the
        product is making. ⭐ `undetermined` quotes it explicitly with 「」, ⭐ which is
        where it most obviously reads as "we do not know this token".
        """
        rendered = sentence_for(
            MetricFacts(
                state=CriterionVerdict.UNDETERMINED, label="值得关注", value=1.0
            )
        ).verdict

        assert rendered == (
            "观察期已到 —— 「值得关注」不在我们能算的指标里，这条判据没有被求值过。"
        )
        assert "我们" in rendered

    def test_the_fields_are_the_boundary(self) -> None:
        """⭐ There is no ``confidence``, no ``score``, no ``rank``.

        ⭐ Any of those is the first step towards 「值得关注」, ⭐ so the absence is asserted
        as a shape rather than left to a reader's judgement.
        """
        assert set(MetricFacts.__slots__) == {
            "state",
            "label",
            "value",
            "as_of",
            "period",
            "bars_available",
        }


# --------------------------------------------------------------------------
# Number formatting, and the round trip that broke
# --------------------------------------------------------------------------


class TestNumberFormatting:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1185.3, "1185.30"),
            (1236.0, "1,236"),
            (1236, "1,236"),
            (0.97, "0.97"),
            (0.0, "0"),
            (-3.5, "-3.50"),
            (1e9, "1,000,000,000"),
        ],
    )
    def test_the_shape_of_a_number(self, value: float, expected: str) -> None:
        """⭐ ⭐ **This is the assertion that caught the fixture drift.**

        ⭐ ``formatValue`` in TypeScript used ``Number.isInteger`` and ``toFixed(2)``, and
        the first E2E fixture after the move wrote ``1,185.30`` — with a thousands
        separator on a **fractional** value. ⭐ The separator is only added when the number
        **is** an integer, so the fixture was wrong and the page was right, ⭐ and the
        failure read as a rendering bug in code that had not changed.

        ⭐ A fractional reading prints as it is: ``1235.5800000001`` in a sentence about
        the reader's own money claims a precision the data does not have.
        """
        from alphacouncil.domain.criterion_sentence import format_value

        assert format_value(value) == expected
