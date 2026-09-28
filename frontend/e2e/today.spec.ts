import { expect, test } from '@playwright/test'
import { routeApi, todayClosed, todayEmpty } from './fixtures'

test.describe('今日页（spec 005/007 + 红线 9）', () => {
  test('closed-market badge names the last trading day, and due criteria speak their line', async ({
    page,
  }) => {
    await routeApi(page, {
      'GET /api/v1/today': todayClosed(),
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
    })
    await page.goto('/#/')

    await expect(page.getByRole('heading', { name: /今天/ }).first()).toBeVisible()
    await expect(page.getByText(/休市 · 最后交易日/)).toBeVisible()
    await expect(page.getByText('2026-09-24')).toBeVisible()

    // The criterion is due, and the page says "go verify" — never "triggered"
    // (spec 005 FR-4: the metric has no data source, so the outcome is
    // unverified and must not be dressed up as decided).
    await expect(page.getByText(/观察期已到/)).toBeVisible()
    await expect(page.getByText('去核实数据')).toBeVisible()
    const body = page.locator('body')
    await expect(body).not.toContainText('已触发')
  })

  test('an unknown market verdict shows no badge instead of inventing one', async ({
    page,
  }) => {
    await routeApi(page, {
      'GET /api/v1/today': todayEmpty(),
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
    })
    await page.goto('/#/')

    await expect(page.getByText(/休市/)).toHaveCount(0)
    await expect(page.getByText(/没有到期的失效条件/)).toBeVisible()
  })

  test('no returns metric is rendered anywhere on the page（红线 9）', async ({ page }) => {
    await routeApi(page, {
      'GET /api/v1/today': todayClosed(),
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
    })
    await page.goto('/#/')

    // The rule's words appear only as the rule itself; the word 收益率 may
    // not be followed by a number — that would be a returns metric, which
    // the page must never display (成绩单是红线 9 禁止的东西).
    const body = page.locator('body')
    await expect(body).toContainText(/没有收益率、没有排行/)
    await expect(body).not.toContainText(/收益率[^。]{0,12}[+−-]?\d/)
  })
})
