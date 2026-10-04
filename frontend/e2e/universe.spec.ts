/**
 * 指数成分（spec 052）—— 一个**只读参考**的四个断言面。
 *
 * ## 这一份测什么，不测什么
 *
 * ⭐ 不测「表里有 300 行」—— 那是 `test_universe_api.py` 的事，而且前端测它就等于把
 * 后端的数量复制一份。⭐ 这里只测**只有前端能保证的四件事**：
 *
 * 1. ⭐⭐ **新鲜度必须上屏，而且网格点必须是一个日期。**
 *    `.ai/data-sources.md:137` 记着「僵尸报价」的成因是「不报错、不崩溃，只是安静地骗人」，
 *    ⭐ 而这一页的主体就是一份可能落后七天的名单 ⭐ **所以「它有多旧」是这一页
 *    唯一的必测项** ⭐ 而不是它的边角。
 * 2. ⭐ **一列都不能排序。** 宪法边界在 UI 上唯一的杠杆就是「不给 `sortValue`」
 *    （`DataTable.tsx:95`）⭐ **而这条只能在这里测** ⭐ 后端与 vitest 都看不见一个
 *    排序控件是否存在。⭐ **一个渲染了 ▲▼ 的池子就是选股的前门。**
 * 3. ⭐ **边界那句话必须在屏幕上。** `pool.spec.ts:77` 为关注池的同类句子做过一条，
 *    ⭐ **而本仓的立场是读者看不见的边界不是边界。**
 * 4. ⭐ **「没取过」与「名单是空的」必须给出不同的句子。**
 *
 * ## fixture 的形状照 `poolRows()` / `poolQuotes()` 的体例：**两个极端**
 *
 * ⭐ 一行「刚被观察到、就在名单里」与一行「2020 年就被摘出去了」—— ⭐ **因为「出现过的」
 * 正是这个板块的全部意义** ⭐ **而一只只有当前那一段的行，说不出这一点。**
 */

import { expect, test } from '@playwright/test'
import { routeApi, type Body } from './fixtures'

const LIST = '/api/v1/universe'

/** ⭐ The newest grid point we hold ⭐ **and it is deliberately not today.** */
const GRID = '2020-07-20'

/** ⭐ Two extremes: one currently in the index, one that left years ago. */
function universe(): Body {
  return {
    freshness: {
      index_code: '000300',
      latest_grid_point: GRID,
      members: 300,
      source: 'baostock',
      resolution: 'weekly',
      ever_swept: true,
    },
    members: [
      {
        market: 'sh',
        code: '600000',
        name: '浦发银行',
        first_observed_on: '2007-07-30',
        last_observed_on: GRID,
        is_latest: true,
      },
      {
        market: 'sz',
        code: '000016',
        name: '深康佳A',
        first_observed_on: '2005-04-08',
        last_observed_on: '2007-12-28',
        is_latest: true,
      },
    ],
  }
}

test.beforeEach(async ({ page }) => {
  await routeApi(page, { [`GET ${LIST}`]: universe() })
})

test.describe('指数成分（spec 052）', () => {
  test('⭐⭐ it says how old the roster is, and names the day', async ({ page }) => {
    await page.goto('#/universe')
    const fresh = page.getByTestId('universe-freshness')
    await expect(fresh).toBeVisible()
    // ⭐ The **grid point**, verbatim ⭐ **because a sentence saying 「有点旧」 without a
    // day is the same defect with better manners.**
    await expect(fresh).toContainText(GRID)
    await expect(fresh).toContainText('300')
    await expect(fresh).toContainText('baostock')
  })

  test('⭐⭐ it offers no way to sort, rank or shortlist', async ({ page }) => {
    await page.goto('#/universe')
    await expect(page.getByTestId('universe-freshness')).toBeVisible()
    // ⭐ `DataTable` renders a sort control per column **that has a `sortValue`** ⭐
    // (`DataTable.tsx:95`) ⭐ so 「no sort-* test ids at all」 is the constitutional
    // boundary expressed as an assertion ⭐ **rather than as a promise in a footer.**
    const sorts = page.locator('[data-testid^="sort-"]')
    await expect(sorts).toHaveCount(0)
  })

  test('⭐ it shows the entry and exit windows, not just the roster', async ({ page }) => {
    await page.goto('#/universe')
    const rows = page.getByTestId('data-row')
    await expect(rows).toHaveCount(2)
    // ⭐ The row that left in 2007 still has its window ⭐ **and that is what
    // 「出现过的」 means** ⭐ — a roster that only held today's members could not say it.
    await expect(page.getByText('深康佳A')).toBeVisible()
    await expect(page.getByText('2005-04-08')).toBeVisible()
    await expect(page.getByText('2007-12-28')).toBeVisible()
  })

  test('⭐ it states its boundary where the reader can read it', async ({ page }) => {
    await page.goto('#/universe')
    await expect(page.getByText('它不排序、不打分，也不告诉你该看哪几只。')).toBeVisible()
  })

  test('⭐⭐ a roster we never fetched is not an empty roster', async ({ page }) => {
    await page.route(`**${LIST}**`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          freshness: {
            index_code: '000300',
            latest_grid_point: null,
            members: null,
            source: null,
            resolution: 'weekly',
            ever_swept: false,
          },
          members: [],
        }),
      }),
    )
    await page.goto('#/universe')
    // ⭐ Two different sentences for two different facts ⭐ **and the first draft of the
    // backend put both in one, which is `F-218` wearing prose.**
    await expect(page.getByTestId('universe-never-swept')).toBeVisible()
    await expect(page.getByTestId('universe-never-swept')).toContainText('而这不是「名单是空的」')
    await expect(page.getByTestId('universe-empty')).toHaveCount(0)
    await expect(page.getByTestId('universe-freshness')).toHaveCount(0)
  })

  test('⭐ a failed fetch says so rather than reading as empty', async ({ page }) => {
    await page.route(`**${LIST}**`, (route) => route.fulfill({ status: 500 }))
    await page.goto('#/universe')
    await expect(page.getByTestId('universe-loading')).toHaveCount(0)
    // ⭐ The error block is a distinct state ⭐ **because `useResource` keeps `data` and
    // a blank table would be indistinguishable from an empty index.**
    await expect(page.getByText('它不会静默显示成「名单是空的」。')).toBeVisible()
  })
})