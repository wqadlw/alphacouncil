import { describe, expect, it } from 'vitest'
import type { DailyBar, IndicatorSeries } from '../../api'
import { histogramPoints, linePoints, splitIndicators } from './indicatorOverlay'

/** `count` bars on consecutive days, ascending. Dates only have to be ordered. */
function bars(count: number): DailyBar[] {
  return Array.from({ length: count }, (_, index) => ({
    symbol: { market: 'cn', code: '600519' },
    trade_date: `2026-01-${String(index + 1).padStart(2, '0')}`,
    open: 100 + index,
    high: 101 + index,
    low: 99 + index,
    close: 100 + index,
    volume: 1000,
    amount: null,
    // Declared in api.ts and unread on the page; carried here because a fixture that
    // omits a wire field is exactly what S-18 (spec 053) now reports on the backend side.
    adj_factor: 1,
    fetched_at: '2026-01-02T00:00:00Z',
    source: 'tencent',
  }))
}

function series(name: string, values: (number | null)[], label = name): IndicatorSeries {
  return { name, label, values }
}

describe('linePoints', () => {
  // ⭐ This is the test that earns the whole 「one entry per bar」 design. An off-by-one
  // here shifts a line one trading day into the past; the chart renders, the server's own
  // tests pass, and nothing else in the system can see it.
  it('pairs each value with the bar at the same index, warm-up and all', () => {
    const rows = bars(5)
    const points = linePoints(series('ma20', [null, null, 3, 4, 5]), rows)

    expect(points).toEqual([
      { time: '2026-01-03', value: 3 },
      { time: '2026-01-04', value: 4 },
      { time: '2026-01-05', value: 5 },
    ])
  })

  it('keeps values and bars aligned even when a bar is missing in the middle', () => {
    // ⭐ The date comes from `bars[index]`, never from a counter. So a short `values`
    // array truncates the line — visibly — instead of sliding it sideways. This test is
    // the difference between a bug you can see and a bug you argue about.
    const points = linePoints(series('ma20', [1, 2]), bars(5))

    expect(points.map((point) => point.time)).toEqual(['2026-01-01', '2026-01-02'])
  })

  it('returns nothing for a series that is entirely warm-up', () => {
    expect(linePoints(series('ma20', [null, null]), bars(2))).toEqual([])
  })

  it('does not invent bars when the values array is longer than the bars', () => {
    const points = linePoints(series('ma20', [1, 2, 3, 4]), bars(2))

    expect(points).toHaveLength(2)
  })

  it('passes through zero, which is a value and not an absence', () => {
    // ⭐ A MACD 柱 sitting exactly on zero is common and means something. A truthiness
    // check would drop it and the histogram would show a gap exactly where the trend
    // turned.
    expect(linePoints(series('dif', [0, 1]), bars(2))).toEqual([
      { time: '2026-01-01', value: 0 },
      { time: '2026-01-02', value: 1 },
    ])
  })
})

describe('histogramPoints', () => {
  const COLORS = { positive: 'red', negative: 'green' }

  it('colours by sign, using positive for exactly zero', () => {
    // ⭐ Zero is neither, and 「not negative」 is the only rule that keeps the 柱 from
    // flickering between two colours as it decays toward the axis.
    const points = histogramPoints(series('histogram', [-1, 0, 1]), bars(3), COLORS)

    expect(points.map((point) => point.color)).toEqual(['green', 'red', 'red'])
  })

  it('uses the same alignment as the lines', () => {
    const points = histogramPoints(series('histogram', [null, 2]), bars(3), COLORS)

    expect(points).toEqual([{ time: '2026-01-02', value: 2, color: 'red' }])
  })
})

describe('splitIndicators', () => {
  const all = [
    series('ma20', [1], 'MA20'),
    series('dif', [2], 'DIF'),
    series('histogram', [3], 'MACD 柱'),
    series('ema12', [4], 'EMA12'),
  ]

  it('sorts by name, so a reordering on the server cannot move a line to the wrong pane', () => {
    // ⭐ Reordered on purpose: `dif` is third here. A positional read would put it with
    // the candles, and a MACD value on a price axis looks like a price.
    const { overlay, pane } = splitIndicators(all)

    expect(overlay.map((item) => item.name)).toEqual(['ma20', 'ema12'])
    expect(pane.map((item) => item.name)).toEqual(['dif', 'histogram'])
  })

  it('carries the colour and pane onto each series', () => {
    const { overlay, pane } = splitIndicators(all)

    expect(overlay[0].color).toBeTruthy()
    expect(overlay[0].pane).toBe('overlay')
    expect(pane[1].pane).toBe('pane')
  })

  it('reports what it could not place instead of dropping it quietly', () => {
    // ⭐ The whole point of `unplaced`: an indicator the server added and this page does
    // not know about has to be **named on screen**. Dropping it silently would make the
    // legend and the chart disagree, and a legend entry with no line under it is a claim
    // the picture does not support.
    const { overlay, pane, unplaced } = splitIndicators([...all, series('rsi14', [5], 'RSI14')])

    expect(overlay).toHaveLength(2)
    expect(pane).toHaveLength(2)
    expect(unplaced.map((item) => item.label)).toEqual(['RSI14'])
  })

  it('returns three empty lists for no indicators at all', () => {
    // ⭐ A short window yields no series server-side, and that is a fact about the data
    // rather than a failure — the chart has to be able to say so.
    expect(splitIndicators([])).toEqual({ overlay: [], pane: [], unplaced: [] })
  })
})
