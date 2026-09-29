"""The one place an HTTP client is constructed (ADR-0031, S-01).

## Why this module exists

Constitution §7.8: 「禁止在业务代码里直接 `httpx.get` / `requests.get` / `urlopen`
—— 所有外部数据访问必须经过**唯一入口函数**」, and its reason is
「限流**必须是一个函数**，不能是"请大家记得加 sleep"」.

⭐ That reason is why ``S-01`` exists, and ``S-01`` used to allow construction anywhere under
``providers/``. Which made the *intent* ("clients are built in recognised places") and the
*implementation* ("in one directory") two different predicates — and the gap between them
is exactly where a notification channel does not fit.

A webhook is not a market data source. Putting it through ``providers/router.py`` would mean
inventing a ``Dataset`` for 「一条飞书消息」, so the outbound POST would be routed, failed
over and **cached** by machinery built for 腾讯/新浪/东财.

⭐ **Which is the actual danger, and it is easy to miss:** a notification that gets
deduplicated by a data cache is a *silently dropped reminder*. It looks exactly like
「reusing a good mechanism already in the codebase」, and no reviewer will flag it.

So the rule was changed — and **tightened**: the set of files allowed to construct a client
goes from *every* ``.py`` under ``providers/`` (four today, more later) to **exactly this
one**. ``providers/sources.py`` no longer constructs one; it calls :func:`build_client`.

## What is shared, and what is deliberately not

Constitution §7.8 lists what the entry point should carry: 串行化 · 最小间隔 · 随机抖动 ·
会话复用 · 默认 UA · 熔断 · 缓存.

⭐ **This module owns three of those seven, and the other four stay in the market-data path
because they do not transfer.** The table that decided it is in ADR-0031; the one line that
matters most:

| | 行情 | webhook |
|---|---|---|
| UA | must **disguise** as a browser (sources reject unknown agents) | must **not** disguise |
| 缓存 | required | ⭐ **harmful** — a notification must be delivered every time |

## ⭐ `user_agent` is required, not defaulted

A default is a decision somebody will not revisit. The market-data path needs
``Mozilla/5.0 (compatible; ...)`` or the source refuses it; a webhook must say what it is.
There is no value that is right for both, so there is no default — ⭐ and a caller that
genuinely has no opinion now gets a ``TypeError`` at import-time review rather than a
wrong header in production.

## What is not here, on purpose

* **No cache, no circuit breaker, no jitter, no serialisation.** Those are the market-data
  path's, and :mod:`alphacouncil.providers.router` already has them. Re-implementing them
  here would give the two paths a second definition each — the defect in
  ``regressions/0010``, one layer over.
* **No retry policy.** ⭐ Retrying is a product decision (a lesson card must not be mailed
  twice — see ``notify/email.py``'s note on ``quit``), so it belongs to the caller.
"""

from __future__ import annotations

import httpx

__all__ = ["DEFAULT_TIMEOUT", "build_client"]

#: Seconds. ⭐ One value, because a second timeout is a second place to change it.
DEFAULT_TIMEOUT = 10.0


def build_client(
    *,
    user_agent: str,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Client:
    """Build an HTTP client with this project's shared connection policy.

    :param user_agent: ⭐ **Required, and it must be chosen, not inherited.** Market data
        sources reject agents they do not recognise, so the provider path passes a browser
        string. A webhook must announce itself honestly. See the module docstring.
    :param headers: Extra headers, merged over ``{"User-Agent": user_agent}``.
    :param timeout: Seconds. Defaults to :data:`DEFAULT_TIMEOUT`.
    :returns: A client with ``follow_redirects`` on, so a redirected data source behaves
        the same as a direct one. ⭐ Redirects are followed, never re-checked: a source
        that redirects somewhere unexpected is a finding, not something to resolve
        silently.
    """
    merged = {"User-Agent": user_agent}
    if headers:
        merged.update(headers)
    return httpx.Client(timeout=timeout, headers=merged, follow_redirects=True)
