/**
 * ⭐⭐ **「这个市场我算不了什么」—— 一句读者能看见的边界。** (spec 059)
 *
 * ## Why this exists, measured
 *
 * ```
 *   GET /api/v1/capabilities   exists, returns 15 cells of dataset x market
 *   grep getCapabilities frontend/src   only DemoBanner's `is_demo`
 *   ⭐⭐ the matrix itself has no consumer at all
 * ```
 *
 * ⭐⭐ **And the repository has already written the rule this violates.** `UniversePage`'s
 * footer says it, and `pool.spec.ts:77` asserts that very sentence:
 *
 * > 这一页只显示事实 … ⭐ **一个读者看不见的边界不是边界**
 *
 * ⇒ So the product had a working endpoint describing exactly what it can see, ⭐ and the
 * one reader harmed by that silence is the one following a **`.BJ`** instrument: measured,
 * `daily` and `financial` are **both `pending`** for `bj`, ⭐ so **not one metric is
 * computable there** — ⭐⭐ and until this component existed, not one word of that reached
 * the screen.
 *
 * ⭐ This is spec 058's other half. 058 says 「你写的那个指标我算不了」;
 * ⭐ 059 says 「**这个市场我整体什么都算不了**」 — ⭐ and 058's `.BJ` branch had already
 * measured the second half while the interface said only the first.
 *
 * ## ⭐⭐ Why it renders **only** when something is missing
 *
 * ⭐ **This is the decision the whole component turns on**, and it was made against my own
 * instinct. A permanent 「everything is available」 line on every page is:
 *
 * - ⭐ **noise**, because for `sh`/`sz` every cell is `usable` ⭐ — measured — so it would
 *   be the same sentence on essentially every page a reader ever opens;
 * - ⭐⭐ **and it teaches people to ignore the one thing that matters.** ⭐ This project
 *   shipped a **permanent banner** in spec 057 (the demo library), ⭐ so it has already
 *   spent some of the reader's patience on a strip that never changes. ⭐ A second
 *   always-on strip would spend the rest.
 *
 * ⇒ **The reader's harm is silence when something is missing.** ⭐ Nobody is harmed by a
 * page that does not announce its own completeness, ⭐ and 「现在我都能算」 is a *claim of
 * completeness* ⭐ — which becomes false silently the moment a provider drops, ⭐ and the
 * word that keeps it honest is 「现在」. ⭐ So the block appears on a boundary and vanishes
 * when there is none.
 *
 * ## ⭐⭐ What it must never say (red line 8)
 *
 * `CapabilityCell` carries `sources: [{name, healthy, cooldown_remaining_s}]`.
 *
 * ⭐⭐ **None of that is rendered, and that is the red-line decision.** ⭐ A 「数据源 42 秒后
 * 恢复」 display is one step from 「过会儿再试」, ⭐ and 「过会儿再试」 **is a nudge** — ⭐
 * 红线 8 forbids exactly that. ⭐ The reader's question is 「我能不能算这个」, ⭐ not 「运维
 * 面板今天怎么样」. ⇒ Only `state` reaches the screen. ⭐ `market-notice.spec.ts` asserts the
 * absence of provider names, ⭐ because a test that only asserts the text is present passes
 * just as well on a page stuffed with them.
 *
 * ⭐ **No ordering.** ⭐ Declared order, never 「importance」 — ⭐ same reason spec 058's
 * token list is sorted by token: ⭐ a list ordered by usefulness is a recommendation list
 * with a technical vocabulary.
 *
 * ## ⭐⭐ A `⭐` leaked into rendered copy, and the second fix was the same mistake
 *
 * The first draft of the closing paragraph was
 * `⭐ 写下来的判据照记，⭐ 到期时…` ⭐⭐ **with the stars in the JSX** — ⭐ so every reader of
 * a `.BJ` instrument saw them. ⭐ Nothing caught it on purpose: ⭐ an assertion for
 * 「我算不了」 failed on a **substring**, ⭐ and ⭐⭐ **reading the actual rendered text is
 * what showed them.**
 *
 * ⭐⭐ **The repair then repeated the defect.** ⭐ The explanation of the leak was written
 * *inside the same `<p>` ⭐ — ⭐ where it also renders ⭐ — ⭐⭐ so the second draft showed a
 * reader even more stars and one English paragraph about markup. ⭐ **The stars are for
 * source comments; ⭐⭐ they are commentary about a sentence, never part of one.**
 *
 * ⇒ `test_the_author_markup_never_reaches_the_reader` asserts that on purpose now, ⭐
 * because a guard that only exists because a substring assertion happened to fail ⭐ is not
 * a guard, ⭐ it is a coincidence with a test around it.
 */

import { useCallback } from 'react'

import { getCapabilities, type CapabilityCell } from './api'
import { useResource } from './useResource'

/**
 * ⭐ What the reader is told, and **nothing more**.
 *
 * ⭐ `pending` and `candidates` both mean 「I cannot serve this」, ⭐ and they mean it for
 * different reasons: ⭐ `pending` is 「not wired yet」 ⭐ while `candidates` is 「the sources
 * that might」. ⭐ Measured, no cell is `candidates` today. ⭐⭐ **Both render the same
 * sentence on purpose** — ⭐ the reader cannot act on the difference, ⭐ and `candidates`
 * means 「a provider says it *might*」, ⭐ which is not a promise ⭐ and rendering it as one
 * would be the exact defect spec 058 fixed.
 */
export function CapabilityNotice({ market }: { market: string }) {
  const capabilities = useResource<{ capabilities: CapabilityCell[] }>(
    useCallback(() => getCapabilities(), []),
    [],
    useCallback((_: unknown) => '无法读取能力矩阵。', []),
  )

  const cells = capabilities.data?.capabilities ?? []
  const missing = cells.filter(
    (cell) => cell.market === market && cell.state !== 'usable',
  )

  // ⭐ Nothing missing, or nothing known yet. ⭐ Both render nothing: ⭐ 「没问出来」 is not
  // 「都齐了」, ⭐ so a failed request must not be read as a clean bill of health — ⭐ the
  // same rule as `DemoBanner` and `DecisionForm`'s vocabulary.
  if (missing.length === 0) return null

  return (
    <section
      className="mt-4 border-l-2 border-l-[color:var(--color-warn)] py-1 pl-2.5"
      data-testid="capability-notice"
      // ⭐ `role="status"` not `role="alert"`: ⭐ this is a standing fact about the market,
      // ⭐ not something to act on now. ⭐ An alert announces itself to a screen reader on
      // ⭐ every render, ⭐ and this block re-renders whenever the price ticks.
      role="status"
    >
      <h2 className="type-meta font-normal caps text-ink-faint">这里我看不到什么</h2>
      <p className="mt-1 type-prose text-ink-soft">
        {missing.length === cells.filter((c) => c.market === market).length ? (
          <>
            这只票所在的
            <strong className="text-ink">{MARKET_LABEL[market] ?? market}</strong>
            市场，我一个指标都算不了。
          </>
        ) : (
          <>
            这只票所在的
            <strong className="text-ink">{MARKET_LABEL[market] ?? market}</strong>
            市场，我算不了这些：
            {missing.map((cell) => (
              <span key={`${cell.market}-${cell.dataset}`}>
                {' '}
                {DATASET_LABEL[cell.dataset] ?? cell.dataset}
              </span>
            ))}
            。
          </>
        )}
      </p>
      <p className="mt-1 type-meta text-ink-faint">
        写下来的判据照记，到期时它会照实说「不在我们能算的指标里」。
      </p>
    </section>
  )
}

/** ⭐ Venue names, in the reader's words. ⭐ Not a market picker — ⭐ just a label. */
const MARKET_LABEL: Record<string, string> = {
  sh: '沪',
  sz: '深',
  bj: '京',
}

/**
 * ⭐ Dataset names, in the reader's words.
 *
 * ⭐ **Only the ones a reader could recognise.** ⭐ `adj_factor` has no reader-facing
 * meaning, ⭐ so it is deliberately **absent** rather than shown as a bare token — ⭐ the
 * same rule as spec 058's metric labels: ⭐ a token the reader cannot interpret is noise,
 * ⭐ and a *missing* boundary is worse than an ugly one. ⭐ When a token has no label the
 * component falls back to the raw name, ⭐ which is honest and obviously unpolished.
 */
const DATASET_LABEL: Record<string, string> = {
  daily: '日线',
  financial: '财报',
}
