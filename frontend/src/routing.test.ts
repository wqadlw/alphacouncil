import { describe, expect, it } from 'vitest'
import {
  activeHref,
  definitionFor,
  instrumentHref,
  parseHash,
  POOL_HREF,
  RETROSPECTIVE_HREF,
  REVIEW_HREF,
  ROUTES,
  titleFor,
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

/**
 * The route table is the single source of truth (spec 022), so these assert the
 * *properties* the rest of the app relies on rather than restating its contents.
 * A test that copied the table would still pass after the table rotted.
 */
describe('ROUTES, the one place a view is declared', () => {
  it('every entry parses back to its own name', () => {
    // The round trip that caught a real bug: the name used to be derived by
    // slicing `#/` off the href, which yields `''` for the today page.
    for (const entry of ROUTES) {
      expect(parseHash(entry.href)).toEqual({ name: entry.name })
    }
  })

  it('no two entries share a hash', () => {
    const hashes = ROUTES.map((entry) => entry.href)
    expect(new Set(hashes).size).toBe(hashes.length)
  })

  it('every label and title is free of digits', () => {
    /**
     * Not a style rule. Three E2E specs assert on the **whole page body** — the
     * dangerous quadrant contains no digit at all (red line 10) — and the nav is
     * part of that body. A digit here breaks a red-line test somewhere else, which
     * is the worst possible place to discover a label.
     */
    for (const entry of ROUTES) {
      expect(entry.label, entry.href).not.toMatch(/[0-9]/)
      expect(entry.title, entry.href).not.toMatch(/[0-9]/)
    }
  })

  it('no label uses a word the whole-page red-line tests forbid', () => {
    // `% 正确率 记住率 掌握度 评分 得分` from review.spec.ts, `收益率` from
    // today.spec.ts. `评分` is why the process score is called 过程分 everywhere.
    const forbidden = ['%', '正确率', '记住率', '掌握度', '评分', '得分', '收益率']
    for (const entry of ROUTES) {
      for (const word of forbidden) {
        expect(entry.label.includes(word), `${entry.label} contains ${word}`).toBe(false)
        expect(entry.title.includes(word), `${entry.title} contains ${word}`).toBe(false)
      }
    }
  })

  it('looks up a definition by name', () => {
    expect(definitionFor('retrospective').href).toBe(RETROSPECTIVE_HREF)
  })
})

describe('activeHref', () => {
  it('marks the current enumerated view', () => {
    expect(activeHref({ name: 'pool' })).toBe(POOL_HREF)
  })

  it('marks nothing on an instrument page', () => {
    // An instrument page is not in the nav, so nothing should read as current —
    // highlighting "今天" there would claim the reader is on the today page.
    expect(activeHref({ name: 'instrument', market: 'sh', code: '600519' })).toBe('')
  })

  it('marks nothing on an unknown address', () => {
    // It has just said it does not know where it is; lighting up a nav item would
    // contradict that in the same breath.
    expect(activeHref({ name: 'unknown', raw: '#/nonsense' })).toBe('')
  })
})

describe('titleFor', () => {
  it('uses the table title for an enumerated view', () => {
    expect(titleFor({ name: 'retrospective' })).toBe(definitionFor('retrospective').title)
  })

  it('names the instrument on an instrument page', () => {
    expect(titleFor({ name: 'instrument', market: 'sh', code: '600519' })).toBe('600519.SH')
  })

  it('says so on an unknown address', () => {
    expect(titleFor({ name: 'unknown', raw: '#/x' })).toBe('这个地址看不懂')
  })
})
