"""The webhook channel and the one dispatcher that calls it (spec 044).

## ⭐ Nothing here touches a socket

Every test replaces ``build_client`` with a fake. ⭐ The web server this talks to is a real
endpoint somebody configured, ⭐ and a suite that occasionally posts to it would send the
project's own notices to a stranger's chat.

## ⭐ What these tests are actually for

Two claims carry the whole design, and both are the kind a mutation run targets:

1. ⭐ **A failed delivery is not recorded.** If it were, the next run would skip it and the
   reader would never hear about a thing we were one retry short of telling them.
2. ⭐ **The same criterion is said once.** Keying on the verdict as well would notify on
   every flip, which is 「异动提醒」 (红线 8) and nagging (红线 11).

The other tests pin the shape of the boundary: what ADR-0031's table said must and must not
be present.
"""

from __future__ import annotations

import ast
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from alphacouncil.domain.criterion_eval import CriterionVerdict
from alphacouncil.notify import dispatch, webhook
from alphacouncil.notify.webhook import ChannelConfig, send_webhook
from alphacouncil.storage import migrate
from alphacouncil.storage.repositories import notifications as repository

pytestmark = pytest.mark.unit

STAMP = "2026-09-30T00:00:00.000Z"
URL = "https://open.feishu.cn/open-apis/bot/v2/hook/abc123"


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Clock:
    """A monotonic clock that **advances on every read**, and remembers what it gave out.

    ⭐ ⭐ **This exists because a pinned clock made an assertion vacuous.** ⭐ The throttle's
    「failed calls still count」 test pinned ``monotonic`` to a constant, ⭐ so
    ``last_sent == 100.0`` was true whether the timestamp was updated or not — ⭐ and the
    mutation run said so by surviving the removal. ⭐ A clock that moves turns 「was it
    written?」 into 「is it the value this clock last produced?」.

    ⭐ The ``reads`` list is what makes the assertion independent of **how many** times the
    code happens to read the clock. ⭐ Hard-coding an expected value instead would pin the
    test to today's call sequence, ⭐ so a harmless extra read would break it — ⭐ and the
    next person would delete the assertion rather than the read.
    """

    def __init__(self, start: float = 100.0, step: float = 7.0) -> None:
        self.now = start
        self.reads: list[float] = []
        self._step = step

    def __call__(self) -> float:
        self.reads.append(self.now)
        self.now += self._step
        return self.now - self._step


class _Client:
    """Records every POST, answers from a script.

    ⭐ It has a ``close()`` because the real client is closed in a ``finally`` — ⭐ and the
    first version of this double did not, so **every** delivery test failed with
    ``AttributeError: '_Client' object has no attribute 'close'``.

    ⭐ That is worth recording rather than just adding the method: ⭐ a test double that does
    not implement the whole contract makes the double, not the code, the thing under test.
    """

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.posts: list[tuple[str, Any, str | None]] = []
        self.closed = False
        self.user_agent: str | None = None

    def post(self, url: str, json: Any = None) -> _Response:
        self.posts.append((url, json, self.user_agent))
        return _Response(self.status)

    def close(self) -> None:
        self.closed = True


_LAST_CLIENT: Any = None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Client]:
    """A scripted client, which also carries the UA it was built with."""
    made = _Client()
    monkeypatch.setattr(webhook, "build_client", _factory(made))
    # ⭐ Reset the process-wide gate, or one test's failure count becomes the next test's
    # circuit-open. ⭐ The same trap `financial.py`'s tests have to reset `_LOGGED_IN`.
    monkeypatch.setattr(webhook._GATE, "last_sent", None)
    monkeypatch.setattr(webhook._GATE, "consecutive_failures", 0)
    monkeypatch.setattr(webhook, "_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(webhook, "_JITTER_S", 0.0)
    yield made


def _factory(made: _Client) -> Any:
    def build(**kwargs: Any) -> Any:
        made.user_agent = kwargs.get("user_agent")
        return made

    return build


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """The real schema, in memory."""
    script = "\n".join(item.up.read_text(encoding="utf-8") for item in migrate.load_migrations())
    connection = sqlite3.connect(":memory:")
    for statement in migrate.split_statements(script):
        connection.execute(statement)
    try:
        yield connection
    finally:
        connection.close()


def _item(
    decision_id: str = "2026-09-20T01:00:00.000Z",
    *,
    state: str = "crossed",
    value: float | None = 1185.3,
    as_of: str | None = "2026-09-29",
    adjudicable: bool = True,
    metric: str = "ma20",
    display: str = "600519.SH",
    threshold: float = 1200,
    verdict: str = "已越过 —— ma20 现在 1185.30（2026-09-29）。",
) -> dict[str, object]:
    """One attention row, in the shape `/api/v1/today` sends.

    ⭐ Every field that makes a criterion *identifiable* is a parameter — ⭐ including
    ``threshold``. ⭐ The first version of the "the reader rewrote their criterion" test
    reached into the nested dict and rebuilt it, ⭐ and `mypy` refused: ⭐ the dict is typed
    ``object``, ⭐ so poking at it is the test arguing with the type system instead of
    saying what it means.
    """
    return {
        "kind": "kill_criterion_due",
        "item": {
            "decision_id": decision_id,
            "market": "sh",
            "code": "600519",
            "display": display,
            "action": "buy",
            "criterion": {
                "metric": metric,
                "operator": "<",
                "threshold": threshold,
                "as_of": "2026-09-20",
            },
        },
        "metric": {
            "state": state,
            "label": metric,
            "value": value,
            "as_of": as_of,
            "period": None,
            "bars_available": None,
        },
        "verdict": verdict,
        "adjudicable": adjudicable,
    }


# --------------------------------------------------------------------------
# The channel
# --------------------------------------------------------------------------


class TestTheChannel:
    def test_it_posts_and_reports_success(self, client: _Client) -> None:
        outcome = send_webhook(ChannelConfig(url=URL), "标题", "正文")

        assert outcome.delivered is True
        assert outcome.status_code == 200
        assert len(client.posts) == 1
        assert client.posts[0][0] == URL
        assert "标题" in client.posts[0][1]["content"]["text"]

    def test_the_user_agent_is_our_own_name(self, client: _Client) -> None:
        """⭐ ⭐ **ADR-0031's row: 「默认 UA: 要，但必须是诚实的 UA」.**

        ⭐ The market-data path *must* disguise itself and this path must not. ⭐ A webhook
        that says ``Mozilla/5.0`` is a request nobody can debug on the far side, ⭐ and
        ``build_client`` takes ``user_agent`` as a **required** argument precisely so
        neither path can inherit the other's value by accident.
        """
        send_webhook(ChannelConfig(url=URL), "标题", "正文")

        assert client.user_agent == "AlphaCouncil-Webhook/1.0"

    def test_the_user_agent_is_not_a_browser(self) -> None:
        """⭐ Asserted separately from the value above: ⭐ the property is 「not lying」 and
        a future edit to the version string should not have to preserve it by luck."""
        assert "Mozilla" not in webhook.USER_AGENT
        assert "Safari" not in webhook.USER_AGENT

    def test_a_refusal_is_a_return_value_not_an_exception(self, client: _Client) -> None:
        client.status = 403

        outcome = send_webhook(ChannelConfig(url=URL), "标题", "正文")

        assert outcome.delivered is False
        assert outcome.status_code == 403
        assert "403" in (outcome.detail or "")

    def test_an_unconfigured_channel_costs_nothing(self, client: _Client) -> None:
        """⭐ Validation before the socket, inherited from ``email.py``: ⭐ a bad URL should
        cost nothing rather than a connect timeout."""
        outcome = send_webhook(None, "标题", "正文")

        assert outcome.delivered is False
        assert client.posts == []

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "   ",
            "not a url",
            "ftp://x/y",
            # ⭐⭐ **`file://host/x`, not `file:///etc/passwd`.** ⭐ The first version of
            # this list used the triple-slash form, ⭐ and the mutation run then showed a
            # `file://` scheme added to the allowlist survived — ⭐ because
            # `urlsplit("file:///etc/passwd").netloc` is `''`, ⭐ so the URL was already being
            # refused for **having no host** rather than for its scheme. ⭐ The test was
            # passing for the wrong reason, ⭐ and a scheme check that is only ever
            # exercised by a URL that fails another check is not a scheme check.
            "file://host/etc/passwd",
            "data://host/x",
        ],
    )
    def test_a_bad_url_is_refused_before_any_request(self, url: str) -> None:
        """⭐ ⭐ Each case isolates **one** reason, ⭐ because a URL can fail several and a
        test that does not isolate cannot say which rule fired.

        ⭐ ``file://`` is in the list on purpose. ⭐ This function's whole contract is
        「hand a rendered message to somebody else's endpoint」, ⭐ and a scheme outside that
        is a configuration mistake worth catching before a socket.
        """
        assert webhook.is_valid_url(url) is False

    @pytest.mark.parametrize("scheme", ["file", "data", "ftp", "gopher", "javascript"])
    def test_only_the_two_schemes_are_allowed(self, scheme: str) -> None:
        """⭐ The scheme allowlist, stated as a property rather than as three examples.

        ⭐ A list of bad URLs stops at the first scheme nobody thought of, ⭐ and the fix
        above happened because a mutation found a gap — ⭐ not because the list was read
        carefully.
        """
        assert webhook.is_valid_url(f"{scheme}://host/path") is False

    def test_nothing_to_say_is_not_a_delivery(self, client: _Client) -> None:
        assert send_webhook(ChannelConfig(url=URL), "  ", "正文").delivered is False
        assert send_webhook(ChannelConfig(url=URL), "标题", "  ").delivered is False
        assert client.posts == []

    def test_the_channel_cannot_recommend_anything(self) -> None:
        """⭐ ⭐ **红线 8, enforced by the signature.**

        ⭐ The parameters are ``(config, title, body)``. ⭐ There is no field for a
        recommendation, no ``priority``, no ``urgency`` — ⭐ so the shape of this function is
        the rule, ⭐ and a word list somewhere else would only ever be a weaker version of
        it. ⭐ ``send_due_criteria`` is the only caller and the only source of the text.
        """
        assert send_webhook.__doc__ is not None
        assert "recommend" not in send_webhook.__doc__.lower()
        parameters = list(send_webhook.__annotations__)
        assert parameters == ["config", "title", "body", "return"]

    def test_it_carries_no_cache_at_all(self) -> None:
        """⭐ ADR-0031's most expensive row: 「缓存 | ⭐ **不要 —— 有害**」.

        ⭐ Asserted over the **imports**, not over the file's text. ⭐ ⭐ The first version
        grepped the source for ``cache`` and failed — because this docstring says 「cache」,
        ⭐ ⭐ which is the same shape as `F-122`/spec 025's 「**规则在描述自己**」: ⭐ a check
        that reads the very text explaining it cannot tell the rule from its explanation.

        ⭐ Over imports it is both stronger and immune: ⭐ a cache here would be an import of
        one, ⭐ and the only way to introduce one is to write that import.
        """
        tree = ast.parse(Path(webhook.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        for banned in ("providers.cache", "alphacouncil.providers.cache", "cachetools"):
            assert banned not in imported

    def test_and_it_does_not_reach_the_market_data_layer(self) -> None:
        """⭐ ⭐ The inheritance ADR-0031 refused, as a reachability claim.

        ⭐ The sentence it wrote: 「⭐ 如果当初没有把 webhook 塞进行情层，就不会有人试图让
        通知继承数据缓存」. ⭐ So the thing to pin is that **the channel and the dispatcher
        cannot reach ``providers/`` at all** — ⭐ not that one file avoids one module, ⭐
        because the inheritance would arrive through a helper, not through a direct import.

        ⭐ ⭐ **The first version of this test scanned every file in ``notify/`` and failed
        on ``__main__.py``**, which imports ``default_router`` to evaluate criteria. ⭐ The
        test was right about the property and wrong about the scope: ⭐ the command entry
        point is where dependencies get assembled, ⭐ which is exactly its job, ⭐ and it is
        the same wiring ``/api/v1/today`` gets from ``deps.py``. ⭐ What must stay clean is
        the pair that *decides and delivers*.
        """
        offenders: list[str] = []
        for path in (webhook.__file__, Path(dispatch.__file__)):
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else []
                )
                # ⭐ `ast.walk` yields `ast.expr` nodes too, and only `stmt` subclasses
                # carry `lineno` — ⭐ narrowing on the import types is what keeps the
                # error report pointing at the offending line.
                if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                    name.startswith("alphacouncil.providers") for name in names
                ):
                    offenders.append(f"{Path(path).name}:{node.lineno}")

        assert offenders == []

    def test_the_throttle_is_not_the_market_ones(self) -> None:
        """⭐ ⭐ Two throttles exist and they are **not** shared, on purpose.

        ⭐ ``providers/financial.py`` spaces BaoStock calls ~0.35s apart because its
        **IP ban** is the thing being avoided; ⭐ this channel spaces webhook posts 1.0s
        apart because 飞书 limits a bot's QPS. ⭐ Sharing one constant would make one of those
        two facts invisible, ⭐ and the second one to be changed would silently move the
        other. ⭐ The duplication is the point, and this test says so before somebody
        「cleans it up」.
        """
        from alphacouncil.providers import financial

        assert webhook._MIN_INTERVAL_S != financial._MIN_INTERVAL_S
        assert webhook._GATE is not getattr(financial, "_GATE", object())

    def test_a_broken_channel_stops_being_tried(self, client: _Client) -> None:
        """⭐ ADR-0031's 熔断 row, with **different semantics**, as its table says: ⭐ a
        stale data source should be retried and a broken channel should not.

        ⭐ After five failures it stops — ⭐ and because this is a command with no background
        loop, 「stop」 means 「say so in the output the human reads」 rather than 「try again
        later on its own」.
        """
        client.status = 500
        for _ in range(webhook._FAILURE_CIRCUIT):
            send_webhook(ChannelConfig(url=URL), "标题", "正文")

        before = len(client.posts)
        outcome = send_webhook(ChannelConfig(url=URL), "标题", "正文")

        assert len(client.posts) == before
        assert "circuit open" in (outcome.detail or "")

    def test_one_success_resets_the_failure_count(self, client: _Client) -> None:
        """⭐ ⭐ **This replaced a test that asserted the circuit reopens — and that was
        wrong about the design.**

        ⭐ The first version hammered it five times, then flipped the script to success and
        expected delivery, and it failed. ⭐ ⭐ **The code was right and the test was not**:
        a circuit that opens can never close, because the only thing that resets it is the
        success it can no longer reach. ⭐ That is a channel that is dead until somebody
        restarts the process — ⭐ which is a bad property to ship while calling it a
        breaker.

        ⭐ So the honest semantics is per-**run**: ⭐ within one invocation a broken channel
        stops being tried, ⭐ and the next invocation starts from zero because the state is
        module-level. ⭐ What a success resets is the **counter**, and that is what this
        asserts — ⭐ one success in the middle must not leave the count where it was.
        """
        client.status = 500
        for _ in range(webhook._FAILURE_CIRCUIT - 1):
            send_webhook(ChannelConfig(url=URL), "标题", "正文")
        assert webhook._GATE.consecutive_failures == webhook._FAILURE_CIRCUIT - 1

        client.status = 200
        assert send_webhook(ChannelConfig(url=URL), "标题", "正文").delivered is True

        assert webhook._GATE.consecutive_failures == 0

    def test_the_circuit_is_per_run_not_per_process_lifetime(self) -> None:
        """⭐ ⭐ **What the previous test's bug was really about, stated as a property.**

        ⭐ There is no background loop, so 「a cooldown that expires」 would have nothing to
        wake it. ⭐ The state lives in module scope and the module is imported fresh by each
        invocation of ``python -m alphacouncil.notify`` — ⭐ so 「wait and try again later」
        is expressed by **running the command again**, ⭐ which is the only thing that can
        happen here and is therefore the thing to document.
        """
        import importlib

        fresh = importlib.reload(webhook)

        assert fresh._GATE.consecutive_failures == 0
        assert fresh._GATE.last_sent is None

    def test_a_failed_call_still_counts_against_the_throttle(
        self, client: _Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """⭐ §7.8: 「失败也算一次访问」 — ⭐ the same rule ``financial.py`` obeys.

        ⭐ A throttle that forgives failures is the one that gets an address blocked, and a
        webhook endpoint that starts rate-limiting us is how a reader stops being told.

        ⭐⭐ **The clock has to *move*, and the first version of this test did not.** ⭐ It
        pinned ``monotonic`` to a constant and asserted ``last_sent == 100.0`` — ⭐ which is
        exactly what the fixture had set it to, ⭐ so deleting the assignment entirely
        survived the mutation run. ⭐ **A constant clock makes 「the timestamp was
        updated」 and 「the timestamp was left alone」 the same observation**, ⭐ and this
        assertion was vacuous until the clock advanced.
        """
        slept: list[float] = []
        clock = _Clock()
        monkeypatch.setattr("alphacouncil.notify.webhook.time.sleep", slept.append)
        monkeypatch.setattr("alphacouncil.notify.webhook.time.monotonic", clock)
        # ⭐ A floor of 60s and a starting point 30s in the past, ⭐ so the wait is
        # ``60 - 30 = 30`` and the sleep happens — ⭐ **and** so the fixture's value is
        # neither what the clock first returns (100) nor any later one.
        # ⭐ The first two versions failed the mutation run for the same reason: ⭐ the
        # fixture's starting value **coincided with a value the clock produces**, ⭐ so
        # 「the timestamp was updated」 and 「it was never touched」 were the same number.
        # ⭐ That is a nastier shape than a weak assertion: ⭐ the test looked strict.
        monkeypatch.setattr(webhook, "_MIN_INTERVAL_S", 60.0)
        monkeypatch.setattr(webhook, "_JITTER_S", 0.0)
        monkeypatch.setattr(webhook._GATE, "last_sent", clock.now - 30.0)
        started_at = clock.now - 30.0

        client.status = 500
        send_webhook(ChannelConfig(url=URL), "标题", "正文")

        assert slept == [pytest.approx(30.0)]
        # ⭐ **The value the clock last handed out**, ⭐ which can only have come from the
        # `finally` block — ⭐ and that block runs on the failure path too.
        assert webhook._GATE.last_sent == pytest.approx(clock.reads[-1])
        assert webhook._GATE.last_sent != pytest.approx(started_at)


# --------------------------------------------------------------------------
# What is worth saying
# --------------------------------------------------------------------------


class TestWhatIsWorthSaying:
    def test_an_actionable_criterion_becomes_one_notice(self) -> None:
        notices = dispatch.notices_for_due_criteria([_item()])

        assert len(notices) == 1
        assert notices[0].subject == "600519.SH"
        assert "已越过" in notices[0].body

    @pytest.mark.parametrize(
        ("state", "verdict"),
        [
            ("warming", "观察期已到 —— ma60 还差 48 根日线才有值，这条判据暂时没有被求值。"),
            ("undetermined", "观察期已到 —— 「x」不在我们能算的指标里，这条判据没有被求值过。"),
            ("no_bars", "观察期已到 —— 这个代码没有日线，这条判据没有被求值过。"),
        ],
    )
    def test_the_three_we_dont_knows_produce_nothing(
        self, state: str, verdict: str
    ) -> None:
        """⭐ ⭐ **Skipping them is a decision with a stated cost.**

        ⭐ They are **our** gap, not news about the reader's judgement, ⭐ and a daily
        「取不到日线」 is the 催促 that 红线 11 is about. ⭐ The cost is that a broken source
        means silence — ⭐ and that trade is written down so somebody can argue with it.
        """
        item = _item(state=state, adjudicable=False, verdict=verdict)

        assert dispatch.notices_for_due_criteria([item]) == []

    def test_a_missing_metric_produces_nothing(self) -> None:
        """⭐ ``metric: null`` means we could not read any bars — ⭐ and the row still has a
        sentence, so only the ``adjudicable`` flag keeps it out."""
        item = _item()
        item["metric"] = None
        item["verdict"] = "观察期已到 —— 这个代码没有日线，这条判据没有被求值过。"
        item["adjudicable"] = False

        assert dispatch.notices_for_due_criteria([item]) == []

    def test_a_not_crossed_criterion_is_still_worth_saying(self) -> None:
        """⭐ ⭐ It is a fact about the market that bears on the reader's own threshold, ⭐
        and 「没有越过」 stops there without becoming comfort (红线 13). ⭐ Only the three
        「我们不知道」 are silent."""
        notices = dispatch.notices_for_due_criteria(
            [
                _item(
                    state="not_crossed",
                    verdict="没有越过 —— ma20 现在 1,236。",
                    value=1236.0,
                )
            ]
        )

        assert len(notices) == 1
        assert "没有越过" in notices[0].body
        for relief in ("还好", "幸好"):
            assert relief not in notices[0].body

    def test_a_notice_names_the_instrument_and_the_criterion(self) -> None:
        (notice,) = dispatch.notices_for_due_criteria([_item()])

        assert notice.subject == "600519.SH"
        assert notice.body.startswith("600519.SH 你写的失效条件")

    def test_nothing_recommends_anything(self) -> None:
        """⭐ The dispatcher cannot render, ⭐ so it has no vocabulary for a recommendation.

        ⭐ Checked across every state with several metric names — ⭐ and **not** by banning
        a metric name that reads like a recommendation, ⭐ because a reader may legitimately
        write 「值得关注」 into a criterion (see ``test_criterion_sentence.py``).
        """
        for state in ("crossed", "not_crossed"):
            for metric in ("gpMargin", "close", "值得关注", "机会"):
                item = _item(state=state, metric=metric, verdict=f"{metric} 现在 1.00。")
                for notice in dispatch.notices_for_due_criteria([item]):
                    for banned in ("推荐", "精选", "值得买", "建议买入", "异动"):
                        assert banned not in notice.body


# --------------------------------------------------------------------------
# Saying it once
# --------------------------------------------------------------------------


class TestSayingItOnce:
    def test_the_same_criterion_is_not_said_twice(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ **The reason the fingerprint exists at all.**"""
        first = dispatch.send_due_criteria(
            db, [_item()], config=ChannelConfig(url=URL), now=STAMP
        )
        second = dispatch.send_due_criteria(
            db, [_item()], config=ChannelConfig(url=URL), now=STAMP
        )

        assert first.sent == 1
        assert second.sent == 0
        assert second.skipped_already_sent == 1
        assert len(client.posts) == 1

    def test_a_flip_back_is_not_a_new_fact(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ **The design decision, as an executable claim.**

        ⭐ A criterion that crossed and then stopped crossing is still **one** thing. ⭐ The
        alternative — keying on the verdict too — would notify on every flip, ⭐ which is
        「异动提醒」 (红线 8) and nagging (红线 11), ⭐ and the cost is paid by the reader.
        """
        dispatch.send_due_criteria(
            db,
            [_item(state="crossed", verdict="已越过 —— ma20 现在 1185.30。")],
            config=ChannelConfig(url=URL),
            now=STAMP,
        )
        second = dispatch.send_due_criteria(
            db,
            [_item(state="not_crossed", verdict="没有越过 —— ma20 现在 1,236。")],
            config=ChannelConfig(url=URL),
            now=STAMP,
        )

        assert second.sent == 0
        assert second.skipped_already_sent == 1
        assert len(client.posts) == 1

    def test_a_different_decision_is_a_different_fact(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        dispatch.send_due_criteria(
            db, [_item("2026-09-20T01:00:00.000Z")], config=ChannelConfig(url=URL), now=STAMP
        )
        second = dispatch.send_due_criteria(
            db, [_item("2026-09-21T01:00:00.000Z")], config=ChannelConfig(url=URL), now=STAMP
        )

        assert second.sent == 1

    def test_a_rewritten_threshold_is_a_different_fact(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ Because the reader changed what they said they were watching.

        ⭐ This is the one case where 「we told you once」 must **not** apply: ⭐ the reader
        has written a new criterion, ⭐ and silently swallowing it would mean the system
        ignores what they just typed.
        """
        dispatch.send_due_criteria(
            db, [_item()], config=ChannelConfig(url=URL), now=STAMP
        )
        # ⭐ The reader changed the threshold they are watching.
        item = _item(threshold=900)
        second = dispatch.send_due_criteria(
            db, [item], config=ChannelConfig(url=URL), now=STAMP
        )

        assert second.sent == 1


# --------------------------------------------------------------------------
# ⭐ The load-bearing one: a failure is not a memory
# --------------------------------------------------------------------------


class TestAFailureIsNotAMemory:
    def test_a_failed_delivery_is_not_recorded(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐⭐ **The difference between this table and a cache, in one test.**

        ⭐ If a failed delivery were recorded, the next run would skip it — ⭐ and the reader
        would never hear about a thing we were one retry short of telling them. ⭐ That is
        indistinguishable, from the outside, from 「we already told you」.

        ⭐ And the failure mode is invisible: nothing errors, nothing is logged as missing,
        ⭐ and the only symptom is a reader who says 「你怎么没告诉我」 about something that
        was correctly noticed and correctly not delivered.
        """
        client.status = 500

        first = dispatch.send_due_criteria(
            db, [_item()], config=ChannelConfig(url=URL), now=STAMP
        )

        assert first.sent == 0
        assert first.failed == 1
        assert repository.already_sent(db, channel="webhook", key=_key()) is False

    def test_and_the_next_run_says_it(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ The consequence of the test above, ⭐ and the reason it is the one that
        matters: ⭐ a transient failure must be retried, ⭐ and 「retry」 is only meaningful
        because nothing was written."""
        client.status = 500
        dispatch.send_due_criteria(db, [_item()], config=ChannelConfig(url=URL), now=STAMP)

        client.status = 200
        second = dispatch.send_due_criteria(
            db, [_item()], config=ChannelConfig(url=URL), now=STAMP
        )

        assert second.sent == 1
        assert repository.already_sent(db, channel="webhook", key=_key()) is True

    def test_a_failure_costs_no_row_and_no_junk(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ **Why only successes are written, stated as a cost.**

        ⭐ Recording failures too would mean a ``delivered = 0`` row that ⭐ **nothing is
        allowed to clean up** — ⭐ the table is append-only and says so with triggers — ⭐ and
        a failed channel would grow the table without bound.

        ⭐ The price is stated in the module docstring and is real: ⭐ this table cannot
        answer 「上次那条投递成功了吗」. ⭐ It answers 「关于这件事我说过没有」, ⭐ which is the
        question the product actually has.
        """
        client.status = 500
        dispatch.send_due_criteria(db, [_item()], config=ChannelConfig(url=URL), now=STAMP)

        assert len(repository.history(db)) == 0

    def test_an_unconfigured_channel_records_nothing(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ A channel that is switched off must not consume the notice.

        ⭐ Otherwise configuring the webhook later would find every due criterion already
        marked as told — ⭐ and the reader would get nothing on the day they turn it on.
        ⭐ This is the same failure ADR-0031 named for cache inheritance, arriving by a
        different road.
        """
        dispatch.send_due_criteria(db, [_item()], config=None, now=STAMP)

        assert repository.already_sent(db, channel="webhook", key=_key()) is False
        assert client.posts == []


def _key() -> str:
    return repository.fingerprint(
        kind="kill_criterion_due",
        decision_id="2026-09-20T01:00:00.000Z",
        metric="ma20",
        operator="<",
        threshold=1200.0,
        as_of="2026-09-20",
    )


# --------------------------------------------------------------------------
# The fingerprint itself
# --------------------------------------------------------------------------


class TestTheFingerprint:
    def test_it_is_stable(self) -> None:
        assert _key() == _key()

    def test_it_does_not_depend_on_the_conclusion(self) -> None:
        """⭐ ⭐ The claim in its most direct form: ⭐ the five inputs are the criterion, ⭐
        and the verdict is not among them.

        ⭐ A fingerprint that included the verdict would re-notify on every state change,
        ⭐ which is what the dispatcher's flip test forbids.
        """
        assert _key() == repository.fingerprint(
            kind="kill_criterion_due",
            decision_id="2026-09-20T01:00:00.000Z",
            metric="ma20",
            operator="<",
            threshold=1200.0,
            as_of="2026-09-20",
        )

    def test_a_space_cannot_forge_two_different_criteria(self) -> None:
        """⭐ ⭐ **The separator is load-bearing and this is its test.**

        ⭐ Joining with a space would let ``metric="a b", operator="c"`` and
        ``metric="a", operator="b c"`` collide — ⭐ and a collision means one reader's
        criterion silently swallows another's, ⭐ which shows up as a notification that was
        never delivered and never explained.
        """
        one = repository.fingerprint(
            kind="k", decision_id="d", metric="a b", operator="c", threshold=1.0, as_of="x"
        )
        two = repository.fingerprint(
            kind="k", decision_id="d", metric="a", operator="b c", threshold=1.0, as_of="x"
        )

        assert one != two

    def test_an_int_and_a_float_threshold_are_the_same_fact(self) -> None:
        """⭐ ``1200`` and ``1200.0`` are the same threshold, ⭐ and the reader writing one
        where the other was stored must not produce a second notification about the same
        criterion."""
        assert _key() == repository.fingerprint(
            kind="kill_criterion_due",
            decision_id="2026-09-20T01:00:00.000Z",
            metric="ma20",
            operator="<",
            threshold=1200,
            as_of="2026-09-20",
        )


# --------------------------------------------------------------------------
# The row that is written
# --------------------------------------------------------------------------


class TestTheRow:
    def test_it_stores_the_sentence_verbatim(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ 「我们当时到底说了什么」必须可查。 ⭐ That is also the second reason the wording
        moved into the server: ⭐ one day somebody will want to know whether the sentence a
        reader received is the sentence we would render today."""
        dispatch.send_due_criteria(db, [_item()], config=ChannelConfig(url=URL), now=STAMP)

        (row,) = repository.history(db)

        assert "已越过 —— ma20 现在 1185.30（2026-09-29）。" in row.body
        assert row.sent_at == STAMP
        assert row.channel == "webhook"

    def test_it_cannot_be_edited(self, db: sqlite3.Connection, client: _Client) -> None:
        """⭐ ⭐ Deleting is the worse half, but editing is the one a tool would try first.

        ⭐ Changing a row would change 「what the reader has already been told」 — ⭐ and
        unlike a cache, that history is **about them**, ⭐ so it is not ours to rewrite.
        """
        dispatch.send_due_criteria(db, [_item()], config=ChannelConfig(url=URL), now=STAMP)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE notifications_sent SET body = 'changed'")

    def test_it_cannot_be_deleted(self, db: sqlite3.Connection, client: _Client) -> None:
        """⭐ ⭐ ⭐ **The one that actually hurts.**

        ⭐ Delete a row and the same criterion is notified **again** — ⭐ to a reader who
        ⭐ already dealt with it. ⭐ That is not a lost cache entry, ⭐ it is a program
        nagging someone about something they finished, ⭐ and it looks exactly like a bug.
        """
        dispatch.send_due_criteria(db, [_item()], config=ChannelConfig(url=URL), now=STAMP)

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM notifications_sent")


# --------------------------------------------------------------------------
# The report the command prints
# --------------------------------------------------------------------------


class TestTheReport:
    def test_it_accounts_for_every_item(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ A report whose parts do not add up is worse than none.

        ⭐ Every row must land in exactly one bucket — ⭐ sent, un-actionable, already said,
        or failed — ⭐ and that is asserted as a **sum**, ⭐ because a report that drops a
        category reads like 「there was nothing else」 ⭐ while actually having silently
        dropped something.
        """
        attention = [
            _item("2026-09-20T01:00:00.000Z"),
            _item("2026-09-21T01:00:00.000Z"),
            _item(
                "2026-09-22T01:00:00.000Z",
                state="warming",
                adjudicable=False,
                verdict="观察期已到 —— ma60 还差 48 根日线才有值，这条判据暂时没有被求值。",
            ),
        ]

        report = dispatch.send_due_criteria(
            db, attention, config=ChannelConfig(url=URL), now=STAMP
        )

        assert report.considered == 3
        assert report.sent == 2
        assert report.skipped_not_actionable == 1
        assert report.failed == 0
        assert (
            report.sent
            + report.skipped_not_actionable
            + report.skipped_already_sent
            + report.failed
            == report.considered
        )

    def test_the_summary_names_what_happened(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        report = dispatch.send_due_criteria(
            db, [_item()], config=ChannelConfig(url=URL), now=STAMP
        )

        summary = report.summary()

        assert "发了 1 条" in summary
        assert "考虑了 1 条" in summary

    def test_nothing_to_say_is_still_a_success(
        self, db: sqlite3.Connection, client: _Client
    ) -> None:
        """⭐ ⭐ A quiet day must not look like a broken one.

        ⭐ This is a command, run by a person or by a scheduled task. ⭐ A non-zero exit on
        「nothing to say」 would make every quiet day report a failure, ⭐ and a failure the
        reader cannot act on trains them to ignore the signal.
        """
        report = dispatch.send_due_criteria(db, [], config=ChannelConfig(url=URL), now=STAMP)

        assert report.sent == 0
        assert report.considered == 0


def test_the_lock_is_process_wide_and_reentrant_safe() -> None:
    """⭐ The throttle serialises, ⭐ and a serialisation that could deadlock on a reentrant
    call would be worse than no throttle — ⭐ so this asserts the lock is an ordinary
    ``Lock`` rather than a ``RLock``, and that a second thread can actually get through."""
    assert isinstance(webhook._LOCK, type(threading.Lock()))

    gate = threading.Event()
    done = threading.Event()

    def worker() -> None:
        gate.wait()
        with webhook._LOCK:
            done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    gate.set()
    assert done.wait(timeout=5.0) is True
    thread.join(timeout=5.0)


def test_the_verdict_enum_is_the_one_source_of_actionability() -> None:
    """⭐ ⭐ 「什么状态可以据此行动」 must have **one** home.

    ⭐ The dispatcher's first draft carried its own list of two members — ⭐ which is the same
    mistake ``criterion_sentence.py`` made with its state names, ⭐ and mypy caught that one.
    ⭐ This test is the tripwire on the other half: :attr:`CriterionVerdict.answerable` is
    what gets asked, ⭐ so the list cannot drift away from the enum's own definition.
    """
    assert CriterionVerdict.CROSSED.answerable is True
    assert CriterionVerdict.NOT_CROSSED.answerable is True
    assert CriterionVerdict.WARMING.answerable is False
    assert dispatch._is_actionable(CriterionVerdict.UNDETERMINED) is False
