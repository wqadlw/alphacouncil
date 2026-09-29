import { describe, expect, it } from 'vitest'
import type { MetricReading } from './api'
import { criterionVerdict } from './criterionVerdict'

function reading(overrides: Partial<MetricReading> = {}): MetricReading {
  return {
    state: 'not_crossed',
    label: 'MA20',
    value: 1275.46,
    as_of: '2026-09-29',
    period: 20,
    bars_available: 215,
    ...overrides,
  }
}

describe('criterionVerdict', () => {
  // ⭐ The five states are the feature. A test that only checks 「crossed renders
  // something」 would pass against a version that renders the same sentence for all five,
  // which is exactly the defect §4.6 names.

  it('says the comparison crossed, and shows the number', () => {
    const out = criterionVerdict(reading({ state: 'crossed', value: 1185.3 }))
    expect(out.crossed).toBe(true)
    expect(out.adjudicable).toBe(true)
    expect(out.verdict).toContain('已越过')
    expect(out.verdict).toContain('1185.30')
  })

  it('says not crossed without dressing it as relief', () => {
    // ⭐ 红线 13: 「没有越过」 and stop. 「还好」/「不错」/「安全」 would be the page
    // congratulating the reader on a fact about the market.
    const out = criterionVerdict(reading())
    expect(out.crossed).toBe(false)
    expect(out.adjudicable).toBe(true)
    for (const comfort of ['还好', '不错', '安全', '通过']) {
      expect(out.verdict).not.toContain(comfort)
    }
  })

  it('names a metric it cannot compute, as the reader typed it', () => {
    // ⭐ Rendering a catalogue label here would imply we recognise it. The whole
    // sentence is 「we do not know this」, and a friendly label undoes that.
    const out = criterionVerdict(
      reading({ state: 'undetermined', label: 'gross_margin', value: null, as_of: null }),
    )
    expect(out.adjudicable).toBe(false)
    expect(out.verdict).toContain('gross_margin')
    expect(out.verdict).toContain('没有被求值过')
  })

  it('counts what is missing, so a warm-up reads as a deferral', () => {
    // ⭐ 「还差 8 根」 tells the reader this resolves by itself. 「还在预热」 is a shrug.
    const out = criterionVerdict(
      reading({ state: 'warming', value: null, period: 20, bars_available: 12 }),
    )
    expect(out.verdict).toContain('还差 8 根')
    expect(out.adjudicable).toBe(false)
  })

  it('never claims zero bars exist when the count is absent', () => {
    // ⭐ `bars_available: null` means the server did not say. Subtracting from it would
    // print 「还差 0 根」 — a promise that the value exists, which is 红线 6.
    const out = criterionVerdict(reading({ state: 'warming', value: null, bars_available: null }))
    expect(out.verdict).not.toContain('还差')
    expect(out.verdict).toContain('还没有值')
  })

  it('distinguishes no bars at all from an unknown metric', () => {
    // ⭐ Two different faults: one may resolve tomorrow, the other will not. A single
    // 「we could not evaluate this」 merges them and the reader cannot tell which to fix.
    const missing = criterionVerdict(null)
    const unknown = criterionVerdict(
      reading({ state: 'undetermined', label: 'gross_margin', value: null, as_of: null }),
    )
    expect(missing.verdict).not.toBe(unknown.verdict)
    expect(missing.verdict).toContain('日线')
    expect(unknown.verdict).toContain('不在我们能算的指标里')
    expect(missing.adjudicable).toBe(false)
    expect(unknown.adjudicable).toBe(false)
  })

  it('never says 已触发 unless the comparison actually crossed', () => {
    // ⭐ The old E2E forbade 已触发 outright. That assertion is gone with the fact that
    // forbade it — but the *shape* of it survives: the word is earned, never defaulted.
    for (const state of ['not_crossed', 'warming', 'undetermined', 'no_bars'] as const) {
      const out = criterionVerdict(reading({ state, value: state === 'not_crossed' ? 1 : null }))
      expect(out.verdict).not.toContain('已触发')
    }
    expect(criterionVerdict(reading({ state: 'crossed' })).verdict).not.toContain('已触发')
  })

  it('prints a whole number as a whole number', () => {
    // ⭐ `1235.5800000001` in a sentence about the reader's own money claims a precision
    // the data does not have, and invites them to distrust the rest of the number.
    const out = criterionVerdict(reading({ state: 'crossed', value: 1236 }))
    expect(out.verdict).toContain('1,236')
    expect(out.verdict).not.toContain('1236.00')
  })

  it('survives a payload that predates the field entirely', () => {
    // ⭐ An E2E caught this: a fixture with no `metric` key made `metric.state` throw
    // **during render**, and the whole Today page went blank — ⭐ on the one page the
    // reader opens to find out what went wrong. `undefined` is therefore treated as
    // 「no bars」, not as a crash.
    const out = criterionVerdict(undefined)
    expect(out.adjudicable).toBe(false)
    expect(out.verdict).toContain('日线')
  })

  it('marks only crossed as actionable', () => {
    // ⭐ A louder rendering of 「we could not check」 would be the page presenting its own
    // gap as news about the reader's decision.
    const states = ['crossed', 'not_crossed', 'warming', 'undetermined', 'no_bars'] as const
    const adjudicable = states
      .map((state) => criterionVerdict(reading({ state, value: 1 })).adjudicable)
    expect(adjudicable).toEqual([true, true, false, false, false])
  })
})
