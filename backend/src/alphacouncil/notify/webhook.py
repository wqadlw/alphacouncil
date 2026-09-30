"""Webhook delivery (spec 044) — ADR-0031's table, executed row by row.

## ⭐ The rows that decided what this file is not

ADR-0031 answered 「HTTP 出口属于谁」 by asking what a webhook needs from §7.8's seven:

| §7.8 | webhook | here |
|---|---|---|
| 超时 / 连接复用 | 要 | :func:`alphacouncil.core.http.build_client` |
| 最小间隔 + 抖动 | 要(飞书等有 QPS 限) | :func:`_throttle` |
| 默认 UA | ⭐ **要,但必须诚实** | :data:`_USER_AGENT` |
| 熔断 | 要,语义不同 | :func:`_consecutive_failures` |
| ⭐ 缓存 | ⭐ **不要 —— 有害** | ⭐ **this module imports no cache at all** |

⭐ The last row is the expensive one to get right. ADR-0031 wrote it this way:

    > ⭐ 如果当初没有把 webhook 塞进行情层,就不会有人试图让通知继承数据缓存.
    > 那个继承一旦写进去,几乎不可能被审出来 —— 它长得太像「复用了已有的好机制」.

⭐ A dedup that looks like a cache **does not live here either**: it is
:mod:`alphacouncil.storage.repositories.notifications`, and it answers 「关于这一件事我
说过没有」, not 「这个值我们取过没有」. ⭐ Same word, opposite failure mode — a cache that
deduplicates a notification is a silently dropped reminder.

## ⭐ The UA is honest, and that is the whole point of the row

The market-data path **must** disguise itself: 腾讯/新浪/东财 refuse agents they do not
recognise. ⭐ A webhook must do the opposite — 飞书/企业微信 log the agent, and a request
that lies about being a browser is a request nobody can debug.

So: ``AlphaCouncil-Webhook/1.0``, never a Mozilla string. ⭐ And
:func:`alphacouncil.core.http.build_client` takes ``user_agent`` as a **required**
argument precisely so that neither path can inherit the other's value by accident.

## ⭐ Validation happens before the socket

Inherited from :mod:`alphacouncil.notify.email`, and for the same reason: a malformed URL
should cost **nothing**, not a connect timeout. ⭐ The URL is validated by
:func:`alphacouncil.notify.webhook.is_valid_url` — deliberately conservative, and
explicitly **not** a general URL parser.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import structlog

from alphacouncil.core.http import build_client

log = structlog.get_logger(__name__)

__all__ = [
    "USER_AGENT",
    "ChannelConfig",
    "Delivery",
    "is_configured",
    "is_valid_url",
    "send_webhook",
]

#: ⭐ **Honest.** See the module docstring — this is the row ADR-0031 marked 要 but with
#: 「必须是诚实的」 attached, and it is the one string a reader of a webhook server's log
#: will rely on.
USER_AGENT = "AlphaCouncil-Webhook/1.0"

#: ⭐ Gap between deliveries, in seconds. 飞书 and 企业微信 both rate-limit per bot, ⭐ and a
#: personal watchlist is a handful of rows — so this is a **floor for the channel's own
#: politeness**, not a throughput plan. The jitter is what keeps two sessions from
#: converging on the same instant.
_MIN_INTERVAL_S = 1.0
_JITTER_S = 0.5

#: ⭐ **No retry.** ADR-0031's 熔断 row says the semantics differ: a stale data source
#: should be retried and a broken channel should not be. ⭐ `email.py` retries twice;
#: this does not, because ⭐ **a repeated notification is the product's own version of
#: nagging** (红线 11) and a webhook receiver is usually a chat app that will show both.
_MAX_ATTEMPTS = 1

#: Schemes a webhook may use. ⭐ `file://` and `data:` are excluded on purpose: this
#: function's whole contract is "hand a rendered message to somebody else's HTTP
#: endpoint", and a scheme outside that is a configuration error worth catching before a
#: socket rather than an interesting surprise after one.
_ALLOWED_SCHEMES = frozenset({"https", "http"})

_LOCK = threading.Lock()


@dataclass
class _Gate:
    """The channel's process-wide state, in one object.

    ⭐ The first draft used three module globals and a ``global`` statement inside each
    function — ⭐ and ``ruff --fix`` deleted the ``noqa`` that was carrying the reason, so
    the reason went with it and the code was left saying nothing about why a module global
    is correct here. ⭐ Grouping them makes the alternative visible: a caller could pass
    its own gate, and that would be wrong for the same reason the session in
    ``financial.py`` is process-wide — ⭐ two channels posting at once is exactly what the
    throttle exists to prevent.
    """

    last_sent: float | None = None
    consecutive_failures: int = 0


_GATE = _Gate()

#: ⭐ A channel that has failed this many times in a row stops being tried, until a
#: success resets it. ⭐ **Not** a cooldown with a timer: ⭐ this is a command, so there is
#: no background loop to retry on, ⭐ and the honest behaviour is 「stop trying, and say so
#: in the output the human reads」.
_FAILURE_CIRCUIT = 5


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """Where to POST, and what to call ourselves.

    ⭐ ``url`` is a whole field rather than a base plus a token, because ⭐ a webhook URL
    almost always **embeds its token** (``https://open.feishu.cn/.../hook/xxxxxxxx``).
    Splitting it would put the token in an ordinary field that anything may ``print``, ⭐
    and the config is a :class:`~pydantic.SecretStr` for exactly that reason.
    """

    url: str


@dataclass(frozen=True, slots=True)
class Delivery:
    """What happened, in enough detail to log once and stop."""

    delivered: bool
    status_code: int | None = None
    detail: str | None = None


def is_valid_url(url: str) -> bool:
    """Whether ``url`` is a webhook endpoint worth attempting.

    ⭐ Deliberately conservative, for the same reason ``is_valid_email`` is: ⭐ this gates
    configuration, so a false positive becomes a request against something that is not a
    webhook, ⭐ and a false negative blocks a channel the user configured correctly. It is
    **not** a general URL validator and does not claim to be — ⭐ in particular it does not
    check that the host resolves, because that costs the thing this function exists to
    avoid.
    """
    candidate = (url or "").strip()
    if not candidate or candidate != url.strip():
        return False
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return False
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return False
    if not parts.netloc or " " in candidate:
        return False
    # ⭐ A URL with a fragment never sends one, and one with a query and no netloc is
    # almost certainly a typo — ⭐ both are configuration mistakes that would otherwise
    # surface as an opaque server-side error.
    return parts.fragment == ""


def is_configured(config: ChannelConfig | None) -> bool:
    """Whether we have somewhere to POST."""
    return config is not None and is_valid_url(config.url)


def _throttle() -> None:
    """Sleep until this delivery is allowed to happen.

    ⭐ The first one is not delayed — there is no previous access to be spaced away from,
    ⭐ and an unconditional sleep makes the cold path visibly slower for nothing.
    """
    if _GATE.last_sent is None:
        return
    # `random` is a fine source of jitter and a terrible source of anything else, so the

    # who should have to see the justification.
    wait = _MIN_INTERVAL_S + random.uniform(0.0, _JITTER_S) - (  # noqa: S311
        time.monotonic() - _GATE.last_sent
    )
    if wait > 0.0:
        time.sleep(wait)


def send_webhook(
    config: ChannelConfig | None, title: str, body: str
) -> Delivery:
    """POST one rendered message. ⭐ Never raises — failure is a return value.

    ⭐ **The caller decides what is worth sending.** This function opens with a rendered
    title and body and has no vocabulary for 「机会」「推荐」「异动」 — ⭐ red line 8 is
    enforced by the shape of this signature, not by a word list somewhere else.
    """


    if not title.strip() or not body.strip():
        return Delivery(delivered=False, detail="nothing to say")
    if not is_configured(config):
        return Delivery(delivered=False, detail="channel not configured")
    if _GATE.consecutive_failures >= _FAILURE_CIRCUIT:
        return Delivery(
            delivered=False,
            detail=f"circuit open after {_GATE.consecutive_failures} failures",
        )

    assert config is not None  # narrowed by is_configured
    payload: dict[str, Any] = {"msg_type": "text", "content": {"text": f"{title}\n{body}"}}
    headers = {"Content-Type": "application/json; charset=utf-8"}

    with _LOCK:
        _throttle()
        try:
            client = build_client(user_agent=USER_AGENT, headers=headers)
            try:
                response = client.post(config.url, json=payload)
                status = response.status_code
                ok = status < 400
                detail = None if ok else f"HTTP {status}"
            finally:
                client.close()
        except Exception as exc:
            _GATE.consecutive_failures += 1
            log.warning("notify.webhook_failed", error=type(exc).__name__, detail=str(exc))
            return Delivery(delivered=False, detail=f"{type(exc).__name__}: {exc}")
        finally:
            # ⭐ The timestamp moves even on failure, for the same reason
            # `financial.py` does it: 「失败也算一次访问」. ⭐ A throttle that forgives
            # failures is the one that gets us blocked.
            _GATE.last_sent = time.monotonic()

    if ok:
        _GATE.consecutive_failures = 0
        log.info("notify.webhook_sent", status=status)
    else:
        _GATE.consecutive_failures += 1
        log.warning("notify.webhook_rejected", status=status, failures=_GATE.consecutive_failures)
    return Delivery(delivered=ok, status_code=status, detail=detail)
