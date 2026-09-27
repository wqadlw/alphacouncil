/**
 * One row of the pool, as the price column renders it.
 *
 * A pure mapping from the four data states to what a row can say — the
 * row-level sibling of the instrument page's `QuoteBody`. The two are kept
 * apart on purpose: a row has room for a label ("取数失败"), the page for the
 * paragraph (which sources were tried, what the error code means, when the
 * number was fetched). One shared wording would either bloat every row or
 * starve the page.
 */

import type { QuoteResult } from './api'
import { formatChange, formatMoment, formatPrice, type Tone } from './format'

export interface QuoteCell {
  /** The price, formatted. Null when this state has no number to show. */
  price: string | null
  /** Signed percentage with its direction — colour plus sign, never colour alone. */
  change: { text: string; tone: Tone } | null
  /** True when every live source failed and this is the last known good value. */
  stale: boolean
  /** The state's row label: 「无报价」/「取数失败」/「无法确认」/「…」. */
  note: string | null
  /** How the label wants to be styled. */
  emphasis: 'normal' | 'warn' | 'faint'
  /** Hover text: provenance for a price, the reason for its absence. */
  detail: string | null
}

const NOTE: Record<Exclude<QuoteResult['status'], 'ok'>, string> = {
  no_data: '无报价',
  error: '取数失败',
  unavailable: '无法确认',
}

export function summarizeQuote(result: QuoteResult | undefined): QuoteCell {
  // `undefined` is the moment before the quotes request has landed — not a
  // data state, a loading one. The row is already on screen (the list never
  // waits for prices); the cell holds a quiet ellipsis until its number walks in.
  if (result === undefined) {
    return { price: null, change: null, stale: false, note: '…', emphasis: 'faint', detail: null }
  }

  if (result.status === 'ok' && result.value) {
    const quote = result.value
    const provenance = `数据时间 ${formatMoment(result.fetched_at)} · 来源 ${result.source}`
    return {
      price: formatPrice(quote.price),
      change: formatChange(quote.change_pct),
      stale: result.stale,
      note: null,
      emphasis: 'normal',
      detail: result.stale ? `${provenance} · 这是缓存里的上一个有效价格` : provenance,
    }
  }

  // The server's model validator refuses to build `ok` without a value, so
  // the branch below should be unreachable; if a future backend breaks that
  // contract, the row says so plainly rather than inventing a fifth state.
  if (result.status === 'ok') {
    return {
      price: null,
      change: null,
      stale: false,
      note: '取数失败',
      emphasis: 'warn',
      detail: 'ok without a value',
    }
  }

  const status = result.status
  return {
    price: null,
    change: null,
    stale: false,
    note: NOTE[status],
    emphasis: status === 'no_data' ? 'faint' : 'warn',
    detail: result.reason ?? result.error_code ?? null,
  }
}
