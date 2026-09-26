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
