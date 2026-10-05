/**
 * ⭐⭐ **The kill criterion's metric: offered, and checked against what this build has.**
 * (spec 058)
 *
 * ## The defect this covers
 *
 * Measured before the endpoint existed:
 *
 * ```
 *   DecisionForm's placeholder      gross_margin
 *   gross_margin in either catalogue   no   ⭐ the real one is gp_margin「销售毛利率」
 *   domain check                  [a-z][a-z0-9_]* — shape only
 *   POST /api/v1/decisions        201, stored verbatim
 *   anything said at write time   nothing
 * ```
 *
 * ⇒ A reader who followed **the product's own example** got a kill criterion this build can
 * never evaluate, and the only place that would ever say so runs months later — where the
 * sentence blames the data, and the data is fine.
 *
 * ## ⭐⭐ Why most of these assertions are about the *notice*, not the list
 *
 * Spec 058 §六 #3: ⭐ **a `<datalist>` is not a `<select>`.** ⭐ 「the token appears in the
 * DOM」 passes just as well when the token is a suggestion the reader is free to ignore — ⭐
 * and ignoring it is precisely the failure being fixed. ⭐ So the load-bearing assertions
 * here are the ones that check the **sentence**, ⭐ and the list assertions exist only to
 * prove the vocabulary is *offered*.
 *
 * ⭐ The other thing this file must not drift into: ⭐ **making the notice block the write.**
 * `criterion_sentence` has a sentence state for a metric this build lacks, ⭐ and a
 * validation error here would make it unreachable from the interface — ⭐ deleting a
 * capability rather than fixing a defect.
 */

import { expect, test } from '@playwright/test'

import { instrumentDetail, metrics, quoteResult, routeApi } from './fixtures'

/** The token the product used to suggest, and the one it actually holds. */
const WRONG = 'gross_margin'
const RIGHT = 'gp_margin'

async function openForm(
  page: import('@playwright/test').Page,
  catalogue: ReturnType<typeof metrics> = metrics(),
): Promise<void> {
  await routeApi(page, {
    '/api/v1/metrics': catalogue,
    [`/api/v1/instruments/sh/600519`]: instrumentDetail(),
    '/api/v1/quote': quoteResult(1237.0, -0.0114),
    // ⭐ Recorded, so a test can prove the write went through even while the notice is up.
    'POST /api/v1/decisions': {
      id: '2026-10-05T01:00:00.000Z',
      market: 'sh',
      code: '600519',
      display: '600519.SH',
      action: 'buy',
      rationale: '渠道库存降到近三年低位',
      counter_evidence: '批价仍在下跌',
      kill_criteria: [{ metric: WRONG, operator: '<', threshold: 0.55, as_of: '2026-12-31' }],
      thesis_id: null,
    },
  })
  await page.goto('/#/i/sh/600519')
}

/** The metric input is the one carrying a datalist reference. */
function metricBox(page: import('@playwright/test').Page) {
  return page.locator('input[list]')
}

/**
 * ⭐ Scoped locators, and the reason is worth recording.
 *
 * The instrument page carries **three** submit buttons (the card form, the decision form,
 * and the decision form's own) and **two** date inputs (the card's 「数据截至（可选）」 and
 * the criterion's 「按截至哪天公布的数据」）. ⭐ So `button[type="submit"]` and
 * `input[type="date"]` both resolve to more than one element and Playwright's strict mode
 * refuses them — ⭐ the same failure `App.tsx` records for two identical headings.
 *
 * ⭐ **Scoped by accessible name**, because that is what distinguishes them *for a reader*
 * and not by DOM position, which would break the moment a section is reordered.
 */
function decisionSubmit(page: import('@playwright/test').Page) {
  return page.getByRole('button', { name: '记下来' })
}

function criterionDate(page: import('@playwright/test').Page) {
  return page.getByRole('textbox', { name: '按截至哪天公布的数据' })
}

test.describe('kill criterion · metric vocabulary', () => {
  test('⭐ offers the vocabulary and names it in Chinese', async ({ page }) => {
    await openForm(page)

    const box = metricBox(page)
    await expect(box).toHaveCount(1)

    // ⭐ Offered, not forced — a `<select>` could not contain `gross_margin` at all, ⭐ and
    // being able to write it is deliberate (the criterion_sentence `unknown` state).
    await box.fill(WRONG)

    // ⭐ The label is what a reader reads, so a bare token list would still be a private
    // vocabulary. ⭐ `gp_margin` must be offered under 「销售毛利率」 ⭐ because that pair is
    // the fact the whole defect turned on.
    //
    // ⚠️ **`hasText` would not find it**: ⭐ on an `<option>` the *text* is the label and the
    // token is the `value` attribute. ⭐ The first version of this assertion used
    // `filter({ hasText: RIGHT })` and found 0 ⭐ — ⭐ a green-looking locator that matches
    // nothing, which is the same species as `F-255` (a guard pointed at the wrong object).
    const offered = page.locator('datalist option[value="gp_margin"]')
    await expect(offered).toHaveCount(1)
    await expect(offered).toHaveText('销售毛利率')
  })

  test('⭐⭐ says 「我算不了」 for a token this build lacks, at write time', async ({ page }) => {
    await openForm(page)
    await metricBox(page).fill(WRONG)

    const notice = page.getByTestId('metric-uncomputable')
    await expect(notice).toBeVisible()
    await expect(notice).toContainText(WRONG)
    await expect(notice).toContainText('我算不了')
  })

  test('⭐⭐ does NOT say it for a token this build has', async ({ page }) => {
    await openForm(page)
    await metricBox(page).fill(RIGHT)

    // ⭐ The negative case, and the reason this file exists: ⭐ a form that always renders
    // the notice is indistinguishable from one that always renders it *correctly*, ⭐ and
    // the reader's trust in the notice is the whole value of showing it.
    await expect(page.getByTestId('metric-uncomputable')).toHaveCount(0)
  })

  test('⭐⭐ stays silent while the vocabulary is unknown', async ({ page }) => {
    await routeApi(page, {
      // ⭐ The request fails. ⭐ Nothing is claimed, so nothing is said — ⭐ and a notice
      // here would accuse the reader of naming a metric that may well be computable.
      '/api/v1/metrics': 500,
      [`/api/v1/instruments/sh/600519`]: instrumentDetail(),
      '/api/v1/quote': quoteResult(1237.0, -0.0114),
    })
    await page.goto('/#/i/sh/600519')
    await metricBox(page).fill(WRONG)

    await expect(page.getByTestId('metric-uncomputable')).toHaveCount(0)
    // ⭐ And the form still works: a picker that cannot load must not take the gate down.
    await expect(decisionSubmit(page)).toBeVisible()
  })

  test('⭐⭐ the notice does not block the write', async ({ page }) => {
    await openForm(page)
    await metricBox(page).fill(WRONG)
    await expect(page.getByTestId('metric-uncomputable')).toBeVisible()

    await page.getByPlaceholder(/渠道库存的回补/).fill('渠道库存降到近三年低位')
    await page.getByPlaceholder(/批价仍在下跌/).fill('批价仍在下跌，说明渠道还在去库存')
    await page.getByPlaceholder('0.55').fill('0.55')
    await criterionDate(page).fill('2026-12-31')

    // ⭐⭐ The load-bearing assertion. ⭐ Not an error, not a disabled button — ⭐ the
    // criterion is a fact the reader has and the product records it, ⭐ because
    // `criterion_sentence` has a sentence state for exactly this case and refusing here
    // would make it unreachable (spec 058 §2.1).
    const submit = decisionSubmit(page)
    await expect(submit).toBeEnabled()

    // ⭐ **Assert the payload, not the click.** ⭐ The first version clicked and then
    // asserted the notice was *still* on screen, ⭐ and it failed — ⭐ because the form
    // resets after a successful write, ⭐ which is correct. ⭐ So the version that was
    // actually testing 「did the write go through」 was testing 「did the form not clear」,
    // ⭐ and it would have passed on a product that recorded nothing at all.
    // ⇒ What matters is that the token reaches the server **unaltered**.
    const [request] = await Promise.all([
      page.waitForRequest((r) => r.url().endsWith('/api/v1/decisions') && r.method() === 'POST'),
      submit.click(),
    ])
    const body = request.postDataJSON()
    expect(body.kill_criteria[0].metric).toBe(WRONG)

    // ⭐ And the form clearing afterwards is the receipt: the write completed.
    await expect(page.getByTestId('metric-uncomputable')).toHaveCount(0)
  })

  test('⭐ a venue with no data source says so, and offers nothing', async ({ page }) => {
    await routeApi(page, {
      // ⭐ `.BJ` measured: `daily` and `financial` are both `pending` — ⭐ no provider
      // declares either for that venue, ⭐ so zero of the 32 are computable there.
      '/api/v1/metrics': metrics({ market: 'bj', metrics: [], unavailable: [RIGHT] }),
      [`/api/v1/instruments/bj/430047`]: instrumentDetail(),
      '/api/v1/quote': quoteResult(18.5, 0.002),
    })
    await page.goto('/#/i/bj/430047')

    await metricBox(page).fill(RIGHT)
    // ⭐ **Not** a list of 24 things that would never resolve. ⭐ The honest answer is that
    // nothing here can be watched, which is a fact about the data layer ⭐ and the sentence
    // this reader most needs.
    await expect(page.getByTestId('metrics-empty')).toBeVisible()
    await expect(page.getByTestId('metrics-empty')).toContainText('一个指标都算不了')
    await expect(page.locator('datalist option')).toHaveCount(0)
  })

  test('⭐ the placeholder is a metric the product actually holds', async ({ page }) => {
    await openForm(page)
    // ⭐⭐ On the *suggested* string, not on the list. ⭐ The list can contain anything
    // computable; ⭐ the placeholder is what a reader copies when they are not thinking,
    // ⭐ and it is the string that produced the defect.
    await expect(metricBox(page)).toHaveAttribute('placeholder', RIGHT)
  })
})
