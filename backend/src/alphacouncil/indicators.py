"""Technical indicators over adjusted daily bars (spec 037).

Pure functions, no I/O, no framework. Every series is the same length as its input and
every immature window is ``None`` rather than a number.

---

## ⭐ Why every immature value is ``None``, and never ``0``

Constitution 红线 6 requires an immature result to render **blank**, and ``S-08``
(``immature_outcome_blank``) enforces it in the UI. That rule reaches all the way down
here: a 20-day moving average over 5 bars has no value, and the two tempting substitutes
are both lies.

* ``0`` says 「the average price was zero」.
* **Carrying the partial mean forward** is worse, because it looks like a real number and
  a chart will draw it. ⭐ A ``MA20`` drawn from 5 bars is a line through the present that
  the reader will believe.

So the type carries the absence: ``float | None``, and the API layer is what renders blank.

## ⭐ The caliber forks, each stated rather than inherited

Indicators are mostly standard, and 「standard」 is where the disagreements live. Each of
these is a place where two correct-looking implementations give different numbers:

* **EMA is recursive** (``alpha = 2/(n+1)``, seeded from an SMA). ⭐ TSP writes
  ``ewm(adjust=False)`` 14 times in its ``pipeline.py`` — the *non*-default, because the
  pandas default ``adjust=True`` is a different, equally defensible function. The fork is
  real and it moves every MACD number.
* **RSI uses Wilder's smoothing**, not a simple mean of gains and losses. Wilder's is an
  RMA (``alpha = 1/n``); a simple mean is a different indicator with the same name.
* **KDJ's ``RSV`` uses the window high/low**, so its denominators change per bar, and
  a flat window makes it undefined. It is smoothed by SMA rather than by EMA.
* **ATR is Wilder-smoothed** over true range, and true range needs the **previous close**,
  so its first value cannot exist.
* **Bollinger bands** are ±k standard deviations of a moving mean; whether that mean is an
  SMA changes the bands, and the default here is SMA.
* **Annualised volatility** multiplies by ``sqrt(252)``, and 252 is A-shares' trading days
  per year — ⭐ stated because 250 and 240 are also in circulation and produce a 1%
  difference nobody would notice and everybody would quote.

## Adjustment basis

Every function here consumes bars as they are stored, which are **forward-adjusted**
(``adj_factor`` is part of the bar). ⭐ That is constitution 4.2's second of four
non-interchangeable units, and it is why a moving average computed here can be compared
with one computed on raw prices and differ — which is the point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: A value that may not exist yet. ⭐ ``None`` means 「this window has not closed」 and is
#: never a placeholder for zero.
Indicator = float | None

#: A-shares trade 252 days a year. ⭐ Named, not inlined: 250 and 240 are also in
#: circulation, and the ~1% difference is the kind nobody notices and everybody quotes.
TRADING_DAYS_PER_YEAR = 252


def sma(values: Sequence[float], period: int) -> list[Indicator]:
    """Simple moving average, trailing, aligned to the input.

    ``result[i]`` is the mean of ``values[i - period + 1 : i + 1]``, or ``None`` until
    there are ``period`` of them.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    out: list[Indicator] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        out.append(running / period if index >= period - 1 else None)
    return out


def ema(values: Sequence[float], period: int) -> list[Indicator]:
    """Recursive exponential moving average — ``adjust=False`` semantics.

    ⭐ Seeded with the SMA of the first ``period`` values, then
    ``ema = alpha * price + (1 - alpha) * previous`` with ``alpha = 2 / (period + 1)``.

    This is the fork TSP encodes as ``ewm(adjust=False)``. The pandas default
    ``adjust=True`` weights the whole history instead, so it produces different numbers
    from the very first bar — ⭐ same name, same length, different series, and no warning.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    out: list[Indicator] = []
    alpha = 2.0 / (period + 1.0)
    seed: list[float] = []
    previous: Indicator = None
    for value in values:
        if previous is None:
            seed.append(value)
            if len(seed) < period:
                out.append(None)
                continue
            previous = sum(seed) / period
            out.append(previous)
            continue
        previous = alpha * value + (1.0 - alpha) * previous
        out.append(previous)
    return out


def rma(values: Sequence[float], period: int) -> list[Indicator]:
    """Wilder's smoothing — ``alpha = 1 / period``, seeded with an SMA.

    ⭐ Not the same as :func:`ema`. RSI and ATR both use this one; confusing the two is a
    common source of an RSI that disagrees with every platform by a percent or two.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    out: list[Indicator] = []
    alpha = 1.0 / period
    seed: list[float] = []
    previous: Indicator = None
    for value in values:
        if previous is None:
            seed.append(value)
            if len(seed) < period:
                out.append(None)
                continue
            previous = sum(seed) / period
            out.append(previous)
            continue
        previous = alpha * value + (1.0 - alpha) * previous
        out.append(previous)
    return out


def _gains_losses(closes: Sequence[float]) -> tuple[list[float], list[float]]:
    """Per-bar gain and loss. The first bar has neither, so it starts empty."""
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    return gains, losses


@dataclass(frozen=True, slots=True)
class MacdRead:
    """MACD: the line, the signal, and the histogram.

    ⭐ One object rather than three parallel lists, because the three are read together and
    a caller holding three lists can pair them wrong by accident — and a wrong pairing
    still looks like plausible numbers.
    """

    dif: list[Indicator]
    dea: list[Indicator]
    histogram: list[Indicator]


def macd(
    closes: Sequence[float],
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MacdRead:
    """MACD over closing prices.

    ⭐ The signal (DEA) is ``ema`` applied to DIF, and it is written as a **call** rather
    than a second, hand-rolled recursion. The first draft inlined the EMA update with its
    own seed — the first available value, where ``ema`` seeds with a ``period``-bar SMA —
    so the file held two definitions of the same estimator that disagreed on every bar
    after the first, and the docstring described neither. ⭐ That is the 「一个教训只有一
    个家」 rule breaking in the one place it is hardest to see: inside a single file, where
    both definitions look local and reasonable.

    The seed is not a detail. It is why DEA's first ``signal - 1`` mature entries were
    ``None`` in the docstring and were **not** in the output; ``spec 038`` found the
    mismatch by counting non-nulls in a live response, after 34 passing tests.

    Aligned back to the input, so DEA's warm-up is the sum of both stages: ``slow - 1``
    bars for DIF plus ``signal - 1`` more for the EMA over it.
    """
    fast_line = ema(closes, fast)
    slow_line = ema(closes, slow)
    dif: list[Indicator] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(fast_line, slow_line, strict=True)
    ]

    # ⭐ `ema` is same-length by construction, so `[None] * warmup + smoothed` is exactly
    # as long as `dif` — the alignment ``spec 037`` requires, and the reason the histogram
    # below can zip with ``strict=True`` without a defensive check.
    mature = [value for value in dif if value is not None]
    # ⭐ The pad is its own annotated name because `[None] * n` infers as `list[None]`, and
    # `list` is invariant — so inlining it into the concatenation is a mypy error and the
    # obvious `list(Indicator)` spelling is not available on a literal. Naming the pad
    # states its type once instead of casting it twice.
    pad: list[Indicator] = [None] * (len(dif) - len(mature))
    dea: list[Indicator] = pad + ema(mature, signal)

    histogram: list[Indicator] = [
        (d - e) if d is not None and e is not None else None for d, e in zip(dif, dea, strict=True)
    ]
    return MacdRead(dif=dif, dea=dea, histogram=histogram)


@dataclass(frozen=True, slots=True)
class RsiRead:
    """Relative strength index. 0-100, and ``None`` until the window closes."""

    rsi: list[Indicator]


def rsi(closes: Sequence[float], period: int = 14) -> RsiRead:
    """Wilder's RSI.

    ⭐ Wilder's smoothing, not a simple mean. A flat series has no losses, so the loss
    average is ``0`` and the index is 100 — ⭐ which is a real answer here, not a division
    by zero: 「nothing fell」 is exactly what RSI 100 means.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    gains, losses = _gains_losses(closes)
    # One extra input bar is needed before the first change exists.
    padded: list[Indicator] = [None, *rma(gains, period)]
    loss_avg = [None, *rma(losses, period)]

    out: list[Indicator] = [None]
    for index in range(1, len(closes)):
        average_gain, average_loss = padded[index], loss_avg[index]
        if average_gain is None or average_loss is None:
            out.append(None)
            continue
        if average_loss == 0.0:
            out.append(100.0)
            continue
        relative = average_gain / average_loss
        out.append(100.0 - (100.0 / (1.0 + relative)))
    return RsiRead(rsi=out)


@dataclass(frozen=True, slots=True)
class KdjRead:
    """KDJ. ⭐ ``K`` and ``D`` are Wilder-free: RSV smoothed by SMA, per the convention."""

    k: list[Indicator]
    d: list[Indicator]
    j: list[Indicator]


def kdj(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
) -> KdjRead:
    """Stochastic KDJ.

    ⭐ The denominator is the window's own high minus its low, so it **changes每bar** — and
    a flat window gives ``0``, which is undefined rather than infinite. Such a bar yields
    ``None`` instead: ⭐ dividing by zero would produce an ``inf`` that a chart would draw
    as a spike off the top of the screen.
    """
    rsv: list[Indicator] = []
    for index in range(len(closes)):
        if index < period - 1:
            rsv.append(None)
            continue
        window_high = max(highs[index - period + 1 : index + 1])
        window_low = min(lows[index - period + 1 : index + 1])
        span = window_high - window_low
        rsv.append(None if span == 0 else (closes[index] - window_low) / span * 100.0)

    k_line = _smoothed_rsv(rsv, k_period)
    d_line = _smoothed_rsv(k_line, d_period)
    j_line: list[Indicator] = [
        (3 * k - 2 * d) if k is not None and d is not None else None
        for k, d in zip(k_line, d_line, strict=True)
    ]
    return KdjRead(k=k_line, d=d_line, j=j_line)


def _smoothed_rsv(values: list[Indicator], period: int) -> list[Indicator]:
    """SMA of an already-masked series, skipping the ``None`` prefix rather than
    averaging around it.

    ⭐ An SMA that treats ``None`` as zero would report a falling indicator during warm-up,
    which is the single most common way an indicator panel lies before it has data.
    """
    out: list[Indicator] = []
    window: list[float] = []
    for value in values:
        if value is None:
            out.append(None)
            continue
        window.append(value)
        if len(window) < period:
            out.append(None)
            continue
        out.append(sum(window[-period:]) / period)
    return out


@dataclass(frozen=True, slots=True)
class BollingerRead:
    """Bollinger bands: an SMA with standard deviations above and below it."""

    middle: list[Indicator]
    upper: list[Indicator]
    lower: list[Indicator]
    bandwidth: list[Indicator]


def bollinger(
    closes: Sequence[float], *, period: int = 20, deviations: float = 2.0
) -> BollingerRead:
    """Bollinger bands over an **SMA** middle (not an EMA — the fork, stated)."""
    middle = sma(closes, period)
    upper: list[Indicator] = []
    lower: list[Indicator] = []
    for index in range(len(closes)):
        if middle[index] is None:
            upper.append(None)
            lower.append(None)
            continue
        window = closes[index - period + 1 : index + 1]
        mean = middle[index]
        assert mean is not None
        variance = sum((value - mean) ** 2 for value in window) / period
        spread = deviations * variance**0.5
        upper.append(mean + spread)
        lower.append(mean - spread)
    return BollingerRead(
        middle=middle,
        upper=upper,
        lower=lower,
        bandwidth=_bandwidth(upper, middle, lower),
    )


def _bandwidth(
    upper: list[Indicator], middle: list[Indicator], lower: list[Indicator]
) -> list[Indicator]:
    """``(upper - lower) / middle`` — a squeeze indicator, so it needs its own line."""
    out: list[Indicator] = []
    for up, mid, low in zip(upper, middle, lower, strict=True):
        if up is None or mid is None or low is None or mid == 0:
            out.append(None)
            continue
        out.append((up - low) / mid)
    return out


def true_range(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> list[Indicator]:
    """True range, which needs the previous close.

    ⭐ The first bar has no previous close, so its true range is ``None`` — not
    ``high - low``, which would be the range of an unknown opening.
    """
    out: list[Indicator] = [None]
    for index in range(1, len(closes)):
        previous_close = closes[index - 1]
        out.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - previous_close),
                abs(lows[index] - previous_close),
            )
        )
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 14,
) -> list[Indicator]:
    """Average true range, Wilder-smoothed."""
    ranges = true_range(highs, lows, closes)
    return [None, *rma([value for value in ranges if value is not None], period)]


def annualised_volatility(closes: Sequence[float], *, period: int = 20) -> list[Indicator]:
    """Annualised standard deviation of log returns over a trailing window.

    ⭐ Log returns rather than percentage returns: compounding multiplies, and the
    volatility of a compounded series is not the compounding of volatilities.
    """
    returns: list[float] = [0.0]
    for index in range(1, len(closes)):
        returns.append(
            0.0 if closes[index - 1] == 0 else math_log(closes[index] / closes[index - 1])
        )
    out: list[Indicator] = []
    for index in range(len(closes)):
        if index < period:
            out.append(None)
            continue
        window = returns[index - period + 1 : index + 1]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        out.append(variance**0.5 * TRADING_DAYS_PER_YEAR**0.5)
    return out


def math_log(value: float) -> float:
    """``log`` under a name that cannot collide with the module being shadowed."""
    from math import log

    return log(value)


__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "BollingerRead",
    "Indicator",
    "KdjRead",
    "MacdRead",
    "RsiRead",
    "annualised_volatility",
    "atr",
    "bollinger",
    "ema",
    "kdj",
    "macd",
    "rma",
    "rsi",
    "sma",
    "true_range",
]
