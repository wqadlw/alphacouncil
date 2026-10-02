/**
 * ⭐⭐⭐ **One home for the reader's words for a grade.**
 *
 * Spec 049. There were three tables for four values:
 *
 * ```
 *   RecallView.tsx        hard  想得起来，但有点犹豫
 *   LessonRecallView.tsx  hard  想得起来，但吃力
 *   timelineAdapters.tsx  hard  想起来了，但慢          <- its own
 * ```
 *
 * The third one was rendered by `NoteReviewTimeline`, which `VaultPage.tsx:1016`
 * draws inside a note's detail. So the reader pressed 「想得起来，但有点犹豫」 and the
 * record of that press said 「想起来了，但慢」 — and this test is the reason it cannot
 * happen a fourth time.
 *
 * ⭐ **Why this test compares strings and does not just compare types.** A type-level
 * check would have been green the whole time the wording was wrong three times over:
 * the wire values were always identical, only the words on screen differed. `regressions/0016`
 * is the shape — **a check that cannot fail on the defect you are guarding is not
 * guarding it.**
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { LESSON_RATINGS, NOTE_RATINGS, labelsOf } from './ratings'
import { NOTE_RATING_LABEL } from '../data/timelineAdapters'

const GRADES = ['again', 'hard', 'good', 'easy'] as const

const ADAPTER = fileURLToPath(new URL('../data/timelineAdapters.tsx', import.meta.url))

describe('the four grades', () => {
  it('are the same four wire values in both queues', () => {
    expect(NOTE_RATINGS.map((r) => r.value)).toEqual([...GRADES])
    expect(LESSON_RATINGS.map((r) => r.value)).toEqual([...GRADES])
  })

  it('say what a note is graded as in the note history', () => {
    // ⭐ The assertion the drift would have broken: the history's words are the queue's
    // words, taken from the table rather than compared by eye.
    for (const grade of GRADES) {
      expect(NOTE_RATING_LABEL[grade], `${grade}: the history must say what the button said`).toBe(
        NOTE_RATINGS.find((r) => r.value === grade)?.label,
      )
    }
  })

  it('keep `again` meaning 「我的想法变了」 in both queues', () => {
    // `RecallView.tsx:51-53` argues this at length: a note the reader has been overtaken
    // by is information the product wants, not an ordinary forgetting. A lesson keeps
    // the same four wire values and the same opening words — the difference between a
    // note and a lesson is in the *reason*, not the vocabulary, so this holds for both.
    expect(NOTE_RATINGS[0].label).toBe('我的想法变了')
    expect(LESSON_RATINGS[0].label).toBe('我的想法变了')
  })

  it('let the two queues differ in the other three, and that is deliberate', () => {
    // ⭐ **Written as an assertion that they DIFFER, not that they match.** The first
    // instinct when collecting three copies into one file is to make them equal; the
    // measured answer is that a lesson is the system's own output and a note is
    // something the reader wrote, so 「吃力」 and 「有点犹豫」 are two true sentences.
    // Flattening them would be a third wording, which is the failure this file ends.
    expect(LESSON_RATINGS[1].label).not.toBe(NOTE_RATINGS[1].label)
    expect(LESSON_RATINGS[2].label).not.toBe(NOTE_RATINGS[2].label)
    expect(LESSON_RATINGS[3].label).not.toBe(NOTE_RATINGS[3].label)
  })
})

describe('labelsOf', () => {
  it('flattens to exactly one label per grade', () => {
    expect(Object.keys(labelsOf(NOTE_RATINGS)).sort()).toEqual([...GRADES].sort())
  })

  it('takes no hint, because a history row is not a button', () => {
    // ⭐ The hint is the argument for pressing; a timeline line is a record, and
    // explaining itself there would be a second, quieter place for the wording to drift.
    expect(Object.values(NOTE_RATING_LABEL)).toEqual(
      NOTE_RATINGS.map((r) => r.label),
    )
  })
})

describe('the timeline holds no grade of its own', () => {
  // ⭐ **A source assertion, and it is here because a value assertion cannot catch a
  // reintroduced table.** `NOTE_RATING_LABEL` could equal the right strings and still
  // have been built from a copy sitting next to it — the assertion above would pass
  // either way. Only reading the file distinguishes 「derived」 from 「equal by luck」.
  //
  // ⭐⭐ **And it reads the file with its comments stripped** — a correction to the
  // first version of this test, which failed on `OUTCOME_LABEL`'s comment quoting
  // 「我的想法变了」 while explaining why `deferred` is not called 「延期」. That is
  // *prose about* the wording and has to stay; the assertion is about code that *holds*
  // the wording.
  //
  // ⇒ Three places the wording was found, and only one of them was a defect:
  //   1. `RecallView.tsx`        the queue's buttons       — correct
  //   2. `LessonRecallView.tsx`  a different queue, argued — correct
  //   3. `timelineAdapters.tsx` a third table              — the drift
  // Stripping comments rather than loosening the assertion is the deliberate choice:
  // loosening it to 「except when it appears in a comment」 would have let all three in.
  const source = stripComments(readFileSync(ADAPTER, 'utf8'))

  it('spells out none of the eight labels itself', () => {
    for (const table of [NOTE_RATINGS, LESSON_RATINGS]) {
      for (const entry of table) {
        expect(source, `timelineAdapters must not hold 「${entry.label}」 of its own`).not.toContain(
          entry.label,
        )
      }
    }
  })

  it('takes its labels through `ratings`', () => {
    expect(source).toContain('labelsOf')
    expect(source).toContain('NOTE_RATINGS')
  })
})

/**
 * Remove `//` and block comments, leaving string literals intact.
 *
 * ⚠️ String state is tracked because a `'//'` inside a URL is not a comment, and a
 * naive stripper that ignores it would delete the rest of the line — turning a passing
 * file into one that looks clean because it was truncated. `regressions/0003` is the
 * same lesson: **a measurement that quietly measures the wrong thing is worse than a
 * broken one, because it reports a number and nobody checks the number.**
 */
function stripComments(source: string): string {
  let out = ''
  let quote: string | null = null
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i]
    if (quote) {
      out += char
      if (char === '\\') {
        out += source[i + 1] ?? ''
        i += 1
      } else if (char === quote) {
        quote = null
      }
      continue
    }
    if (char === "'" || char === '"' || char === '`') {
      quote = char
      out += char
      continue
    }
    if (char === '/' && source[i + 1] === '/') {
      while (i < source.length && source[i] !== '\n') i += 1
      out += '\n'
      continue
    }
    if (char === '/' && source[i + 1] === '*') {
      i += 2
      while (i < source.length && !(source[i] === '*' && source[i + 1] === '/')) i += 1
      i += 1
      continue
    }
    out += char
  }
  return out
}