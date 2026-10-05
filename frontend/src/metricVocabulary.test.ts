/**
 * ⭐ `uncomputable()` — the sentence's only gate. (spec 058)
 *
 * ## ⭐ Why this test exists and not only the E2E
 *
 * The E2E proves the sentence reaches the screen. ⭐ This proves **when it should and
 * should not appear**, ⭐ which is the half a browser cannot isolate: ⭐ every negative case
 * needs a filled field, a catalogue that arrived or did not, ⭐ and a settled render.
 *
 * ⭐⭐ **And it exists because the mutation check could not measure the E2E reliably.**
 * Measured 2026-10-05: the frontend mutation script returned VOID 「build failed」 for this
 * behaviour **three runs running**, ⭐ while the identical mutation built cleanly when
 * applied by hand — ⭐ the previous mutation's `vite preview` was still holding `dist/`
 * (`F-253`'s family). ⭐ ⇒ **A guard verified only by an unreliable harness is half a
 * guard** (`F-254`: a non-result recorded as if it were one), ⭐ so this function is pure
 * and pinned here, where a mutation dies in milliseconds.
 *
 * ⭐ The tokens are the real ones: ⭐ **`gross_margin` is the name the product used to
 * suggest and does not hold; `gp_margin` is the one it does**, label 「销售毛利率」.
 */

import { describe, expect, it } from 'vitest'

import { METRIC_DATALIST_ID, uncomputable } from './metricVocabulary'

/** ⭐ The 32-token vocabulary, reduced to the two this spec turned on. */
const COMPUTABLE = new Set(['close', 'ma20', 'gp_margin'])

describe('uncomputable', () => {
  it('⭐ says so for a token this build does not hold', () => {
    // ⭐ The defect, verbatim: `gross_margin` is what the field's own placeholder used to
    // say, ⭐ and it is in neither catalogue — ⭐ while gross margin itself **is** held,
    // as `gp_margin`.
    expect(COMPUTABLE.has('gross_margin')).toBe(false)
    expect(COMPUTABLE.has('gp_margin')).toBe(true)
    expect(uncomputable('gross_margin', COMPUTABLE, true)).toBe(true)
  })

  it('⭐⭐ stays quiet for a token this build holds', () => {
    // ⭐⭐ **The negative case, and the reason this file is not one test.** ⭐ A predicate
    // that always returns `true` passes every assertion above, ⭐ and a reader who is told
    // 「我算不了」 about `close` has been told something false — ⭐ which is the same species
    // of defect as the one being fixed, ⭐ pointed at the reader instead of the product.
    expect(uncomputable('gp_margin', COMPUTABLE, true)).toBe(false)
    expect(uncomputable('close', COMPUTABLE, true)).toBe(false)
    expect(uncomputable('ma20', COMPUTABLE, true)).toBe(false)
  })

  it('⭐ says nothing while the vocabulary is unknown', () => {
    // ⭐ A failed request must not accuse the reader of naming a metric that may well be
    // computable. ⭐ 「nothing claimed」 is not 「something false」.
    expect(uncomputable('gross_margin', COMPUTABLE, false)).toBe(false)
    // ⭐ Including for a token that genuinely is not computable — ⭐ we do not know that
    // yet, and a guess is not a fact.
    expect(uncomputable('revenue_yoy', new Set(), false)).toBe(false)
  })

  it('⭐ says nothing about an empty field', () => {
    // ⭐ An empty box is not yet a claim about a metric; the reader is still typing.
    expect(uncomputable('', COMPUTABLE, true)).toBe(false)
    expect(uncomputable('   ', COMPUTABLE, true)).toBe(false)
  })

  it('⭐ trims before deciding, because the field lets you type spaces', () => {
    expect(uncomputable('  gp_margin  ', COMPUTABLE, true)).toBe(false)
    expect(uncomputable('  gross_margin ', COMPUTABLE, true)).toBe(true)
  })

  it('⭐ an empty vocabulary means everything is uncomputable — and says so', () => {
    // ⭐⭐ **The `.BJ` case**, and it must come out the *opposite* way from the previous
    // test. ⭐ Measured: for `bj` both `daily` and `financial` are `pending`, ⭐ so zero of
    // the 32 are computable there. ⭐
    // ⭐ With the vocabulary *known* and empty, every real token is genuinely uncomputable,
    // ⭐ and saying so is the only true sentence available. ⭐ The pair of tests is the
    // point: ⭐ 「empty set」 means **「nothing is computable」** ⭐ and 「`known: false`」
    // means **「we do not know yet」** — ⭐ collapsing them would either accuse the reader
    // on a network error, ⭐ or stay silent on a venue with no data source.
    expect(uncomputable('close', new Set(), true)).toBe(true)
    expect(uncomputable('gp_margin', new Set(), true)).toBe(true)
    expect(uncomputable('close', new Set(), false)).toBe(false)
  })

  it('⭐ the datalist id is a stable constant, not a per-render id', () => {
    // ⭐ One `<datalist>` shared by every criterion row. ⭐ If this became a `useId`, each
    // row would get its own — ⭐ N copies of the same 32 tokens, ⭐ and `list` references
    // would point at whichever node React happened to keep.
    expect(METRIC_DATALIST_ID).toBe('alphacouncil-metric-vocabulary')
  })
})
