import { expect, test } from '@playwright/test'
import { routeApi, todayEmpty } from './fixtures'

test.describe('路由（hash 层）', () => {
  test('an unknown address says so instead of rendering a plausible page', async ({
    page,
  }) => {
    await routeApi(page, {})
    await page.goto('/#/nonsense')

    await expect(page.getByText('这个地址看不懂')).toBeVisible()
  })

  test('an empty hash lands on today', async ({ page }) => {
    await routeApi(page, {
      'GET /api/v1/today': todayEmpty(),
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
    })
    await page.goto('/#/')

    await expect(page.getByRole('heading', { name: /今天/ }).first()).toBeVisible()
  })
})
