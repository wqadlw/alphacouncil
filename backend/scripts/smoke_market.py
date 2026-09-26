"""Live smoke test for the data layer. Not part of the unit suite — this one
really does hit the network, which is exactly why it is separate.
"""

from __future__ import annotations

from datetime import date

from alphacouncil.models.market import Market, Symbol
from alphacouncil.providers import default_router

router = default_router()
moutai = Symbol(market=Market.SH, code="600519")

print("usable datasets:", sorted(d.value for d in router.usable_datasets(moutai)))

snap = router.get_realtime(moutai)
print("\n[realtime]")
print("  status :", snap.status.value, "| stale:", snap.stale)
print("  source :", snap.source)
if snap.value is not None:
    q = snap.value
    print(f"  price  : {q.price}")
    print(f"  change : {q.change_pct:+.4%}  (decimal fraction)")
    print(f"  ohlc   : {q.open} / {q.high} / {q.low}")
    print(f"  volume : {q.volume:,.0f} shares")
    print(f"  amount : {q.amount:,.0f} CNY")
else:
    print("  reason :", snap.reason, snap.error_code)

daily = router.get_daily(moutai, start=date(2026, 9, 18), end=date(2026, 9, 26))
print("\n[daily 2026-09-18 .. 2026-09-26]")
print("  status :", daily.status.value, "| stale:", daily.stale)
print("  source :", daily.source)
if daily.value:
    for bar in daily.value:
        amount = "None" if bar.amount is None else f"{bar.amount:,.0f}"
        print(
            f"  {bar.trade_date}  O{bar.open} H{bar.high} L{bar.low} C{bar.close}"
            f"  V{bar.volume:,.0f}  A{amount}"
        )
else:
    print("  reason :", daily.reason, daily.error_code)

# A venue no source claims — must degrade honestly, not invent a request.
bj = Symbol(market=Market.BJ, code="430047")
missing = router.get_realtime(bj)
print("\n[unsupported venue BJ]")
print("  status :", missing.status.value, "| code:", missing.error_code)
