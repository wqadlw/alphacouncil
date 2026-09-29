/**
 * Candlesticks with volume, for 「现在是什么样」 (spec 034).
 *
 * ## `stale` is a flag, and getting that wrong hides a sentence
 *
 * The first draft branched on `series.status === 'stale'`. ⭐ There is no such status:
 * `DataStatus` is `'ok' | 'no_data' | 'error' | 'unavailable'`, and `stale` is a boolean on
 * an `ok` result. So that branch was unreachable and the sentence 「这是上次拿到的数据」
 * could never appear — ⭐ **the one case where the reader most needs telling was the case
 * the code could not name.**
 *
 * Which is the real argument for reusing `DataResult`'s shape rather than inventing one: an
 * invented union has no member to reject a wrong idea, and the wrong idea then type-checks.
 *
 * ## What it draws, and what it refuses to draw
 *
 * Four states and no fifth. ⭐ **An empty chart is the dangerous option** — it looks like
 * 「这只票没有历史」 when the truth may be 「今天三个源都在熔断」, and those point at
 * different next steps. `no_data` and `error` are therefore rendered apart, following the
 * endpoint's own argument: 「所有源都拒绝了」 is worth retrying, 「这个代码不是数据源报价的
 * 东西」 is not.
 *
 * A stale series is **drawn and labelled**, not hidden — the bars are true, and hiding them
 * would discard information the reader asked for while pretending to be careful.
 *
 * ## The library API here is v3-style, and that was checked
 *
 * `lightweight-charts@4.2.0` exposes `addCandlestickSeries` / `addHistogramSeries`;
 * `addSeries` and the `CandlestickSeries` definition-object API are **v5** and appear
 * **zero** times in 4.2.0's typings. Written from memory they would have type-checked
 * against nothing and drawn nothing.
 */

import { useEffect, useRef } from 'react'
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
} from 'lightweight-charts'

import type { DailyResult } from '../../api'

/** A-series in CNY: up is red, down is green, as the mainland convention has it. */
const UP = '#c0392b'
const DOWN = '#1e8449'

export interface KlineChartProps {
  result: DailyResult
}

/** One message per state, and each says what it means for the reader. */
function StateNotice({ title, detail }: { title: string; detail: string }) {
  return (
    <div data-testid="kline-state" className="rounded-[4px] border border-[color:var(--color-line)] p-4">
      <p className="text-[13px] text-ink-soft">{title}</p>
      <p className="text-[12px] text-ink-faint">{detail}</p>
    </div>
  )
}

export function KlineChart({ result }: KlineChartProps) {
  const host = useRef<HTMLDivElement | null>(null)
  const bars = result.status === 'ok' ? (result.value ?? []) : []

  useEffect(() => {
    const element = host.current
    if (element === null || bars.length === 0) {
      return undefined
    }

    const chart: IChartApi = createChart(element, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#8a8f98',
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(138, 143, 152, 0.16)', style: LineStyle.Solid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, rightOffset: 4 },
      width: element.clientWidth,
      height: 320,
    })

    const candles = chart.addCandlestickSeries({
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    })
    candles.setData(
      bars.map((bar) => ({
        time: bar.trade_date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    )

    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    // ⭐ Volume overlays the candles rather than taking its own pane: in a 320px chart a
    // second pane would be mostly volume.
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    volume.setData(
      bars.map((bar) => ({
        time: bar.trade_date,
        value: bar.volume,
        color:
          bar.close >= bar.open ? 'rgba(192, 57, 43, 0.5)' : 'rgba(30, 132, 73, 0.5)',
      })),
    )

    chart.timeScale().fitContent()

    // ⭐ A chart that does not follow its container is a chart that lies about its width.
    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: element.clientWidth })
    })
    observer.observe(element)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [bars])

  if (result.status === 'no_data') {
    return (
      <StateNotice
        title="没有数据源报这个代码"
        detail="这不是「这只票没有历史」—— 是数据源不报它。换一个代码试试。"
      />
    )
  }
  if (result.status === 'error' || result.status === 'unavailable') {
    return (
      <StateNotice
        title="所有已知数据源都拒绝了"
        detail="这一条值得重试：过一会儿再按一次，或换一个源。"
      />
    )
  }
  if (bars.length === 0) {
    return (
      <StateNotice
        title="这段时间没有交易"
        detail="数据源答了，答案是空的 —— 这是区间的性质，不是这只票的性质。"
      />
    )
  }

  return (
    <div>
      {result.stale && (
        <p data-testid="kline-stale" className="text-[12px] text-[color:var(--color-up)]">
          ⭐ 数据源此刻拿不到，下面是缓存里那一份
          {result.fetched_at ? `（${result.fetched_at}）` : ''}。
        </p>
      )}
      <div ref={host} data-testid="kline-chart" />
      <p className="text-[12px] text-ink-faint" data-testid="kline-caption">
        {bars.length} 根日线 · {bars[0].trade_date} 至 {bars[bars.length - 1].trade_date}
        {result.source ? ` · 来源 ${result.source}` : ''} · 前复权口径 · 成交量单位为股，
        成交额该源不提供
      </p>
    </div>
  )
}
