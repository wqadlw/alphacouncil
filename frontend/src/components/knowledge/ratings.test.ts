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
 * ⭐⭐ **It happened again anyway, in the one queue this file never named.** Spec 055
 * measured a **fourth** set in `ReviewPage.tsx:250`:
 *
 * ```
 *   ReviewPage.tsx:250    again 忘了   hard 有点难   good 记得   easy 太简单
 * ```
 *
 * ⭐ **The reason is the lesson, and it is why the block at the bottom of this file
 * exists.** The drift was found by putting call sites **side by side**, and this one was
 * never in that comparison — so a test that only checks the tables it already knows about
 * **cannot notice a third**. 「One home」 is a claim to be re-measured every time a surface
 * starts rendering a grade, not a thing a table's existence establishes.
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

import { CARD_RATINGS, LESSON_RATINGS, NOTE_RATINGS, labelsOf } from './ratings'
import { NOTE_RATING_LABEL } from '../data/timelineAdapters'

const GRADES = ['again', 'hard', 'good', 'easy'] as const

const ADAPTER = fileURLToPath(new URL('../data/timelineAdapters.tsx', import.meta.url))
const REVIEW_PAGE = fileURLToPath(new URL('../../ReviewPage.tsx', import.meta.url))

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
  //   4. `ReviewPage.tsx:250`    a fourth table            — found later, by spec 055
  // Stripping comments rather than loosening the assertion is the deliberate choice:
  // loosening it to 「except when it appears in a comment」 would have let all four in.
  //
  // ⭐ **`CARD_RATINGS` is in this loop as of spec 055**, because the card review history
  // renders in this file's own output — an inline card label here would be a **fifth**
  // copy, and it would sit two lines above `NOTE_RATING_LABEL`.
  const source = stripComments(readFileSync(ADAPTER, 'utf8'))

  it('spells out none of the twelve labels itself', () => {
    for (const table of [NOTE_RATINGS, LESSON_RATINGS, CARD_RATINGS]) {
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
 * ⭐⭐ **The fourth copy, and the assertion that ends it.**
 *
 * Spec 055 measured this on 2026-10-05. The two blocks above converged *three* tables,
 * and this file's header has always said 「one home」 — while a **fourth** set of words sat
 * in `ReviewPage.tsx` as five `<Button>` literals, in the one queue this test never named:
 *
 * ```
 *   ReviewPage.tsx:250    again 忘了   hard 有点难   good 记得   easy 太简单
 * ```
 *
 * ⭐ **The reason it survived spec 049 is the reason this block exists.** The drift was
 * found by putting call sites **side by side**, and this one was never in that comparison.
 * ⇒ **A table's existence is not evidence that everything uses it.** A test that only
 * checks the two tables it already knows about cannot notice a third.
 *
 * ⚠️ **These are source assertions, deliberately.** A DOM assertion — 「render the queue and
 * read the button text」 — would pass with the literals still in place, because
 * **the defect is that the words are equal while their origin differs**. Only reading the
 * file distinguishes 「derived from the table」 from 「equal by luck」, exactly as the block
 * above argues for `timelineAdapters`. (`regressions/0016`: a check that cannot fail on the
 * defect you are guarding is not guarding it.)
 */
describe('the card queue takes its labels from here too', () => {
  const page = stripComments(readFileSync(REVIEW_PAGE, 'utf8'))

  it('holds the same four wire values', () => {
    expect(CARD_RATINGS.map((r) => r.value)).toEqual([...GRADES])
  })

  it('spells out none of the four labels itself', () => {
    for (const entry of CARD_RATINGS) {
      expect(page, `ReviewPage must not hold 「${entry.label}」 of its own`).not.toContain(entry.label)
    }
  })

  it('reads them from `CARD_RATINGS`', () => {
    expect(page).toContain('CARD_RATINGS')
  })

  it('keeps every label non-empty and distinct', () => {
    // ⭐ The two failure shapes a hand-written table actually takes: a blank label, and the
    // same label twice (a copy-paste that reads correctly at a glance).
    const labels = CARD_RATINGS.map((r) => r.label)
    for (const label of labels) expect(label.length).toBeGreaterThan(0)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it('says 「忘了」 where the note queue says 「我的想法变了」, and that is the point', () => {
    // ⭐ **Written as an assertion that they DIFFER.** The instinct when collecting copies
    // into one file is to make them equal — and for a card that would be a fourth wording:
    // `ratings.ts`'s header argues at length that a card is the reader's claim **about a
    // company**, so forgetting it is a plain fact rather than a statement about the reader's
    // own thinking. Three true sentences beat one uniform one.
    expect(CARD_RATINGS[0].label).toBe('忘了')
    expect(CARD_RATINGS[0].label).not.toBe(NOTE_RATINGS[0].label)
  })

  it('keeps all four apart from the note queue, not just the first', () => {
    // ⭐⭐ **Added because the mutation check found the hole, not because a reviewer did.**
    // M3b changed the card's `good` to 「还是我的想法」 — the note's own word — and it
    // **stayed green**, because the assertion above only covered `again`. ⭐ That is
    // precisely the drift this file exists to end: one queue silently starting to read
    // like another. Recorded as `F-250`.
    //
    // ⚠️ **Compared as sets, not pairwise by index.** The property that matters is
    // 「no card word is a note word」, because that is what 「a card reads like a card」
    // means on screen — and a pairwise loop would pass if the table were reordered.
    const noteLabels = new Set(NOTE_RATINGS.map((r) => r.label))
    for (const entry of CARD_RATINGS) {
      expect(noteLabels, `「${entry.label}」 is a note word; the card queue must not borrow it`).not.toContain(
        entry.label,
      )
    }
  })

  it('does NOT pin the other three word-for-word, and that is deliberate', () => {
    // ⚠️ **A documented non-assertion.** The mutation check also ran 「有点难 -> 稍微难」
    // and it stayed green. ⭐ That is the intended behaviour, not a gap: this file pins the
    // **load-bearing** word (`again`, where forgetting and 「我的想法变了」 are different
    // claims) and the **relationships** (distinct from the note queue, distinct from each
    // other). It does not pin all four words, for the same reason it does not pin the note
    // table's — ⭐ **a test spelling out all four would be a second copy of the table**,
    // which is the failure this file exists to end, and it would report an editorial
    // copy-edit as a defect.
    //
    // ⇒ Both of these are true at once: a word-for-word rewrite is an **editorial act**
    // and is allowed to be green; a word that makes a card read like a note is a
    // **defect** and is red, by the block above. The second is the one that matters.
    expect(CARD_RATINGS).toHaveLength(4)
  })

  it('has no hint, because the queue never had one', () => {
    // ⭐ `recallContract.test.ts` asserts hints are longer than two characters — and it
    // asserts that of **NOTE** ratings. Inventing a hint here to fill the field would be a
    // sentence nobody chose, and it would make this table the odd one out under a rule that
    // does not apply to it.
    for (const entry of CARD_RATINGS) expect(entry.hint).toBe('')
  })

  it('renders the four grades from the table and leaves 「现在不是时候」 alone', () => {
    // ⚠️ `现在不是时候` is `outcome: 'deferred'`, not a rating, so it has no grade to key a
    // `data-testid` on. That is *why* the five buttons are not one `.map()` (`plan.md` §三),
    // and this assertion keeps the distinction from being tidied away later.
    expect(page).toContain('CARD_RATINGS.map')
    expect(page).toContain('rate-defer')
    expect(page).toContain('现在不是时候')
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