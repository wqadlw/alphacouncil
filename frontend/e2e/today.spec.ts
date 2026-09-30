import { expect, test } from '@playwright/test'
import { routeApi, todayClosed, todayEmpty, todayEveryState } from './fixtures'

test.describe('今日页（spec 005/007 + 红线 9）', () => {
  test('closed-market badge names the last trading day, and a due criterion says what we know', async ({
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

    // ⭐ **This assertion replaced two others, and the reason matters more than the
    // replacement.** It used to read:
    //
    //     await expect(page.getByText('去核实数据')).toBeVisible()
    //     await expect(body).not.toContainText('已触发')
    //
    // and the second one recorded its own reason (spec 005 FR-4): 「the metric has no
    // data source, so the outcome is unverified and must not be dressed up as decided」.
    // ⭐ **That reason stopped being true in spec 034/037/038, and the evaluator landed in
    // spec 040.** So the prohibition went with the fact that created it — a test whose
    // premise has expired should be deleted, not kept as a superstition and not
    // reinterpreted.
    //
    // What replaces it is the same prohibition with a **live** premise: this fixture's
    // metric is `revenue_yoy`, D4 is not built, and so the page must not claim the
    // criterion was decided. `criterionVerdict.test.ts` pins the general form — 已触发 is
    // never emitted, and `crossed` says 已越过 rather than borrowing a word.
    // ⭐ Scoped to the row, not the page. The section note was rewritten in spec 040 and
    // it **also** opens with 「观察期已到」 — so a bare `getByText` resolves to two
    // elements and Playwright's strict mode rejects the match. ⭐ That is the same trap
    // the comment above the row warns about, reappearing because a nearby sentence grew
    // a shared prefix. The assertion belongs to the row, so it asks the row.
    const row = page.getByTestId('attention-row')
    await expect(row).toContainText('观察期已到')
    await expect(row).toContainText(/不在我们能算的指标里/)
    await expect(row).toContainText(/没有被求值过/)
    const body = page.locator('body')
    await expect(body).not.toContainText('已触发')
    await expect(body).not.toContainText('已越过')
  })

  test('the three 「we cannot tell you」 states are three different sentences', async ({
    page,
  }) => {
    // ⭐ This is the spec. A single 「无法求值」 covering warming / undetermined /
    // no-bars would tell the reader their criterion held — a statement about their own
    // judgement that nobody checked.
    await routeApi(page, {
      'GET /api/v1/today': todayEveryState(),
      'GET /api/v1/watchlist': [],
      'GET /api/v1/watchlist/quotes': [],
    })
    await page.goto('/#/')

    const rows = page.getByTestId('attention-row')
    await expect(rows).toHaveCount(4)

    // crossed: the comparison ran, and the number is right there
    await expect(rows.nth(0)).toContainText('已越过')
    await expect(rows.nth(0)).toContainText('1185.30')
    await expect(rows.nth(0)).toHaveAttribute('data-crossed', 'true')

    // warming: too young, with the count, so it reads as a deferral
    await expect(rows.nth(1)).toContainText('还差 48 根')
    await expect(rows.nth(1)).toContainText('暂时没有被求值')
    await expect(rows.nth(1)).toHaveAttribute('data-adjudicable', 'false')

    // undetermined: the catalogue has never heard of it
    await expect(rows.nth(2)).toContainText('不在我们能算的指标里')

    // no bars at all: a different fault, and it must not borrow the other sentences
    // ⭐ The wording moved to `criterion_sentence.py` in spec 044 and is now shipped by the
    // server, so the assertion is against **that** sentence. ⭐ It used to be
    // 「取不到这个代码的日线」 because `metric: null` meant "we could not read any bars";
    // ⭐ the sentence now says 「这个代码没有日线」, which names the same fault in fewer
    // words — ⭐ and the fixture carries the server's exact string so the two cannot drift.
    await expect(rows.nth(3)).toContainText('这个代码没有日线')
    await expect(rows.nth(3)).not.toContainText('不在我们能算的指标里')

    // ⭐ and nowhere does the page say the criterion held
    const body = page.locator('body')
    await expect(body).not.toContainText('没有越过')
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
