/**
 * Formatting, in one place, so the two pages cannot disagree.
 *
 * Everything here is presentation only. Notably, `change_pct` arrives already
 * computed from the server — this module multiplies by 100 to display it and
 * does no arithmetic beyond that. A second implementation of "what is the
 * percentage change" is a second chance to disagree about rounding or sign.
 */

const MARKET_LABEL: Record<string, string> = { sh: 'SH', sz: 'SZ', bj: 'BJ' }

/** `600519` + `sh` -> `600519.SH`. */
export function displayCode(market: string, code: string): string {
  return `${code}.${MARKET_LABEL[market] ?? market.toUpperCase()}`
}

/**
 * Timestamps arrive as UTC ISO strings; show them in the reader's own zone.
 *
 * The backend stamps everything in UTC (the events table enforces a `Z` suffix
 * in its CHECK constraints), so converting here is what makes "I wrote this at
 * 21:19" match the clock on the wall.
 */
export function formatMoment(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (value: number) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    ` ${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

export function formatPrice(value: number): string {
  return value.toFixed(2)
}

export type Tone = 'up' | 'down' | 'flat'

/** Tone → CSS class. Lived in InstrumentPage until a second page needed it. */
export const TONE_CLASS: Record<Tone, string> = {
  up: 'text-up',
  down: 'text-down',
  flat: 'text-ink-soft',
}

/**
 * Rule 3 — direction is carried by **colour and sign together**.
 *
 * Red is up and green is down, per the A-share convention (the opposite of the
 * US one). The sign is not decoration: colour alone is invisible to a reader
 * who cannot distinguish the two, and this is the one place in the product
 * where a misread digit matters.
 */
export function formatChange(pct: number): { text: string; tone: Tone } {
  const basisPoints = pct * 100
  const text = `${basisPoints >= 0 ? '+' : '−'}${Math.abs(basisPoints).toFixed(2)}%`
  if (basisPoints > 0) return { text, tone: 'up' }
  if (basisPoints < 0) return { text, tone: 'down' }
  return { text, tone: 'flat' }
}

/** Volume is in shares; a Chinese reader expects 手 (100 shares) for size. */
export function formatVolume(shares: number): string {
  const lots = shares / 100
  if (lots >= 1e8) return `${(lots / 1e8).toFixed(2)} 亿手`
  if (lots >= 1e4) return `${(lots / 1e4).toFixed(2)} 万手`
  return `${lots.toFixed(0)} 手`
}

/** Turnover arrives in CNY. */
export function formatAmount(cny: number): string {
  if (cny >= 1e8) return `${(cny / 1e8).toFixed(2)} 亿`
  if (cny >= 1e4) return `${(cny / 1e4).toFixed(2)} 万`
  return `${cny.toFixed(0)} 元`
}

export const EVENT_LABEL: Record<string, string> = {
  added: '加入关注',
  reason_revised: '修改理由',
  removed: '不再关注',
}

/** The five actions, in the words a reader would use for their own trade. */
export const ACTION_LABEL: Record<string, string> = {
  buy: '买入',
  add: '加仓',
  hold: '持有',
  trim: '减仓',
  exit: '清仓',
}

/**
 * Operators as words, because the predicate is meant to read as a sentence.
 *
 * `domain/decision.py` chose symbols over words (`lt` / `gt`) for the *stored*
 * form, on the grounds that `<` is what a person types in a screener. That
 * reasoning is about input; this is about reading it back months later, and
 * "gross_margin 小于 0.55" is the sentence that was intended.
 */
export const OPERATOR_LABEL: Record<string, string> = {
  '<': '小于',
  '<=': '不大于',
  '>': '大于',
  '>=': '不小于',
  '==': '等于',
  '!=': '不等于',
}

/**
 * A calendar date, rendered as written.
 *
 * **Not** through `new Date(...)`. `as_of` is a date, not an instant — it is the
 * point-in-time cutoff for a financial figure — and passing it through the
 * timezone machinery would let a reader in UTC-5 see 2026-12-30 for a cutoff
 * they wrote as 2026-12-31. A date that moves when you travel is not a date.
 */
export function formatDay(iso: string | null): string {
  if (!iso) return '—'
  return /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(0, 10) : iso
}

/** One predicate as a sentence: "截至 2026-12-31，gross_margin 小于 0.55". */
export function formatPredicate(criterion: {
  metric: string
  operator: string
  threshold: number
  as_of: string
}): string {
  const word = OPERATOR_LABEL[criterion.operator] ?? criterion.operator
  return `截至 ${formatDay(criterion.as_of)}，${criterion.metric} ${word} ${criterion.threshold}`
}
