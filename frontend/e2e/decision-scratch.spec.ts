import { expect, test } from '@playwright/test'
import { instrumentDetail, quoteResult, routeApi } from './fixtures'

/**
 * 「这条是试验记录」 on the instrument page (spec 060).
 *
 * What this spec holds fixed is the *screen half* of a promise the backend tests
 * hold the other half of: the record stays on the page, labelled, and the label
 * says what the mark does rather than what the record is. A row that said
 * 「假的」 would be the product grading the reader's own writing, which red line
 * 11 refuses; a row that simply vanished would be deleting it.
 */

const DECISION_ID = '2026-09-20T01:00:00.000Z'

/** The decision as the server answers after the mark was written. */
function markedDecision(scratch: boolean) {
  const detail = instrumentDetail()
  const decision = (detail.decisions as Record<string, unknown>[])[0]
  return { ...decision, scratch }
}

test.beforeEach(async ({ page }) => {
  await routeApi(page, {
    'GET /api/v1/instruments/sh/600519': instrumentDetail(),
    'GET /api/v1/instruments/sh/600519/quote': quoteResult(1237.0, -0.0114),
    'POST /api/v1/decisions': { detail: 'e2e does not record decisions' },
    'GET /api/v1/decisions': [],
  })
})

test.describe('试验记录（spec 060）', () => {
  test('the unmarked decision offers the mark, and says what it does', async ({
    page,
  }) => {
    await page.goto('/#/i/sh/600519')

    // The wording is the contract: it names the consequence (excluded from the
    // retrospective), not a verdict on the record (a trial, not "fake").
    const mark = page.getByRole('button', { name: '这条是试验记录，不进复盘结论' })
    await expect(mark).toBeVisible()
    await expect(page.getByText('记录本身一直留着')).toBeVisible()
    await expect(page.getByText('试验记录', { exact: true })).toHaveCount(0)
  })

  test('pressing it labels the row and keeps the row on the page', async ({ page }) => {
    let posted: unknown = null
    await routeApi(page, {
      [`POST /api/v1/decisions/${DECISION_ID}/scratch`]: markedDecision(true),
    })
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/scratch')) {
        posted = r.postDataJSON()
      }
    })

    await page.goto('/#/i/sh/600519')
    await page.getByRole('button', { name: '这条是试验记录，不进复盘结论' }).click()

    // The row survives, labelled. This is the whole point of the feature.
    await expect(page.getByText('试验记录', { exact: true })).toBeVisible()
    await expect(page.getByText('毛利率连续三年高于 90%').first()).toBeVisible()

    // The button becomes the un-mark, so the toggle is two-way on screen.
    await expect(
      page.getByRole('button', { name: '取消「试验记录」' }),
    ).toBeVisible()

    // And the request carried the mark and nothing else. A body with a `reason`
    // or a `tag` is the road from a purpose-limited mark to a self-score.
    expect(posted).toEqual({ marked: true })
  })

  test('a failed write does not claim the record was marked', async ({ page }) => {
    await routeApi(page, {
      // A bare number is the status: 500, so `request` rejects and the row's
      // catch branch is what is under test. Answering 200 with an error-shaped
      // body would have exercised nothing here.
      [`POST /api/v1/decisions/${DECISION_ID}/scratch`]: 500,
    })

    await page.goto('/#/i/sh/600519')
    await page.getByRole('button', { name: '这条是试验记录，不进复盘结论' }).click()

    // The label must not appear, and the page must say so rather than leaving
    // the reader to believe a press that went nowhere.
    await expect(page.getByText('没有写进去，再按一次。')).toBeVisible()
    await expect(page.getByText('试验记录', { exact: true })).toHaveCount(0)
  })
})
