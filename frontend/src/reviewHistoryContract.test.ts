/**
 * ⭐⭐⭐ **The card review history's red-line decisions, asserted against the real values.**
 *
 * `recallContract.test.ts` holds the *queue*'s copy decisions for the same reason this
 * file exists: **wording and emphasis are exactly what gets "improved" later by someone
 * who has not read why it was chosen.**
 *
 * ## ⭐ Why this file exists at all — a debt I declared and then had to re-measure
 *
 * spec 055 shipped the card review history and its mutation check reported three green
 * results, which I recorded as 「适配器的三条红线无守卫」. ⚠️ **That sentence was wrong, and
 * finding out why is the reason this file exists.**
 *
 * I had run those mutations against **one** harness (`ratings.test.ts`, the file that
 * owns the vocabulary). Re-run against everything:
 *
 * | mutation | vitest | E2E | what was actually true |
 * |---|---|---|---|
 * | 「延期」 instead of the reader's wording | green | **inconsistent** — red once, green once | see below |
 * | render `duration_ms` | green | green | ⭐ **a real hole. This file closes it** |
 * | colour the `deferred` row | green | **never valid** — the build failed | ⭐ **my mutation was not valid TypeScript** |
 *
 * ⭐⭐ **Two lessons, and the second is the one that generalises:**
 *
 * 1. **The 「延期」 row flipped between runs.** The cause is `reuseExistingServer: !isCI` in
 *    `playwright.config.ts` ⭐ — sequential mutation runs reuse the previous run's
 *    already-built bundle, ⭐ so **each case can be measuring the previous case's artifact**.
 *    Verified by grepping `dist/assets/*.js` for the marker before each run. ⇒ **The E2E
 *    suite is not a trustworthy mutation oracle for source-level edits on this machine**,
 *    and the honest entry is 「could not be measured reliably」 — **not** 「guarded」 and
 *    **not** 「unguarded」. `F-253`.
 * 2. ⭐⭐ **A mutation that fails the build was being counted as a passing mutation.**
 *    `tone: (…) as const` on a conditional is `TS1355`, so the A3 case never produced an
 *    artifact at all ⭐ and any verdict about it was a verdict about nothing. ⇒ **Confirm
 *    the mutation reached the artifact before believing the result** (F-140, one level up).
 *
 * ⇒ **Everything below is a value assertion for that reason.** No source scraping, no
 * browser, no build. It runs in ~40ms and it cannot be confused with an infrastructure
 * failure, because there is no infrastructure.
 */

import { describe, expect, it } from 'vitest'

import {
  CARD_MARKED_OUTCOMES,
  CARD_OUTCOME_LABEL,
  CARD_RATING_LABEL,
  NOTE_MARKED_OUTCOMES,
  NOTE_OUTCOME_LABEL,
  cardReviewEvents,
  noteReviewEvents,
} from './components/data/timelineAdapters'

describe('规则 7 · colour carries meaning, and only where it does', () => {
  // ⭐ **Asserted as sets of outcomes, not as class names.** 规则 7 is about *meaning*,
  // and the mechanism that carries it is one exported set per adapter ⭐ — so asserting the
  // set asserts the decision, ⭐ whereas asserting a class name would only assert the
  // rendering and would stay green if a second row picked up the same colour.
  it('marks exactly the note outcome whose consequence differs', () => {
    // ⭐ `reset` and only `reset`: a rewrite **wiped the schedule**, so the row's
    // consequence is different from every other row's. spec 028 made it a `reset` for
    // exactly this reason — the reader has to be able to learn they are looking at a
    // second pass over different text.
    expect([...NOTE_MARKED_OUTCOMES].sort()).toEqual(['reset'])
  })

  it('marks nothing in the card history, and the emptiness is the argument', () => {
    // ⭐⭐ **An empty set asserted, not a `tone: 'neutral'` literal.**
    //
    // A card's `outcome` is constrained to `('reviewed','deferred')` by migration 0005,
    // so there is no `reset` ⭐ and nothing whose consequence differs: a postponement and
    // a recall both leave the reader with a card on a schedule. ⭐ Colouring one would
    // invent a distinction the product does not make.
    //
    // ⚠️ And this is why the source reads `CARD_MARKED_OUTCOMES.has(...)` rather than a
    // literal: **a literal would say 「colour is switched off」 where the truth is 「there
    // is nothing to mark」**, and those are different claims to leave lying in a file.
    expect(CARD_MARKED_OUTCOMES.size).toBe(0)
  })

  it('does not mark a card row, whichever way the mutation is written', () => {
    // ⭐ The second half of the guard, and it is the half a size assertion cannot see.
    // ⭐ `CARD_MARKED_OUTCOMES` is typed over `CardReview['outcome']`, so a name that does
    // not exist on the wire is a **compile error** ⭐ — the drift cannot be written at all.
    const outcomes = ['reviewed', 'deferred'] as const
    for (const outcome of outcomes) {
      expect(CARD_MARKED_OUTCOMES.has(outcome), `${outcome} must not earn colour`).toBe(false)
    }
  })
})

describe('红线 11 · the reader is not timed, and not counted', () => {
  /**
   * ⭐⭐⭐ **The first version of this guard asserted the exported labels and was GREEN
   * while a mutation printed `duration_ms` into the `detail` line.**
   *
   * `detail` is a template literal assembled inside `cardReviewEvents`, ⭐ so no label
   * table could see it. ⭐ **That is `ratings.test.ts`'s own warning reproduced in a new
   * place** — 「a value assertion cannot see a string assembled one line away from it」 —
   * and it is recorded here rather than quietly fixed, because ⭐ **a guard that checks the
   * wrong object is worse than no guard**: it was green, it looked like coverage, and
   * red line 11 had nothing behind it.
   *
   * ⇒ So the assertions below run the builders and inspect **what a row actually says**.
   */
  const timedCard = {
    id: 'review_1',
    card_id: 'card_1',
    outcome: 'reviewed',
    rating: 'good',
    reviewed_at: '2026-10-01T02:00:00+00:00',
    duration_ms: 4321,
    from_due_at: '2026-10-09T01:00:00+00:00',
    to_due_at: '2026-10-16T01:00:00+00:00',
    from_state: 'learning',
    to_state: 'learning',
  } as const

  const timedNote = {
    id: 'review_1',
    note_id: 'note_1',
    outcome: 'reviewed',
    rating: 'good',
    reviewed_at: '2026-10-01T02:00:00+00:00',
    duration_ms: 4321,
    from_due_at: '2026-10-09T01:00:00+00:00',
    to_due_at: '2026-10-16T01:00:00+00:00',
    from_state: 'learning',
    to_state: 'learning',
  } as const

  it('a card row never says how long the reader took', () => {
    // ⭐ The row is built from a review that **does** carry `duration_ms: 4321`, ⭐ so the
    // assertion is about the adapter declining to print a fact it was handed — not about a
    // field that happens to be absent.
    const [event] = cardReviewEvents([timedCard])
    const said = [event.what, event.detail].filter((part): part is string => typeof part === 'string')
    expect(said.length).toBeGreaterThan(0)
    for (const text of said) {
      expect(text, `卡片行渲染出了时长：「${text}」`).not.toMatch(/4321|ms|毫秒|秒/)
      expect(text, `卡片行渲染出了 duration_ms：「${text}」`).not.toMatch(/duration/i)
    }
  })

  it('a note row never says how long the reader took either', () => {
    const [event] = noteReviewEvents([timedNote])
    const said = [event.what, event.detail].filter((part): part is string => typeof part === 'string')
    for (const text of said) {
      expect(text, `笔记行渲染出了时长：「${text}」`).not.toMatch(/4321|ms|毫秒|秒/)
    }
  })

  it('and the row still says the two things the reader asked for', () => {
    // ⭐⭐ **The other half, and it is why this is an assertion on output rather than a
    // prohibition.** Red line 11 forbids the duration; it does not forbid the row. ⭐ A
    // guard written only as 「no duration」 is satisfied by an empty string ⭐ — so this
    // pins what the row **must** carry: the grade in the reader's words, and where the
    // card goes next. ⭐ `timelineAdapters.tsx` argues that either half alone leaves the
    // reader guessing.
    const [event] = cardReviewEvents([timedCard])
    expect(event.what).toBe(`复习过 · ${CARD_RATING_LABEL.good}`)
    expect(event.detail).toBe('下一次 2026-10-16')
  })

  it('neither history offers a tally of how many times the reader was reviewed', () => {
    // ⭐ Red line 11's counting half: a number the reader could try to climb.
    // `GET /review/due` already returns a bare list for the same reason, and
    // `routes/notes.py:286-288` argues it for notes. ⭐ Checked on **every field of every
    // rendered row**, ⭐ because a tally reads naturally in the `detail` slot — which is
    // exactly where the duration guard first looked and did not find anything.
    //
    // ⚠️⚠️ **The first version of this assertion banned every digit and was wrong.** ⭐ The
    // `detail` slot legitimately carries **a date** — 「下一次 2026-10-16」 ⭐ — and a date
    // is a fact about time, not a measure of the reader. ⭐ So the rule is not 「no digits」
    // but **「no number wearing a unit of activity」**: `4 次` / `3 遍` / `12 条`.
    // ⭐ A blanket digit ban would have forced the one thing this product owes the reader
    // (when the card comes back) to be deleted to satisfy a red line.
    const TALLY = /\d+\s*(次|遍|回|轮|个|条|张|天|小时|分钟)/
    const rows = [
      ...cardReviewEvents([timedCard]),
      ...noteReviewEvents([timedNote]),
    ]
    for (const row of rows) {
      for (const [slot, value] of Object.entries(row)) {
        if (typeof value === 'string' && slot !== 'at' && slot !== 'id') {
          expect(value, `${slot} 看起来像一个关于读者的计数：「${value}」`).not.toMatch(TALLY)
        }
      }
    }
    // ⭐ And the date that the ban above must **not** remove.
    expect(cardReviewEvents([timedCard])[0].detail).toContain('2026-10-16')
  })
})

describe('the reader\'s own words for a postponement', () => {
  it('says the same sentence in both histories, and never 「延期」', () => {
    // ⭐ One action, two queues, **one** wording. 「延期」 is a scheduler's word; this is the
    // reader's. spec 055 `plan.md` §三 measured that 「现在不是时候」 is
    // `outcome: 'deferred'` rather than a rating, ⭐ so it is the same action arriving
    // through a different field ⭐ — and two sentences for one action is how spec 049's
    // drift started.
    expect(CARD_OUTCOME_LABEL.deferred).toBe('我说以后再看')
    expect(NOTE_OUTCOME_LABEL.deferred).toBe(CARD_OUTCOME_LABEL.deferred)

    for (const [name, table] of [
      ['card', CARD_OUTCOME_LABEL],
      ['note', NOTE_OUTCOME_LABEL],
    ] as const) {
      for (const [outcome, text] of Object.entries(table)) {
        expect(text, `${name}.${outcome} 用了「延期」—— 那是排程器的词`).not.toContain('延期')
      }
    }
  })

  it('gives a note history three outcomes and a card history two, for a structural reason', () => {
    // ⭐ **Asserted as a difference, and the reason is a CHECK constraint, not a preference.**
    // Migration 0005: `CHECK (outcome IN ('reviewed', 'deferred'))` ⭐ — a card is
    // immutable, so its schedule is never wiped and there is nothing to record. ⭐ A note is
    // editable, so a rewrite restarts its schedule and is recorded.
    //
    // ⚠️ So `CARD_OUTCOME_LABEL` must **never** be made a subset of the note's ⭐: `reset`
    // is not missing on purpose, ⭐ there is no such event for a card to have.
    expect(Object.keys(NOTE_OUTCOME_LABEL).sort()).toEqual(['deferred', 'reset', 'reviewed'])
    expect(Object.keys(CARD_OUTCOME_LABEL).sort()).toEqual(['deferred', 'reviewed'])
  })
})