/**
 * `formatAgo` — the recall queue's only sense of time (spec 029).
 *
 * Three properties the queue's product rule depends on, and each is a claim about
 * the *shape* of the string rather than about its content:
 *
 * ⭐ **No digits are banned** — the label says 「8 天前」, and 8 is not a count of
 * anything the reader owes. The rule is about *tallies*, not numbers, and a test
 * that banned digits here would be banning the only useful thing in the row.
 * ⭐ **The past tense.** No 「还有」「逾期」「该做」 — a queue the reader can be
 * behind is a to-do list, and `项目总纲` §2.1⑤ asks for
 * 「一句陈述，无推送、无红点、无催促词」.
 * ⭐ **A future due date does not print a negative age.** A deferral or a reset can
 * move a due date forward; `-3 天前` would be a bug that reads as data.
 */

import { describe, expect, it } from 'vitest'
import { formatAgo } from './formatAgo'

const NOW = new Date('2026-09-28T12:00:00.000Z')

describe('formatAgo · 复习队列的时间（spec 029）', () => {
  it('recent stays in days rather than hours', () => {
    // 「5 小时前」 invites the reader to wonder whether the schedule is working.
    // 「今天」 is reassuring and the cheapest thing to say.
    expect(formatAgo('2026-09-28T07:00:00.000Z', NOW)).toBe('今天')
    // ⭐ Five hours, not twenty-nine. The first draft used `2026-09-27T07:00Z`
    // and expected `今天`, but that is 29 hours earlier and `1 天前` is the
    // honest answer. Loosening the formatter to hide a bad expectation would
    // misreport every note someone skipped a day on.
    expect(formatAgo('2026-09-28T07:00:00.000Z', NOW)).toBe('今天')
    // And the boundary itself: 24 hours exactly is a day, not 「今天」.
    expect(formatAgo('2026-09-27T12:00:00.000Z', NOW)).toBe('1 天前')
  })

  it('counts days, then months, then years', () => {
    expect(formatAgo('2026-09-20T12:00:00.000Z', NOW)).toBe('8 天前')
    expect(formatAgo('2026-08-28T12:00:00.000Z', NOW)).toBe('1 个月前')
    expect(formatAgo('2026-01-28T12:00:00.000Z', NOW)).toBe('8 个月前')
    expect(formatAgo('2024-09-28T12:00:00.000Z', NOW)).toBe('2 年前')
  })

  it('a due date in the future says 今天 rather than a negative age', () => {
    // A deferral, or a reset that put the note back, can both do this. `-3 天前`
    // would read as data rather than as a bug.
    expect(formatAgo('2026-10-01T12:00:00.000Z', NOW)).toBe('今天')
    expect(formatAgo('2027-01-01T12:00:00.000Z', NOW)).toBe('今天')
  })

  it('never says anything in the imperative', () => {
    const samples = [
      '2026-09-28T07:00:00.000Z',
      '2026-09-20T12:00:00.000Z',
      '2026-01-28T12:00:00.000Z',
      '2024-09-28T12:00:00.000Z',
    ]
    for (const iso of samples) {
      const label = formatAgo(iso, NOW)
      for (const forbidden of ['还', '逾期', '该', '请', '欠', '剩']) {
        expect(label, `「${label}」里出现了「${forbidden}」`).not.toContain(forbidden)
      }
    }
  })

  it('has no place to put a tally', () => {
    // ⭐ One phrase, one number, and the number is a **duration** — not a count of
    // how many notes are waiting. A test banning digits here would ban the only
    // useful thing in the row; what it must forbid is a number *of items*, which
    // shows up as a noun right after a digit.
    for (const iso of ['2026-09-20T12:00:00.000Z', '2026-01-28T12:00:00.000Z']) {
      const label = formatAgo(iso, NOW)
      // ⭐ `个` is **not** in this list: `8 个月前` is a duration, and the
      // regex `/\d+个/` matches it. That is the same failure as spec 028's
      // 「条」 rule rejecting 「**这**条在复习队列上」 — a list written by listing
      // cannot see which meaning a word carries in its sentence, and the tell
      // is always the same: the test fails on output that is obviously right.
      // The item counters stay; the duration unit goes.
      expect(label).not.toMatch(/\d+\s*(条|篇|项|张)/)
    }
  })

  it('an absent or unreadable date is a dash, not a crash', () => {
    expect(formatAgo(null, NOW)).toBe('—')
    expect(formatAgo('not a date', NOW)).toBe('—')
  })
})
