/**
 * ⭐⭐ **「这里我看不到什么」—— the boundary, on the page where the reader commits.**
 * (spec 059)
 *
 * ## Why it exists, measured
 *
 * ```
 *   GET /api/v1/capabilities   exists, 15 cells of dataset x market
 *   grep getCapabilities frontend/src   only DemoBanner's `is_demo`
 *   ⭐⭐ the matrix itself had no consumer at all
 * ```
 *
 * ⭐ And the repository had already written the rule it violates — `pool.spec.ts:77` asserts
 * 「一个读者看不见的边界不是边界」.
 *
 * ## ⭐⭐ The two ways this file could pass while doing nothing
 *
 * ⭐ **Spec 059 §五 lists both, and both are assertions in here:**
 *
 * 1. ⭐⭐ **Rendering `sources`.** ⭐ A test that asserts 「the notice is present」 passes
 *    just as well on a page listing `eastmoney · healthy · cooldown 42s`, ⭐⭐ and that is one
 *    nudge away from 「过会儿再试」 — ⭐ 红线 8. ⇒ **`test_the_provider_names_never_reach_the_page`**
 *    is a negative assertion, ⭐ and it is the load-bearing one.
 * 2. ⭐⭐ **Never rendering at all.** ⭐ Every default fixture in this repo is `sh`, ⭐ and
 *    `sh` has **no** missing cells, ⭐ so a component that returned `null` unconditionally
 *    would pass every `sh` assertion. ⇒ **`test_a_venue_with_no_data_source_says_so` builds a
 *    `.BJ` case on purpose** — ⭐⭐ without it, this component would be untested while
 *    looking tested.
 */

import { expect, test } from '@playwright/test'

import {
  capabilities,
  capabilityMatrix,
  cooldownMatrix,
  instrumentDetail,
  quoteResult,
  routeApi,
} from './fixtures'

/** ⭐ `.BJ` — the only venue where measured cells are not `usable`. */
const BJ = 'bj'

async function openInstrument(page: import('@playwright/test').Page, market: string): Promise<void> {
  await routeApi(page, {
    [`/api/v1/instruments/${market}/600519`]: instrumentDetail(),
    '/api/v1/quote': quoteResult(1237.0, -0.0114),
  })
  await page.goto(`/#/i/${market}/600519`)
}

test.describe('capability boundary', () => {
  test('⭐⭐ says so on a venue with no data source at all', async ({ page }) => {
    // ⭐⭐ The case that does not happen by accident. ⭐ Measured: `daily` and `financial`
    // are both `pending` for `bj`, ⭐ so **not one** of the 32 metrics is computable there.
    await routeApi(page, { '/api/v1/capabilities': capabilities({}, BJ) })
    await openInstrument(page, BJ)

    const notice = page.getByTestId('capability-notice')
    await expect(notice).toBeVisible()
    // ⭐ The whole-venue case gets its own sentence ⭐ rather than a list of five things,
    // ⭐ because 「一个指标都算不了」 is a different fact from 「我算不了这些」. ⭐
    // ⭐ Not 「我算不了」: ⭐ that is not a substring of it — ⭐ the 「一个指标都」 sits in
    // ⭐ between the two — ⭐ and an assertion written for a shorter phrase than the one
    // ⭐ that renders is an assertion that documents the wish rather than the product.
    await expect(notice).toContainText('一个指标都算不了')
  })

  test('⭐⭐ the author markup never reaches the reader', async ({ page }) => {
    // ⭐⭐ **This exists because of a leak, and the leak did not fail a test.**
    //
    // ⭐ The first draft of this component's closing paragraph read
    // `⭐ 写下来的判据照记，⭐ 到期时…` — ⭐⭐ **with the stars in the JSX**, ⭐ so every reader
    // of a `.BJ` instrument saw them. ⭐ Nothing caught it: ⭐ an assertion for 「我算不了」
    // failed on a substring, ⭐ and ⭐⭐ reading the actual text is what revealed them.
    // ⭐⭐ **The repair repeated the defect** — ⭐ the explanation was written inside the
    // same `<p>`, ⭐ where it also renders.
    //
    // ⇒ `⭐` and `✨` are this repository's markers for *commentary about* a sentence. ⭐⭐
    // They belong in `//` and in docstrings, ⭐ never in a text node. ⭐ This asserts it
    // across the whole page, ⭐ because the failure is invisible in every other assertion.
    await routeApi(page, { '/api/v1/capabilities': capabilities({}, BJ) })
    await openInstrument(page, BJ)

    // ⭐⭐⭐ **The wait, and without it this test asserted nothing at all.**
    //
    // ⭐ `openInstrument` returns right after `goto`, ⭐ and the notice only exists **after
    // ⭐ `/api/v1/capabilities` has answered** ⭐ — ⭐ so `document.body.textContent` was
    // ⭐ read off a page that had not rendered the block yet. ⭐⭐ The mutation 「put a `⭐`
    // ⭐ in the JSX」 therefore **survived**: ⭐⭐ it leaked to a reader and the guard was
    // ⭐ green, ⭐⭐ because the guard was reading a document that did not yet contain the
    // ⭐ thing it was guarding. ⭐ **A negative assertion about an element that may not be
    // ⭐ there yet is vacuously true** — ⭐ and vacuous looks exactly like passing.
    //
    // ⭐⭐ **The same file's other test was right for a reason nobody wrote down**:
    // ⭐ `the provider names never reach the page` waits for visibility before it reads,
    // ⭐ which is the only reason its mutation died. ⭐ One test waiting and one not, ⭐ in
    // ⭐ the same describe block, ⭐⭐ and the difference is the entire verdict.
    await expect(page.getByTestId('capability-notice')).toBeVisible()

    // ⭐⭐⭐ **`textContent`, and `innerText` was the second reason this guard did not work.**
    //
    // ⭐ An earlier draft used `locator('body').innerText()`. ⭐⭐ The mutation was verified
    // ⭐ to land in the served bundle, ⭐ and a DOM probe confirmed the star **was in the
    // ⭐ document** (`textContent`, code point `11088` = U+2B50) ⭐ — ⭐⭐ and the test passed
    // ⭐ anyway. ⭐ `innerText` is rendering-aware and `textContent` is not; ⭐ U+2B50 has
    // ⭐ `Emoji_Presentation=Yes`, ⭐⭐ so **`innerText` is the wrong instrument for 「is this
    // ⭐ character in the document」** — ⭐ its answer depends on font fallback. ⭐ A guard
    // ⭐ silently blind to a whole class of character is worse than no guard, ⭐ because it
    // ⭐ reports green.
    const body = await page.evaluate(() => document.body.textContent ?? '')
    expect(body).not.toContain('⭐')
    expect(body).not.toContain('✨')
    // ⭐ And no English leaked either, ⭐ which is the other half of the second draft's
    // ⭐ failure: a paragraph of commentary about markup, rendered to the reader.
    expect(body).not.toMatch(/draft|mutation|leak/i)
  })

  test('⭐ renders nothing when nothing is missing', async ({ page }) => {
    await openInstrument(page, 'sh')

    // ⭐ Measured: every `sh` cell is `usable`, ⭐ so the honest rendering is silence.
    // ⭐⭐ This is the assertion that makes the component a *boundary* rather than a
    // banner — ⭐ a permanent 「everything is fine」 strip on every page would be noise, ⭐
    // and it would spend patience this product already spent on the demo banner (057).
    await expect(page.getByTestId('capability-notice')).toHaveCount(0)
  })

  test('⭐⭐ the provider names never reach the page', async ({ page }) => {
    // ⭐⭐⭐ **This is the assertion the mutation check forced into existence, and the
    // reason matters more than the code.**
    //
    // ⭐ The first version of this test used the `bj` fixture, ⭐ and the 「render the
    // provider names」 mutation **survived**. ⭐⭐ Reading
    // `providers/router.py::capability_matrix` explains why: ⭐ a **`pending`** cell carries
    // `sources: []`, ⭐⭐ because no provider declares it for that venue — ⭐ so there was
    // nothing to leak, ⭐ and my negative assertion was passing **for the wrong reason**.
    //
    // ⭐⭐ **A guard that cannot fail is not a guard.** ⭐ And the reachable case is
    // `candidates`, ⭐ where every source is `healthy: false` with a
    // `cooldown_remaining_s` — ⭐⭐ which is **ordinary use**: ⭐ a rate-limited provider,
    // ⭐ i.e. the moment a reader is most likely to be looking. ⭐ And `reason` there is
    // 「declaring sources are all in cooldown」 ⭐⭐ — a countdown to 「过会儿再试」, ⭐⭐ which
    // is the nudge 红线 8 forbids.
    await routeApi(page, {
      '/api/v1/capabilities': { ...capabilities(), capabilities: cooldownMatrix() },
    })
    await openInstrument(page, 'sh')

    // ⭐ And the notice does appear for `candidates` ⭐ — it is a limit like any other ⭐ —
    // ⭐ so this test is not vacuously true because the block stayed hidden.
    const notice = page.getByTestId('capability-notice')
    await expect(notice).toBeVisible()

    // ⭐ `textContent` for the same reason as the markup test above: ⭐ `innerText` is
    // rendering-aware, ⭐ and a guard that silently misses characters reports green.
    const body = await page.evaluate(() => document.body.textContent ?? '')
    for (const provider of ['eastmoney', 'tencent', 'baostock']) {
      expect(body).not.toContain(provider)
    }
    expect(body).not.toMatch(/cooldown/i)
    expect(body).not.toMatch(/healthy/)
    // ⭐ And the server's own `reason` is an operator sentence ⭐ — 「declaring sources are
    // all in cooldown」 describes this codebase's plumbing, ⭐ not the reader's situation.
    expect(body).not.toMatch(/in cooldown|not wired yet/)
    // ⭐⭐ **And no countdown in any form.** ⭐ 「42 秒后恢复」 is the nudge; ⭐ the reader
    // is entitled to know the market cannot serve this now, ⭐ and to nothing about when
    // ⭐ that might change.
    expect(body).not.toMatch(/42|秒后|恢复/)
  })

  test('⭐⭐ a cooldown is stated as a limit, never as a retry hint', async ({ page }) => {
    await routeApi(page, {
      '/api/v1/capabilities': { ...capabilities(), capabilities: cooldownMatrix() },
    })
    await openInstrument(page, 'sh')

    const text = await page.getByTestId('capability-notice').innerText()
    // ⭐⭐ **The distinction this whole component exists to keep straight.** ⭐ 「我算不了」
    // is a fact about the market. ⭐ 「42 秒后」 is a fact about a circuit breaker, ⭐ and the
    // only action it suggests is 「过会儿再试」 — ⭐⭐ a nudge toward more activity, which is
    // exactly what 红线 8 rules out. ⭐ The first is the reader's; the second is ours.
    expect(text).toContain('我算不了')
    expect(text).not.toMatch(/秒|稍后|重试|过会|再试|恢复/)
  })

  test('⭐⭐ does not blame a provider or promise a retry', async ({ page }) => {
    await routeApi(page, { '/api/v1/capabilities': capabilities({}, BJ) })
    await openInstrument(page, BJ)

    const text = await page.getByTestId('capability-notice').innerText()
    // ⭐ 红线 13: the product does not reassure, and does not invite a retry.
    expect(text).not.toMatch(/稍后|重试|过会|再试/)
    // ⭐⭐ Nor does it promise the gap will close. ⭐ A `.BJ` provider is not scheduled,
    // ⭐ so 「以后会有的」 is an event with no date — ⭐ the same defect as 058's
    // 「等到我能算为止」, ⭐ and it would pass every assertion above.
    expect(text).not.toMatch(/会有的|将来|以后|即将/)
  })

  test('⭐⭐ says the criterion is still recorded', async ({ page }) => {
    // ⭐ Because the sentence is a boundary, **not a warning**. ⭐ A reader who is told
    // 「这个市场我算不了」 and nothing else would reasonably conclude their notes are lost.
    // ⭐ They are not: `criterion_sentence` has the 「不在我们能算的指标里」 state, ⭐ which is
    // 058's whole point — the record is kept and reports the reason when it comes due.
    await routeApi(page, { '/api/v1/capabilities': capabilities({}, BJ) })
    await openInstrument(page, BJ)

    await expect(page.getByTestId('capability-notice')).toContainText('照记')
  })

  test('⭐⭐ renders nothing when the matrix cannot be read', async ({ page }) => {
    // ⭐⭐ 「没问出来」 is not 「都齐了」. ⭐ A failed request must not be read as a clean bill
    // of health ⭐ — and it certainly must not be read as 「你算不了」, ⭐ which would be an
    // accusation the product cannot support. ⭐ Same rule as `DemoBanner` and the metric
    // vocabulary: nothing claimed is not something false.
    await routeApi(page, { '/api/v1/capabilities': 500 })
    await openInstrument(page, BJ)

    await expect(page.getByTestId('capability-notice')).toHaveCount(0)
    // ⭐ And the page still works — a boundary that cannot be checked must not take the
    // instrument page down with it.
    await expect(page.getByTestId('app-shell')).toBeVisible()
  })

  test('⭐ a partially-missing venue names what it cannot do', async ({ page }) => {
    // ⭐⭐ The case `sh` never reaches, ⭐ so it has to be built: **one** dataset pending and
    // the rest usable. ⭐ Measured, no venue is in this state today ⭐ — which is exactly why
    // it needs a fixture: ⭐ a branch that no real market takes is a branch nobody has run.
    const mixed = capabilityMatrix('sh').map((cell) =>
      cell.dataset === 'financial' ? { ...cell, state: 'pending', sources: [], reason: 'not wired' } : cell,
    )
    await routeApi(page, {
      '/api/v1/capabilities': { ...capabilities(), capabilities: mixed },
    })
    await openInstrument(page, 'sh')

    const notice = page.getByTestId('capability-notice')
    await expect(notice).toBeVisible()
    await expect(notice).toContainText('财报')
    // ⭐ **Not** the whole-venue sentence, ⭐ because four of five datasets still work ⭐ and
    // 「一个指标都算不了」 would be false.
    await expect(notice).not.toContainText('一个指标都算不了')
  })

  test('⭐ the heading is a real heading, for someone navigating by them', async ({ page }) => {
    // ⭐ `InstrumentPage`'s own comment says the headings stay real heading elements ⭐ and
    // that a section which is not a heading is invisible to someone navigating by them.
    // ⭐⭐ A boundary announced in a `<div>` is a boundary that a screen-reader user never
    // meets ⭐ — ⭐ which would make this another 「看得见的边界」 for sighted users only.
    await routeApi(page, { '/api/v1/capabilities': capabilities({}, BJ) })
    await openInstrument(page, BJ)

    await expect(
      page.getByRole('heading', { name: '这里我看不到什么' }),
    ).toBeVisible()
  })
})
