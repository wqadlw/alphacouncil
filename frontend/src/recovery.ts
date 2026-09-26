/**
 * The arithmetic of a loss — red line 12, as numbers.
 *
 * "Cut your losses" is advice. "This position needs five years of gains to get
 * back to even" is a fact about the world, and the second one changes behaviour
 * because it converts a number the reader is emotionally attached to into a
 * number about their life. That conversion is the whole reason the stop-loss
 * prompt exists (`checks/rules/time_cost_in_stop_loss.py`, rule S-09).
 *
 * Pure arithmetic, no strings: the copy lives in the component, so this module
 * can be tested against maths instead of against wording.
 */

/** Losses as a fraction: `0.32` means down 32%. */
export type Fraction = number

/**
 * The annual rate the prompt assumes until the reader changes it.
 *
 * There is no correct value, which is why it is an **input on screen** rather
 * than a constant in here. A recovery estimate that hides its assumption is a
 * number pretending to be a fact.
 */
export const DEFAULT_ANNUAL_RATE = 0.15

/**
 * The gain required to undo a loss, as a fraction: 0.5 -> 1.0, i.e. +100%.
 *
 * `loss / (1 - loss)`. This is the asymmetry in one line — a 50% loss needs a
 * 100% gain, and a 90% loss needs 900% — and it is the reason "wait for it to
 * come back" is not symmetric with "it went down".
 */
export function gainNeeded(loss: Fraction): number {
  if (loss <= 0) return 0
  if (loss >= 1) return Number.POSITIVE_INFINITY
  return loss / (1 - loss)
}

/**
 * Years to get back to even, compounding at `annualRate`.
 *
 * `-ln(1 - loss) / ln(1 + annualRate)`. Compounded rather than the tempting
 * `loss / annualRate`: simple division understates the wait at every size
 * (a 50% loss at 15% looks like 3.3 years by division and is 5.0 in fact), and
 * this panel's entire job is to not understate it.
 *
 * Returns `Infinity` rather than throwing for inputs where recovery never
 * happens — a wiped-out position and a zero or negative assumed rate both land
 * there, and "never" is the true answer for both.
 */
export function yearsToRecover(loss: Fraction, annualRate: number = DEFAULT_ANNUAL_RATE): number {
  if (loss <= 0) return 0
  if (loss >= 1) return Number.POSITIVE_INFINITY
  if (!(annualRate > 0)) return Number.POSITIVE_INFINITY
  return -Math.log(1 - loss) / Math.log(1 + annualRate)
}

/** `0.15` -> `15%`. One decimal only when it carries information. */
export function formatRate(rate: number): string {
  const pct = rate * 100
  return `${Number.isInteger(pct) ? pct.toFixed(0) : pct.toFixed(1)}%`
}

/**
 * `0.5` -> `100%`, `0.9` -> `900%`.
 *
 * One decimal below 100%, whole numbers above it: a tenth of a percent carries
 * information when the figure is small (11.1% is a different situation from 12%)
 * and is false precision when the figure is 900%. The cut is at 100% rather than
 * at 10% because the four figures a reader actually meets — 11.1, 42.9, 100,
 * 900 — should all read as themselves.
 *
 * `NaN` gets `—` rather than `无法回本`: "we could not compute this" and "this
 * can never come back" are different statements, and letting the first render
 * as the second would be a wrong answer wearing a confident face.
 */
export function formatGain(gain: number): string {
  if (Number.isNaN(gain)) return '—'
  if (!Number.isFinite(gain)) return '无法回本'
  const pct = gain * 100
  return `${(pct < 100 ? pct.toFixed(1) : pct.toFixed(0)).toString()}%`
}

/** `5.04` -> `5.0`, and anything past a century becomes `> 100`. */
export function formatYears(years: number): string {
  if (Number.isNaN(years)) return '—'
  if (!Number.isFinite(years)) return '永远'
  if (years > 100) return '> 100'
  return years.toFixed(1)
}

/**
 * The depths the prompt puts side by side.
 *
 * Not decoration: read down the column and the shape of the thing appears — the
 * first row is a bad week, the last is most of a working life. A reader who
 * sees only their own number learns nothing about where they are on the curve.
 */
export const DEPTHS: readonly Fraction[] = [0.1, 0.3, 0.5, 0.7, 0.9]

/**
 * How close a figure has to be to a row for the two to be the same row.
 *
 * Half a percentage point, which is the precision the table prints at — so two
 * figures that would render identically are treated as identical. Without this,
 * being down 30.2% would produce a `30%` row *and* a `30.2%` row that read the
 * same and sit next to each other.
 */
const NEAR = 0.005

/** Whether a row is the reader's own, at the precision the table shows. */
export function isOwnDepth(loss: Fraction, depth: Fraction): boolean {
  return Math.abs(loss - depth) < NEAR
}

/**
 * The rows to render, with the reader's own figure among them.
 *
 * The five fixed depths answer "here is the curve". They do not answer "and
 * where am I on it", which is the only question the reader actually asked —
 * someone down 32% would find no row of their own and have to interpolate by
 * eye. So their figure is inserted (ascending) unless it is already close
 * enough to one of the fixed rows to be the same row.
 *
 * Out-of-range values are ignored rather than clamped: `0` and `1` are not
 * positions on this curve, and inventing a row for them would be the table
 * making up a fact.
 */
export function depthsIncluding(loss: Fraction, depths: readonly Fraction[] = DEPTHS): number[] {
  if (!(loss > 0) || loss >= 1) return [...depths]
  const alreadyThere = depths.some((depth) => isOwnDepth(loss, depth))
  const rows = alreadyThere ? [...depths] : [...depths, loss]
  return rows.sort((a, b) => a - b)
}
