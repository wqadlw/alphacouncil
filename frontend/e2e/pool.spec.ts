import { expect, test } from '@playwright/test'
import { poolQuotes, poolRows, recordedEvent, routeApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await routeApi(page, {
    'GET /api/v1/watchlist': poolRows(),
    'GET /api/v1/watchlist/quotes': poolQuotes(),
    'POST /api/v1/watchlist': recordedEvent(),
    'POST /api/v1/watchlist/remove': recordedEvent(),
  })
})

test.describe('关注池（spec 004 + 红线 9/13）', () => {
  test('rows carry the four states honestly: priced-but-stale and refused differ', async ({
    page,
  }) => {
    await page.goto('/#/pool')

    await expect(page.getByText('600519.SH')).toBeVisible()
    await expect(page.getByText('1237.00')).toBeVisible()
    await expect(page.getByText('−1.14%')).toBeVisible()
    // A stale value says so out loud — an old price shown as current is a
    // quiet lie (spec 004 AC-5).
    await expect(page.getByText('旧', { exact: false })).toBeVisible()

    // The refused row says "the fetch failed", not "there is no data".
    await expect(page.getByText('取数失败')).toBeVisible()
  })

  test('an empty reason keeps the submit disabled and names the rule', async ({ page }) => {
    await page.goto('/#/pool')

    const ticker = page.locator('form input').first()
    const reason = page.locator('form input').nth(1)
    await expect(ticker).toHaveValue('')
    await expect(reason).toHaveValue('')

    const submit = page.locator('form button[type="submit"]')
    await expect(submit).toBeDisabled()
    await expect(page.getByText('这是唯一不能跳过的一步')).toBeVisible()

    await ticker.fill('600036')
    await expect(submit).toBeDisabled() // reason still missing

    await reason.fill('毛利率连续三年高于 90%')
    await expect(submit).toBeEnabled()
  })

  test('a recorded write echoes the receipt, never a fabricated success', async ({ page }) => {
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('600036')
    await page.locator('form input').nth(1).fill('ROE 长期 15%+')
    await page.locator('form button[type="submit"]').click()

    await expect(page.getByText(/已记录（事件 #99）/)).toBeVisible()
  })

  test('removing says the record stays (append-only is the product promise)', async ({
    page,
  }) => {
    await page.goto('/#/pool')

    await page.getByRole('button', { name: '不再关注' }).first().click()

    await expect(page.getByText(/记录没有被删除/)).toBeVisible()
  })

  test('the page states its own no-returns rule（红线 9）', async ({ page }) => {
    // The red line forbids a returns *metric*; the footer states the rule in
    // words, and its presence is what this assertion pins.
    await page.goto('/#/pool')

    await expect(page.getByText('它不显示收益率，也不给你推荐。')).toBeVisible()
  })
})
