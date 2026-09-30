/**
 * What the today page does with a criterion's sentence — which is **presentation only**.
 *
 * ## ⭐ The sentence moved to the server, and this file is what was left behind
 *
 * Up to spec 044 the five sentences lived here, in TypeScript. A notification needs the
 * same sentence in a place with no browser in it, and there were only two available moves:
 *
 * - rewrite it in Python — two homes, and they drift;
 * - send the bare state (`crossed`) — that is a debug line, not a reminder.
 *
 * So `backend/src/alphacouncil/domain/criterion_sentence.py` owns the wording now, and
 * `/api/v1/today` ships it as `verdict` on every attention item. ⭐ The pay-off is not
 * tidiness: **the page and the notification can no longer say different things**, and that
 * is structural rather than a convention somebody has to remember.
 *
 * ⭐ Which leaves exactly the two things that genuinely belong to a browser: the accent
 * colour, and whether the row is styled as 「你今天就能据此行动」. Both arrive as flags for
 * the same reason — ⭐ the styling and the sentence say the same thing, so deriving one
 * from the other would let them disagree.
 *
 * ## ⭐ Why there is no fallback sentence here
 *
 * The first draft kept a `criterionVerdict(null)` branch returning 「取不到这个代码的日线」,
 * because `metric` is `null` when the server could not read any bars. ⭐ That is a second
 * home for one of the five, and it is exactly the one case a notification cannot render:
 * the notification has no `metric` object at all, only the sentence.
 *
 * So the server puts `verdict` on the **attention item** rather than on the metric — ⭐ a
 * property of 「这件事需要你处理」, not of 「这个指标」 — and it is always present.
 */

import type { AttentionItem } from './api'

/**
 * The two things this page needs, straight off the payload.
 *
 * ⭐ `undefined` is accepted alongside `null` on purpose. The server sends `metric: null`
 * when it has no bars, and the type says so — but a payload from a build that predates
 * spec 040 simply has no such key, and `metric.state` on `undefined` throws **during
 * render**, which white-screens the one page the reader opens to find out what went wrong.
 * ⭐ Every other 「we don't know」 in this product costs the reader a sentence; that one
 * would have cost them the page.
 */
export interface CriterionPresentation {
  /** The clause, verbatim from the server. Never re-derived here. */
  verdict: string
  /** ⭐ `true` only when the comparison actually ran. Drives the row's accent colour. */
  crossed: boolean
  /** ⭐ Whether the reader is being told something they could act on today. */
  adjudicable: boolean
}

export function criterionPresentation(item: AttentionItem): CriterionPresentation {
  const metric = item.metric

  return {
    verdict: item.verdict,
    // ⭐ Read off the state rather than assumed, so a state the server adds cannot render
    // as 「not crossed」 by omission — ⭐ and `undefined` falls here, which is the case
    // above.
    crossed: metric?.state === 'crossed',
    adjudicable: item.adjudicable,
  }
}
