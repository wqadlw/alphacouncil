/**
 * ⭐ The two pieces of the metric vocabulary's logic that are **pure**, and therefore the
 * two pieces that can be tested without a browser. (spec 058)
 *
 * ## ⭐ Why this file exists rather than living inside `DecisionForm.tsx`
 *
 * Two reasons, and the second is the one that matters.
 *
 * 1. ⭐ `only-export-components` (oxlint) objects to a `.tsx` module exporting a
 *    non-component, ⭐ and the usual workarounds — a `// eslint-disable`, or a test that
 *    imports the component — both cost something.
 * 2. ⭐⭐ **The mutation check needs somewhere it can measure.** `uncomputable()` decides
 *    whether the reader is told 「我算不了」, ⭐ and ⭐ **a browser test for it is a browser
 *    test that can be measured against the wrong bundle** (`F-253`). ⭐ Measured: the
 *    mutation script's P2 came back VOID 「build failed」 three runs running ⭐ while the
 *    identical mutation built cleanly on its own, ⭐ because the *previous* mutation's
 *    `vite preview` was still holding `dist/`. ⭐ ⇒ **A guard whose verification is
 *    unreliable should not be the only guard.** ⭐ This function is pure, ⭐ so its
 *    behaviour is pinned here and its mutation is killed in milliseconds.
 *
 * ⭐ The E2E still exists and still matters — it proves the sentence reaches the screen,
 * ⭐ which no unit test can see. ⭐ Two layers, ⭐ because they fail differently.
 */

/**
 * The `<datalist>`'s id.
 *
 * ⭐ A constant, not a `useId`. ⭐ `useId` exists for ids that must be unique *per rendered
 * element*, ⭐ and a `<datalist>` referenced by `list` wants **one shared node** — ⭐ N
 * criteria rows pointing at N copies of the same 32 tokens is 32 copies of one fact.
 */
export const METRIC_DATALIST_ID = 'alphacouncil-metric-vocabulary'

/**
 * ⭐ Should the reader be told that this build cannot compute the token they wrote?
 *
 * Three inputs, and ⭐ **the third is the one that is easy to get wrong**: when the
 * vocabulary has not arrived, the answer is **`false`** — ⭐ not 「assume unknown」. ⭐ A
 * failed request must never produce a notice accusing someone of naming a metric that may
 * well be computable, ⭐ and 「nothing claimed」 is not 「something false」. ⭐ Same rule as
 * `DemoBanner`: a blank means no claim was made, not that the safe answer is yes.
 *
 * ⭐ A blank token is also `false`, ⭐ because an empty field is not yet a claim about a
 * metric — the reader is still typing.
 */
export function uncomputable(
  token: string,
  computable: ReadonlySet<string>,
  vocabularyKnown: boolean,
): boolean {
  const trimmed = token.trim()
  return vocabularyKnown && trimmed !== '' && !computable.has(trimmed)
}
