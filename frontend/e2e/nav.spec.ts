/**
 * The application shell (spec 022).
 *
 * Before this there was **no navigation at all** — six pages each hand-wrote a
 * "← back to X" link, and the only way to reach any view was to type its hash. That
 * is not a missing feature, it is a missing frame, and it is why the retrospective
 * page shipped with no way in.
 *
 * ⭐ Two of these tests exist because **the shell is part of the page body**, and
 * three other specs assert on the whole body:
 *
 * - `retrospective.spec.ts` — in the dangerous quadrant the page contains **no
 *   digit at all** (red line 10, strongest form)
 * - `review.spec.ts` — no `%`, `正确率`, `记住率`, `掌握度`, `评分`, `得分` (red line 9)
 * - `today.spec.ts` — no `收益率`
 *
 * So the nav is asserted to be free of digits and of those words, on **every**
 * view. A label like "复习 3" would not be a style problem; it would break a
 * red-line test somewhere else, and it would be red line 11 (不鼓励频繁操作 /
 * 禁止打卡计数) wearing a helpful little badge.
 */

import { expect, test } from '@playwright/test'
import { routeApi, todayEmpty } from './fixtures'

const VIEWS = [
  { hash: '#/', label: '今天' },
  { hash: '#/pool', label: '关注池' },
  { hash: '#/review', label: '复习' },
  { hash: '#/retrospective', label: '复盘' },
  { hash: '#/universe', label: '指数成分' },
]

/** Enough fixtures that no view is left waiting on a 404 mid-assertion. */
function stub(page: Parameters<typeof routeApi>[0]): Promise<void> {
  return routeApi(page, {
    'GET /api/v1/today': todayEmpty(),
    'GET /api/v1/watchlist': [],
    'GET /api/v1/watchlist/quotes': [],
    'GET /api/v1/review/due': [],
    'GET /api/v1/decision-reviews/due': [],
  })
}

test.describe('应用外壳', () => {
  test('每个页面都有导航，且当前页被标出', async ({ page }) => {
    await stub(page)
    for (const view of VIEWS) {
      await page.goto(`/${view.hash}`)
      const nav = page.getByTestId('nav')
      await expect(nav, view.hash).toBeVisible()
      await expect(nav.getByTestId(`nav-${view.label}`)).toHaveAttribute('data-active', 'true')
      // …and exactly one item is current. Two lit items would mean the reader is
      // in two places at once, which is the same class of lie as the page title
      // bug the route table replaced.
      await expect(page.locator('[data-testid^="nav-"][data-active="true"]')).toHaveCount(1)
    }
  })

  test('点导航能在页面之间走', async ({ page }) => {
    await stub(page)
    await page.goto('/#')
    await page.getByTestId('nav-关注池').click()
    await expect(page).toHaveURL(/#\/pool/)
    await page.getByTestId('nav-复盘').click()
    await expect(page).toHaveURL(/#\/retrospective/)
    await page.getByTestId('nav-今天').click()
    await expect(page).toHaveURL(/#\/?$/)
  })

  test('⭐ 导航没有任何数字、禁用词或红点（红线 9 / 10 / 11）', async ({ page }) => {
    await stub(page)
    for (const view of VIEWS) {
      await page.goto(`/${view.hash}`)
      const navText = (await page.getByTestId('nav').innerText()).replace(/\s+/g, '')
      expect(navText, `${view.hash} 导航含数字`).not.toMatch(/[0-9]/)
      for (const word of ['%', '正确率', '记住率', '掌握度', '评分', '得分', '收益率', '连续', '打卡']) {
        expect(navText.includes(word), `${view.hash} 导航含「${word}」`).toBe(false)
      }
    }
  })

  test('⭐ 导航不预告队列里还剩几条', async ({ page }) => {
    /**
     * Separate from the digit test above, and it is the one that would actually
     * stop the feature. `项目总纲` §2.1⑤ asks for "一句陈述，无推送、无红点、无催促词":
     * a count in the nav turns "you owe three cards" into a number you can see,
     * keep and try to climb. The queue's length is fine *inside* the page you
     * chose to open — it is the advance advertisement that is the problem.
     */
    await routeApi(page, {
      'GET /api/v1/today': todayEmpty(),
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
      'GET /api/v1/review/due': [
        { card_id: 'card_1', state: 'learning', due_at: '2026-09-28T09:00:00+00:00' },
        { card_id: 'card_2', state: 'learning', due_at: '2026-09-28T09:00:00+00:00' },
        { card_id: 'card_3', state: 'learning', due_at: '2026-09-28T09:00:00+00:00' },
      ],
      'GET /api/v1/decision-reviews/due': [],
    })
    await page.goto('/#/review')
    // The page itself may say how many it is holding.
    await expect(page.getByTestId('review-actions')).toBeVisible()
    // The nav may not.
    const navText = await page.getByTestId('nav').innerText()
    expect(navText).not.toMatch(/[0-9]/)
  })

  test('地址看不懂时导航仍在，读者能点出去', async ({ page }) => {
    /**
     * The shell's real job on the error path. A bad hash used to land on a bare
     * page with one link; rendering it *inside* the shell means a reader who
     * mistypes can leave by clicking, not by editing the URL bar.
     */
    await stub(page)
    await page.goto('/#/nonsense')
    await expect(page.getByText('这个地址看不懂')).toBeVisible()
    await expect(page.getByTestId('nav')).toBeVisible()
    // And no nav item claims to be current, because the app has just said it does
    // not know where it is.
    await expect(page.locator('[data-testid^="nav-"][data-active="true"]')).toHaveCount(0)
    await page.getByTestId('nav-今天').click()
    await expect(page).toHaveURL(/#\/?$/)
  })
})
