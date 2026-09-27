import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  displayCode,
  formatAmount,
  formatChange,
  formatMoment,
  formatPrice,
  formatVolume,
  todayLabel,
} from './format'

/**
 * The stylesheet, read as text rather than imported.
 *
 * `import css from './index.css?raw'` returns an empty string here: the
 * Tailwind plugin claims the `.css` id before Vite's raw-asset handling sees it.
 * Reading the file off disk is deterministic and skips the plugin pipeline
 * entirely, which is what a test of the *contents* wants anyway.
 */
const css = readFileSync(new URL('./index.css', import.meta.url), 'utf8')

describe('formatChange', () => {
  it('reads a rise as up and a fall as down', () => {
    expect(formatChange(0.0114).tone).toBe('up')
    expect(formatChange(-0.0114).tone).toBe('down')
  })

  it('states the sign as well as the colour', () => {
    // Colour alone is invisible to a reader who cannot tell the two apart, and
    // this is the one place in the product where misreading a digit matters.
    // The minus is U+2212 (a true minus, the width of a digit in tabular
    // figures), not the ASCII hyphen.
    expect(formatChange(0.0114).text).toBe('+1.14%')
    expect(formatChange(-0.0114).text).toBe('−1.14%')
  })

  it('uses the A-share convention — a rise is red, a fall is green', () => {
    // The tone is only half the encoding; the other half is which colour it
    // becomes, and that mapping lives in CSS where no other test would reach
    // it. It is worth an assertion precisely because this is the one convention
    // in the product that is *inverted* from the US default, and therefore the
    // one a well-meaning change is most likely to flip.
    expect(css).toContain('--color-up: #c0392b')
    expect(css).toContain('--color-down: #1e7a46')
  })

  it('treats an unchanged close as neither up nor down', () => {
    expect(formatChange(0).tone).toBe('flat')
    expect(formatChange(0).text).toBe('+0.00%')
  })

  it('formats a large move without losing the sign', () => {
    expect(formatChange(-0.1003).text).toBe('−10.03%')
  })
})

describe('displayCode', () => {
  it('renders the conventional form', () => {
    expect(displayCode('sh', '600519')).toBe('600519.SH')
    expect(displayCode('sz', '000001')).toBe('000001.SZ')
  })

  it('upper-cases a venue it has no label for, rather than dropping it', () => {
    // The identity is (market, code). Rendering only the code would print two
    // different instruments identically.
    expect(displayCode('bj', '430047')).toBe('430047.BJ')
  })
})

describe('formatMoment', () => {
  it('renders an absent timestamp as an em dash', () => {
    expect(formatMoment(null)).toBe('—')
  })

  it('returns unparseable input unchanged rather than inventing a date', () => {
    expect(formatMoment('not a date')).toBe('not a date')
  })

  it('renders an instant in the reader’s own zone', () => {
    // Asserted by shape, not by value: the machine's timezone is not this
    // test's business, and hard-coding one would make the suite pass or fail
    // depending on where it runs.
    expect(formatMoment('2026-09-26T13:19:00.033Z')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })
})

describe('formatPrice', () => {
  it('always shows two decimals, so a column of prices aligns', () => {
    expect(formatPrice(1237)).toBe('1237.00')
    expect(formatPrice(9.5)).toBe('9.50')
  })
})

describe('formatVolume', () => {
  it('converts shares to 手, because that is the unit a reader expects', () => {
    expect(formatVolume(50_000)).toBe('500 手')
  })

  it('switches to 万 above ten thousand 手', () => {
    expect(formatVolume(3_123_900)).toBe('3.12 万手')
  })

  it('switches to 亿 above a hundred million 手', () => {
    expect(formatVolume(2.4e10)).toBe('2.40 亿手')
  })
})

describe('formatAmount', () => {
  it('switches to 万 and 亿 at the expected thresholds', () => {
    expect(formatAmount(9_000)).toBe('9000 元')
    expect(formatAmount(3_867_310_000)).toBe('38.67 亿')
    expect(formatAmount(2_500_000)).toBe('250.00 万')
  })
})

describe('todayLabel', () => {
  it('renders the reader\'s calendar date with its weekday', () => {
    // The clock is a parameter: a test pins the date instead of hoping it
    // runs before midnight. 2026-09-27 is a Sunday.
    expect(todayLabel(new Date(2026, 8, 27, 23, 5))).toBe('2026-09-27 · 周日')
  })

  it('stays on the constructed calendar day', () => {
    // Built from local fields, the label must not re-derive the date through
    // the timezone machinery — midnight in Beijing is the 26th in UTC, and a
    // "today" that flips at midnight UTC is nobody's today.
    expect(todayLabel(new Date(2026, 8, 27, 0, 30))).toBe('2026-09-27 · 周日')
  })
})
