/**
 * Turning server-computed indicators into chart points (spec 038).
 *
 * ## Why this is a module and not three helpers inside the component
 *
 * ⭐ The whole design rests on `values[i]` meaning **bar `i`** — the server sends one entry
 * per bar, `null` where the indicator does not exist yet, precisely so that nobody has to
 * infer the correspondence. If that correspondence is off by one the line shifts in time by
 * one trading day, the chart still renders, the tests on the server still pass, and the
 * error is **invisible to everything except a reader who checks a number against a known
 * value.** So the alignment is the one piece of this feature worth a test, and code that
 * cannot be imported cannot be tested.
 *
 * ## Why no arithmetic happens here
 *
 * The indicators are computed server-side, in ``spec 037``'s single Python implementation.
 * A `sma()` in TypeScript would be a second definition of the same thing, and the two would
 * agree until the day one of them was edited. So there is no division, no subtraction and
 * no window anywhere in this file — it moves values from index space to chart space and
 * nothing else. ⭐ **If a future change adds arithmetic here, that is the bug, not the
 * feature.**
 *
 * ## One table decides colour and pane together
 *
 * ⭐ The first draft had a `SERIES_COLOR` record and two parallel id arrays, and a `??`
 * fallback colour for anything unrecognised. That combination was wrong in a way worth
 * recording: a name in neither list was **dropped from the chart but still listed in the
 * legend**, because the legend rendered `indicators` rather than what was drawn. The
 * reader would see a labelled swatch with no line under it — ⭐ an indicator that appears
 * computed and is not. A fallback colour was never the answer; the fallback colour was
 * papering over the fact that dropping is a decision someone has to be told about.
 *
 * So: one table, no fallback, and ``unplaced`` returned so the component can say how many
 * series arrived that this page does not draw. Silence is the one option not on the table.
 */

import type { DailyBar, IndicatorSeries } from '../../api'

/** Which pane a series belongs to, and what colour it is drawn in. */
export type Pane = 'overlay' | 'pane'

interface Placement {
  pane: Pane
  color: string
}

/**
 * ⭐ The single source of truth for what this page draws.
 *
 * A colour and a pane live together because they change together: adding an indicator
 * means adding a row here, and forgetting the pane is no longer expressible. The two keys
 * the component must not get wrong are the two that are easy to confuse — `histogram` is a
 * **bar** on the price-pane side of the legend, not a line, which is why the component
 * branches on it by name.
 *
 * ⭐ **All four line colours are distinct, and the first draft had two.** DIF reused
 * `ma20`'s navy and DEA reused `ema12`'s brass, so the legend read
 * 「MA20 EMA12 DIF DEA」 with two colours in it — ⭐ and a legend the reader cannot use to
 * tell two marks apart is not a legend, it is a list. Being on separate panes does not
 * rescue it, because the legend is one row and the reader reads across it.
 *
 * The pair for the indicator pane is drawn from what the design system already has, and
 * deliberately leaves red and green alone: those two mean 涨 and 跌, and spending them on
 * an oscillator would make the page say 「涨」 where it means 「正」.
 */
const PLACED: Record<string, Placement> = {
  ma20: { pane: 'overlay', color: '#1e3a5f' },
  ema12: { pane: 'overlay', color: '#9a7b4f' },
  dif: { pane: 'pane', color: '#b4690e' },
  dea: { pane: 'pane', color: '#7a8797' },
  histogram: { pane: 'pane', color: '#c0392b' },
}

export interface IndicatorPoints {
  time: string
  value: number
}

export interface PlacedSeries extends IndicatorSeries {
  color: string
  /** The pane it goes in, resolved once here rather than twice in the component. */
  pane: Pane
}

export interface SplitIndicators {
  /** Drawn on top of the candles. */
  overlay: PlacedSeries[]
  /** Drawn in the separate indicator pane below. */
  pane: PlacedSeries[]
  /** ⭐ Arrived from the server, and this page does not draw them. */
  unplaced: IndicatorSeries[]
}

/**
 * The points for one line series, warm-up dropped.
 *
 * ⭐ The `null`s are dropped rather than drawn as gaps, and that is only correct because
 * they are a **prefix**: `sma`, `ema` and `macd` all return `None` until their period is
 * satisfied and never again. Nothing here checks that, and a future indicator that went
 * nullable mid-series would silently draw a straight line across the hole. The date always
 * comes from the bar, never from a counter kept here, so a misaligned *series* shows up as
 * a short line — visible — instead of a shifted one.
 */
export function linePoints(series: IndicatorSeries, bars: DailyBar[]): IndicatorPoints[] {
  const points: IndicatorPoints[] = []
  series.values.forEach((value, index) => {
    const bar = bars[index]
    if (value !== null && bar !== undefined) {
      points.push({ time: bar.trade_date, value })
    }
  })
  return points
}

/**
 * The same points, coloured by sign.
 *
 * ⭐ The MACD 柱 is a signed difference, so it takes the A-share colouring for the same
 * reason the candles do: positive is red. It is the one series whose fill has to be decided
 * per point, and deciding it in one place is what keeps it from drifting into a second
 * definition of 「涨」.
 */
export function histogramPoints(
  series: IndicatorSeries,
  bars: DailyBar[],
  colors: { positive: string; negative: string },
): { time: string; value: number; color: string }[] {
  const points: { time: string; value: number; color: string }[] = []
  series.values.forEach((value, index) => {
    const bar = bars[index]
    if (value === null || bar === undefined) {
      return
    }
    points.push({
      time: bar.trade_date,
      value,
      color: value >= 0 ? colors.positive : colors.negative,
    })
  })
  return points
}

/**
 * Sort the server's series into the two panes, and report whatever is left over.
 *
 * ⭐ Split by `name`, not by index: the server chooses the set and its order, and a
 * positional read would put `dif` on the price chart the day someone reordered the list to
 * put `histogram` last — a MACD line drawn at a price of 300, which is not wrong-looking
 * enough to be noticed.
 */
export function splitIndicators(indicators: IndicatorSeries[]): SplitIndicators {
  const overlay: PlacedSeries[] = []
  const pane: PlacedSeries[] = []
  const unplaced: IndicatorSeries[] = []
  for (const item of indicators) {
    const placement = PLACED[item.name]
    if (placement === undefined) {
      unplaced.push(item)
    } else {
      ;(placement.pane === 'overlay' ? overlay : pane).push({ ...item, ...placement })
    }
  }
  return { overlay, pane, unplaced }
}
