/**
 * Candlesticks with volume and indicators, for 「现在是什么样」 (spec 034, extended by 038).
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
 *
 * ## MACD gets a second chart, because 4.2.0 has no second pane
 *
 * ⭐ `paneIndex` and `addPane` appear **zero** times in 4.2.0's typings — multiple panes
 * arrived in v5. The two obvious workarounds are both bad: overlaying MACD on the price
 * scale hides it entirely (a MACD of ±8 against a 300 CNY stock is a flat line), and giving
 * it an overlay scale puts a second number next to the price where it reads as a second
 * price. So the indicator pane is a **separate chart instance** sharing a time range, and
 * the two are wired together in `useEffect` — ⭐ which is the only part of this file where
 * two things must agree and nothing forces them to.
 *
 * ## The indicators arrive computed, or this file would be a second opinion
 *
 * Spec 038's ruling: the server computes. A client-side `sma()` would be a second
 * implementation of a definition that ``spec 037`` pinned down in six places, and the two
 * would agree until the day one of them was edited. So this file never derives a number —
 * it only aligns, colours and labels. The `null`s in `values` are dropped rather than
 * plotted, which is safe ⭐ **only** because they are a warm-up prefix: `sma`/`ema`/`macd`
 * return `None` until their period is satisfied and never again. Nothing here depends on
 * that being true, though, and a future indicator that goes nullable in the middle would
 * silently draw a line across the hole.
 */

import { useEffect, useMemo, useRef } from 'react'
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type LogicalRange,
  type Time,
} from 'lightweight-charts'

import type { DailyBar, DailyResult, IndicatorSeries } from '../../api'
import { histogramPoints, linePoints, splitIndicators } from './indicatorOverlay'
import type { PlacedSeries } from './indicatorOverlay'

/** A-series in CNY: up is red, down is green, as the mainland convention has it. */
const UP = '#c0392b'
const DOWN = '#1e8449'
const GRID = 'rgba(138, 143, 152, 0.16)'
const AXIS_TEXT = '#8a8f98'
/** The MACD 柱's two fills, the same hues as `UP`/`DOWN` at lower opacity. */
const HIST = { positive: 'rgba(192, 57, 43, 0.55)', negative: 'rgba(30, 132, 73, 0.55)' }

/**
 * ⭐ A shared empty array, so a result with no series does not hand the effect a new
 * `[]` on every render. Identity is what `useEffect` compares, and a `?? []` inline
 * would rebuild the charts on every keystroke anywhere above this component.
 */
const NO_BARS: DailyBar[] = []
const NO_INDICATORS: IndicatorSeries[] = []

export interface KlineChartProps {
  result: DailyResult
}

/** One message per state, and each says what it means for the reader. */
function StateNotice({ title, detail }: { title: string; detail: string }) {
  return (
    <div
      data-testid="kline-state"
      className="rounded-[4px] border border-[color:var(--color-rule-soft)] p-4"
    >
      <p className="text-[13px] text-ink-soft">{title}</p>
      <p className="text-[12px] text-ink-faint">{detail}</p>
    </div>
  )
}

/** The chart options both instances share, so the panes cannot drift apart visually. */
function commonOptions(width: number, height: number) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' } as const,
      textColor: AXIS_TEXT,
      attributionLogo: false,
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { color: GRID, style: LineStyle.Solid },
    },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, rightOffset: 4 },
    width,
    height,
  }
}

/**
 * The legend, and it names **only what was drawn**.
 *
 * ⭐ Rendered from `[...overlay, ...pane]` rather than from the server's list on purpose.
 * Listing everything the server sent is how a series ends up labelled on a chart where no
 * line was drawn — a legend that says 「RSI」 under a chart with no RSI in it is a claim the
 * picture does not support, and it is exactly the kind of lie that survives review because
 * every individual part is true.
 */
function Legend({
  overlay,
  pane,
}: {
  overlay: PlacedSeries[]
  pane: PlacedSeries[]
}) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1" data-testid="kline-legend">
      {[...overlay, ...pane].map((item) => (
        <li key={item.name} className="flex items-center gap-1.5">
          {/* ⭐ A 柱 is a block, not a line, and it is two colours — a single-hue swatch
              would name a mark the picture never draws. Half red, half green, in the
              order the series reads. Being right about shape and hue is most of what a
              legend is for. */}
          {item.name === 'histogram' ? (
            <span aria-hidden="true" className="inline-flex h-[9px] w-[6px]">
              <span className="w-1/2" style={{ background: HIST.positive }} />
              <span className="w-1/2" style={{ background: HIST.negative }} />
            </span>
          ) : (
            <span
              aria-hidden="true"
              className="inline-block h-[2px] w-4"
              style={{ background: item.color }}
            />
          )}
          <span className="text-[12px] text-ink-faint">{item.label}</span>
        </li>
      ))}
    </ul>
  )
}

export function KlineChart({ result }: KlineChartProps) {
  const host = useRef<HTMLDivElement | null>(null)
  const paneHost = useRef<HTMLDivElement | null>(null)
  const series = result.value
  const bars = series?.bars ?? NO_BARS
  const indicators = series?.indicators ?? NO_INDICATORS
  // ⭐ Memoised because these are the effect's dependencies — `splitIndicators` returns new
  // arrays every call, and an unmemoised result tears down and rebuilds both charts on
  // every render of the page. That is not a performance complaint; it is a chart that
  // flickers, and a legend that re-mounts while the reader is reading it.
  const { overlay, pane, unplaced } = useMemo(
    () => splitIndicators(indicators),
    [indicators],
  )

  useEffect(() => {
    const element = host.current
    if (element === null || bars.length === 0) {
      return undefined
    }

    const chart: IChartApi = createChart(element, {
      ...commonOptions(element.clientWidth, 320),
      crosshair: { mode: CrosshairMode.Normal },
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
        time: bar.trade_date as Time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    )

    for (const item of overlay) {
      const points = linePoints(item, bars)
      if (points.length > 0) {
        const line = chart.addLineSeries({
          color: item.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        line.setData(points)
      }
    }

    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    // ⭐ Volume overlays the candles rather than taking its own pane: in a 320px chart a
    // second pane would be mostly volume. 4.2.0 has no real panes — see the header.
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    volume.setData(
      bars.map((bar) => ({
        time: bar.trade_date as Time,
        value: bar.volume,
        color:
          bar.close >= bar.open ? 'rgba(192, 57, 43, 0.5)' : 'rgba(30, 132, 73, 0.5)',
      })),
    )

    chart.timeScale().fitContent()

    // ⭐ The MACD pane is a second chart that must show the same dates. Nothing in the
    // library links them in 4.2.0, so this is the whole mechanism — and the guard flag is
    // not optional: `setVisibleLogicalRange` re-enters the handler, and without it the two
    // charts would hand the range back and forth until the stack gave out.
    const paneElement = paneHost.current
    let macd: IChartApi | null = null
    if (paneElement !== null && pane.length > 0) {
      macd = createChart(paneElement, { ...commonOptions(paneElement.clientWidth, 120) })
      for (const item of pane) {
        if (item.name === 'histogram') {
          // ⭐ The MACD 柱 is a signed difference, so it takes the A-share colouring by
          // sign — the same convention as the candles, for the same reason.
          const hist = macd.addHistogramSeries({ priceLineVisible: false })
          hist.setData(histogramPoints(item, bars, HIST))
        } else {
          const points = linePoints(item, bars)
          if (points.length === 0) {
            continue
          }
          const line = macd.addLineSeries({
            color: item.color,
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          })
          line.setData(points)
        }
      }
    }

    let syncing = false
    const link = (target: IChartApi | null) => (range: LogicalRange | null) => {
      if (syncing || target === null || range === null) {
        return
      }
      syncing = true
      target.timeScale().setVisibleLogicalRange(range)
      syncing = false
    }
    chart.timeScale().subscribeVisibleLogicalRangeChange(link(macd))
    if (macd !== null) {
      macd.timeScale().subscribeVisibleLogicalRangeChange(link(chart))
      // ⭐ **This is why the link has to exist, not just niceness.** Each chart fits its
      // own data on load, and the two do not cover the same span: the candles start at
      // bar 0, while `dif`/`dea`/`histogram` are `null` until their warm-up ends. So
      // left alone the pane would open ~33 bars later than the chart above it and the
      // two would disagree about which date is under the cursor. Copying the main range
      // across is what makes 「同一时间轴」 true rather than a claim.
      const initial = chart.timeScale().getVisibleLogicalRange()
      if (initial !== null) {
        macd.timeScale().setVisibleLogicalRange(initial)
      }
    }

    // ⭐ A chart that does not follow its container is a chart that lies about its width.
    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: element.clientWidth })
      if (paneElement !== null && macd !== null) {
        macd.applyOptions({ width: paneElement.clientWidth })
      }
    })
    observer.observe(element)
    if (paneElement !== null) {
      observer.observe(paneElement)
    }

    return () => {
      observer.disconnect()
      macd?.remove()
      chart.remove()
    }
  }, [bars, overlay, pane])

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
      {(overlay.length > 0 || pane.length > 0) && <Legend overlay={overlay} pane={pane} />}
      {pane.length > 0 && (
        <>
          <div ref={paneHost} data-testid="kline-indicator-pane" />
          <p className="text-[11px] text-ink-faint" data-testid="kline-pane-caption">
            ⭐ MACD 12/26/9，与上图同一时间轴
          </p>
        </>
      )}
      {indicators.length === 0 && (
        <p className="text-[12px] text-ink-faint" data-testid="kline-no-indicators">
          ⭐ 这 {bars.length} 根日线不够算任何一条指标 —— 每条指标都有预热段，比这更短的
          区间算不出它。数据本身是全的。
        </p>
      )}
      {unplaced.length > 0 && (
        <p className="text-[12px] text-ink-faint" data-testid="kline-unplaced">
          ⭐ 服务端算了 {indicators.length} 条指标，本页只画 {overlay.length + pane.length}{' '}
          条；未画的是 {unplaced.map((item) => item.label).join('、')}。图例里没有它们，
          因为图例只列画出来的东西。
        </p>
      )}
      <p className="text-[12px] text-ink-faint" data-testid="kline-caption">
        {bars.length} 根日线 · {bars[0].trade_date} 至 {bars[bars.length - 1].trade_date}
        {result.source ? ` · 来源 ${result.source}` : ''} · 前复权口径 · 成交量单位为股，
        成交额该源不提供
      </p>
    </div>
  )
}
