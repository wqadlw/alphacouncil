import { describe, expect, it } from 'vitest'
import type { QuoteResult } from './api'
import { summarizeQuote } from './quoteSummary'

const STAMP = '2026-09-27T04:00:00Z'

function ok(overrides: Partial<QuoteResult> = {}): QuoteResult {
  return {
    status: 'ok',
    value: {
      // `symbol` is declared and never read (see api.ts). The fixture carries it because
      // `tsc` is the only thing that notices when the server stops sending it.
      symbol: { market: 'cn', code: '600519' },
      price: 1237.0,
      prev_close: 1251.0,
      change_pct: -0.0112,
      open: 1250,
      high: 1255,
      low: 1230,
      volume: 2_400_000,
      amount: 2.97e9,
      quoted_at: STAMP,
      source: 'tencent',
      fetched_at: STAMP,
    },
    reason: null,
    detail: null,
    error_code: null,
    source: 'tencent',
    fetched_at: STAMP,
    stale: false,
    ...overrides,
  }
}

describe('summarizeQuote', () => {
  it('holds an ellipsis while the quotes request has not landed', () => {
    // `undefined` is not one of the four states — it is "the list is on
    // screen, the numbers are still walking over". The row must not borrow a
    // data-state's vocabulary for what is only a loading moment.
    const cell = summarizeQuote(undefined)

    expect(cell).toEqual({
      price: null,
      change: null,
      stale: false,
      note: '…',
      emphasis: 'faint',
      detail: null,
    })
  })

  it('formats the price and signs the change', () => {
    const cell = summarizeQuote(ok())

    expect(cell.price).toBe('1237.00')
    // -0.0112 arrives as a decimal fraction; the sign is part of the text, so
    // colour never carries the direction alone.
    expect(cell.change).toEqual({ text: '−1.12%', tone: 'down' })
    expect(cell.note).toBeNull()
    expect(cell.stale).toBe(false)
  })

  it('keeps the up sign and tone for a gain', () => {
    const cell = summarizeQuote(ok({ value: { ...ok().value!, change_pct: 0.0205 } }))

    expect(cell.change).toEqual({ text: '+2.05%', tone: 'up' })
  })

  it('marks a stale value instead of passing it off as today\'s', () => {
    // The router relabels a cache fallback as stale; the row's duty is to say
    // 「旧」out loud — a cached price shown as current is a quiet lie.
    const cell = summarizeQuote(ok({ stale: true }))

    expect(cell.stale).toBe(true)
    expect(cell.price).toBe('1237.00')
    expect(cell.detail).toContain('上一个有效价格')
  })

  it('says 无报价 when the source has nothing for the code', () => {
    const result = ok({
      status: 'no_data',
      value: null,
      reason: 'symbol not present in response',
      source: null,
      fetched_at: null,
    })
    const cell = summarizeQuote(result)

    expect(cell.price).toBeNull()
    expect(cell.change).toBeNull()
    expect(cell.note).toBe('无报价')
    expect(cell.emphasis).toBe('faint')
    expect(cell.detail).toBe('symbol not present in response')
  })

  it('says 取数失败 with the error code at hand', () => {
    const result = ok({
      status: 'error',
      value: null,
      error_code: 'DATA_SOURCE_UNAVAILABLE',
      source: null,
      fetched_at: null,
    })
    const cell = summarizeQuote(result)

    expect(cell.note).toBe('取数失败')
    // A failure is worth a warning tint; "the source has nothing" is not.
    expect(cell.emphasis).toBe('warn')
    expect(cell.detail).toBe('DATA_SOURCE_UNAVAILABLE')
  })

  it('says 无法确认 for the state between having and verifying', () => {
    const result = ok({
      status: 'unavailable',
      value: null,
      reason: 'received, unverifiable',
      source: null,
      fetched_at: null,
    })
    const cell = summarizeQuote(result)

    expect(cell.note).toBe('无法确认')
    expect(cell.emphasis).toBe('warn')
  })
})
