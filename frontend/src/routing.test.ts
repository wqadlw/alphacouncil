import { describe, expect, it } from 'vitest'
import {
  instrumentHref,
  parseHash,
  POOL_HREF,
  RETROSPECTIVE_HREF,
  REVIEW_HREF,
  TODAY_HREF,
} from './routing'

describe('parseHash', () => {
  it('reads an empty hash as the today page', () => {
    // Product definition §六: opening the program lands on today. The pool is
    // one deliberate click away, not the default.
    expect(parseHash('')).toEqual({ name: 'today' })
    expect(parseHash('#')).toEqual({ name: 'today' })
    expect(parseHash('#/')).toEqual({ name: 'today' })
  })

  it('reads the pool route', () => {
    expect(parseHash('#/pool')).toEqual({ name: 'pool' })
  })

  it('reads the review route', () => {
    expect(parseHash('#/review')).toEqual({ name: 'review' })
  })

  it('reads the retrospective route', () => {
    expect(parseHash('#/retrospective')).toEqual({ name: 'retrospective' })
  })

  it('does not let the two review routes be confused', () => {
    // `#/decision-review` would have been three characters from `#/review` and
    // means something else entirely: one recalls a claim, the other grades your
    // own reasoning about a past decision. It must not resolve.
    expect(parseHash('#/decision-review')).toEqual({
      name: 'unknown',
      raw: '#/decision-review',
    })
    expect(RETROSPECTIVE_HREF).not.toBe(REVIEW_HREF)
  })

  it('reads an instrument route', () => {
    expect(parseHash('#/i/sh/600519')).toEqual({
      name: 'instrument',
      market: 'sh',
      code: '600519',
    })
  })

  it('reports an unrecognised hash instead of falling back to today', () => {
    // Showing a plausible page for a mistyped link is the kind of failure that
    // looks like success — the same reason the backend reports an ambiguous
    // ticker rather than choosing a market for you.
    expect(parseHash('#/i/sh/60051')).toEqual({ name: 'unknown', raw: '#/i/sh/60051' })
    expect(parseHash('#/nonsense')).toEqual({ name: 'unknown', raw: '#/nonsense' })
  })

  it('rejects a code that is not exactly six digits', () => {
    expect(parseHash('#/i/sh/6005190').name).toBe('unknown')
    expect(parseHash('#/i/sh/abcdef').name).toBe('unknown')
  })

  it('rejects a market it does not know', () => {
    // The venue is a closed set (sh / sz / bj). A four-letter "market" is a
    // typo, not a new exchange.
    expect(parseHash('#/i/hk/00700').name).toBe('unknown')
  })
})

describe('instrumentHref', () => {
  it('round-trips through parseHash', () => {
    // The two must agree, or a link built by one page would not open on the
    // other — and nothing else in the app would notice.
    const href = instrumentHref('sz', '000001')
    expect(parseHash(href)).toEqual({ name: 'instrument', market: 'sz', code: '000001' })
  })

  it('produces the documented address form', () => {
    expect(instrumentHref('sh', '600519')).toBe('#/i/sh/600519')
  })
})

describe('TODAY_HREF', () => {
  it('parses back to today', () => {
    expect(parseHash(TODAY_HREF)).toEqual({ name: 'today' })
  })
})

describe('POOL_HREF', () => {
  it('parses back to the pool', () => {
    expect(parseHash(POOL_HREF)).toEqual({ name: 'pool' })
  })
})
