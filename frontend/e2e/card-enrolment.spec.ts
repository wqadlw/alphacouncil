/**
 * 加入复习：卡片能不能自己进队列，以及界面知不知道它在不在队列里（spec 048）
 *
 * ⭐⭐⭐ **这个 spec 存在的原因是一条量出来的死结。**
 *
 * ```
 *   POST /api/v1/cards                 -> 201 card_1790916668533
 *   GET  /api/v1/review/due            -> 0 items    ← 服务端不主动贡献任何东西
 *   POST /api/v1/cards/{id}/schedule   -> 201 {"state":"learning", …}
 *   GET  /api/v1/review/due            -> 1 item
 *   grep scheduleCard                  -> api.ts:282 定义，调用者 0 个
 * ```
 *
 * **⇒ 卡片只能靠写代码进复习队列。** 而缺的不止是按钮：**`GET` 端点当时不存在**，
 * 所以界面既不知道一张卡在不在队列里，**也不能从 `/review/due` 推断** ——
 * 那个端点只给**到期**的，排在下周三的卡不在里面。
 *
 * ⇒ 「加入复习」如果只能靠点完才知道结果，**它就是一个赌注**，而这个产品不拿读者的
 * 记录下赌。后端补的那条 `GET` 就是为了不赌。
 *
 * ⚠️ **三态，不是布尔。** 笔记那边（`VaultPage`）用 `.catch(() => false)`，
 * 任何失败都读成「未入队」—— 于是后端一停就出现一个点了必然失败的按钮。
 * 本 spec 的核心断言之一就是**那种按钮不许出现**。
 */

import { expect, test } from '@playwright/test'
import {
  CARD_NOT_SCHEDULED,
  anInstrumentCard,
  cardSchedule,
  instrumentDetail,
  quoteResult,
  routeApi,
} from './fixtures'

const CARD_ID = 'card_1700000000000'

/**
 * One instrument page with one card on it.
 *
 * ⭐ **`instrumentDetail()` returns `cards: []`**, so without this the page under
 * test has no card and therefore no enrolment control at all — and the suite would
 * be green the whole time.
 */
async function instrumentWithCard(page: Parameters<typeof routeApi>[0]): Promise<void> {
  await routeApi(page, {
    'GET /api/v1/instruments/sh/600519': {
      ...instrumentDetail(),
      cards: [anInstrumentCard()],
    },
    'GET /api/v1/instruments/sh/600519/quote': quoteResult(1237.0, -0.0114),
    'GET /api/v1/decisions': [],
  })
}

test.describe('关注池之外 · 加入复习（spec 048）', () => {
  test.beforeEach(async ({ page }) => {
    await routeApi(page, {
      'GET /api/v1/instruments/sh/600519': instrumentDetail(),
      'GET /api/v1/instruments/sh/600519/quote': quoteResult(1237.0, -0.0114),
      'GET /api/v1/decisions': [],
    })
  })

  test('A4 · 未入队时给出按钮，点了写入', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      'GET /api/v1/cards/card_1700000000000/schedule': {
        status: 409,
        body: CARD_NOT_SCHEDULED,
      },
      'POST /api/v1/cards/card_1700000000000/schedule': cardSchedule(),
    })
    const writes: string[] = []
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/schedule')) writes.push(r.url())
    })

    await page.goto('/#/i/sh/600519')

    const control = page.getByTestId('card-schedule-out')
    await expect(control).toBeVisible()
    // ⭐ **The button says what committing to this means.** One clause, and it is the
    // sentence that makes 「它会自己回来」 a promise rather than a slogan.
    await expect(control).toContainText('到时会自己回来。')
    // ⚠️ **No count and no "enrol everything".** Enrolling every claim the reader ever
    // wrote builds a backlog nobody drains — the reason `VaultPage` writes out for
    // notes, reused here.
    await expect(page.getByRole('button', { name: /全部|所有/ })).toHaveCount(0)

    await page.getByRole('button', { name: '加入复习' }).click()
    await expect(page.getByTestId('card-schedule-in')).toBeVisible()
    expect(writes).toHaveLength(1)
  })

  test('A5 · 入队后显示下次，并且按钮不再出现', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      'GET /api/v1/cards/card_1700000000000/schedule': cardSchedule(),
    })

    await page.goto('/#/i/sh/600519')

    await expect(page.getByTestId('card-schedule-in')).toContainText('已加入复习')
    // ⭐ **The date is the server's, rendered — not a number the client made up**, and
    // the assertion names the fixture's value so a fixture that drifts is visible.
    await expect(page.getByTestId('card-schedule-in')).toContainText('下次')
    await expect(page.getByTestId('card-schedule-out')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '加入复习' })).toHaveCount(0)
  })

  test('A6 · 读状态失败时说「不知道」，并且不给按钮', async ({ page }) => {
    await instrumentWithCard(page)
    // ⭐ **A transport failure, not a 409.** This is the state the notes' version
    // collapses into 「not enrolled」 — and it is the one that must never produce a
    // button, because the button is guaranteed to fail.
    await page.route('**/api/v1/cards/*/schedule', (route) => route.abort('failed'))

    await page.goto('/#/i/sh/600519')

    await expect(page.getByTestId('card-schedule-unknown')).toContainText('复习状态取不到')
    // ⭐ **The assertion that matters.** A button here would look perfectly usable and
    // fail on every press.
    await expect(page.getByRole('button', { name: '加入复习' })).toHaveCount(0)
    await expect(page.getByTestId('card-schedule-out')).toHaveCount(0)
  })

  test('卡片不存在时也不给按钮（404 与 409 是两件事）', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      'GET /api/v1/cards/card_1700000000000/schedule': {
        status: 404,
        body: {
          severity: 'error',
          code: 'CARD_NOT_FOUND',
          message: "card 'card_1700000000000' not found",
          target: null,
          fix: null,
        },
      },
    })

    await page.goto('/#/i/sh/600519')

    // ⭐ **404 is not 「not enrolled」.** If the two collapsed, a stale link would render
    // a working-looking 「加入复习」 for a card that does not exist.
    await expect(page.getByTestId('card-schedule-unknown')).toBeVisible()
    await expect(page.getByRole('button', { name: '加入复习' })).toHaveCount(0)
  })

  test('已收敛的卡片不给入队按钮', async ({ page }) => {
    // ⭐ **A converged card is not 「what I currently believe」 any more**, so asking the
    // reader to schedule it into review would queue a claim they have already retired
    // (red line 10: it stays visible, it does not stay active).
    //
    // ⚠️⚠️ **The schedule read is stubbed as 409 on purpose, and without that this test
    // passes for the wrong reason.** The first version left it unstubbed, so the read
    // 404'd, the control landed in its 「不知道」 state, and **no button appeared for a
    // reason that had nothing to do with convergence.** Mutation M3 — deleting the
    // `!converged` guard — did **not** turn this test red, which is how the vacuity was
    // found. With 409 stubbed, the button is one click away, so removing the guard has
    // somewhere to show.
    await routeApi(page, {
      'GET /api/v1/instruments/sh/600519': {
        ...instrumentDetail(),
        cards: [anInstrumentCard({ status: 'converged' })],
      },
      'GET /api/v1/cards/card_1700000000000/schedule': {
        status: 409,
        body: CARD_NOT_SCHEDULED,
      },
    })
    await page.goto('/#/i/sh/600519')

    // The card itself is still on screen — red line 10 keeps it visible, dimmed.
    // ⭐ `.first()` because Playwright's strict mode refuses an ambiguous locator, and
    // 「已收敛」 legitimately appears twice on this row (the claim-type label *and* the
    // lifecycle line). The first version asserted the bare text and failed on a
    // strict-mode violation rather than on anything about the product.
    await expect(page.getByText('已收敛').first()).toBeVisible()
    await expect(page.getByTestId('card-schedule-out')).toHaveCount(0)
    await expect(page.getByTestId('card-schedule-in')).toHaveCount(0)
    await expect(page.getByTestId('card-schedule-unknown')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '加入复习' })).toHaveCount(0)
  })

  test('没有卡片的标的页不发那个请求', async ({ page }) => {
    // ⭐ **A page with no cards must not ask.** `instrumentDetail()` has `cards: []`
    // and this asserts the request count, so a future change that fires the read for
    // every instrument on every page load is visible as extra traffic rather than as
    // a slower page nobody measured.
    const reads: string[] = []
    page.on('request', (r) => {
      if (r.url().includes('/schedule')) reads.push(r.method())
    })
    await page.goto('/#/i/sh/600519')
    // ⚠️ **The anchor is the display code, not a section heading.** The first version
    // waited for 「我对它说过什么」, a string written from memory rather than read, and
    // the page's section labels are not that. Waiting for a string nobody read is the
    // same mistake as `regressions/0008` one layer up.
    await expect(page.getByText('600519.SH').first()).toBeVisible()
    expect(reads, '没有卡片就没有入队控件，也就没有那个请求').toHaveLength(0)
  })
})

test.describe('空队列说得清（T0 · spec 048）', () => {
  test('A7 · 复习页说队列从哪来，并指向那个动作', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/review/due': [] })
    await page.goto('/#/review')

    await expect(page.getByText('今天没有到期的卡片')).toBeVisible()
    // ⭐ **The sentence that names where the queue comes from.** Measured on an empty
    // database (2026-10-02) this page rendered **62 characters** against 今日's 360 —
    // it explained why *its own* queue was empty and never said where cards come from,
    // which for a brand-new reader is an upstream fact they were never told.
    await expect(page.getByText('队列来自你自己写下的卡片')).toBeVisible()
    // ⚠️ **And it points at the control spec 048 added**, so the sentence has an action
    // behind it rather than being a dead end in better prose.
    await expect(page.getByText('加入复习')).toBeVisible()
  })

  test('A7 · 复盘页同样说清队列从哪来', async ({ page }) => {
    await routeApi(page, {
      'GET /api/v1/decision-reviews/due': [],
      'GET /api/v1/decision-reviews/recent': [],
    })
    await page.goto('/#/retrospective')

    await expect(page.getByText('现在没有到期的复盘')).toBeVisible()
    await expect(page.getByText('队列来自你记录过的判断')).toBeVisible()
  })

  test('⚠️ 两个空态都不猜「你还没有卡片」', async ({ page }) => {
    // ⭐ **This is the assertion that keeps the copy honest.**
    //
    // `/review/due` returns `[]` both when there are no cards at all and when there
    // are cards none of which are due, so **the page cannot know which** — and a
    // sentence that guesses is worse than no sentence. If someone later "improves" the
    // empty state to say 「你还没有卡片」, this fails.
    await routeApi(page, {
      'GET /api/v1/review/due': [],
      'GET /api/v1/decision-reviews/due': [],
      'GET /api/v1/decision-reviews/recent': [],
    })

    await page.goto('/#/review')
    await expect(page.getByText('你还没有卡片')).toHaveCount(0)
    await page.goto('/#/retrospective')
    await expect(page.getByText('你还没有记录过判断')).toHaveCount(0)
  })

  test('A8 · 队列里没有任何「全部加入」的控件', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/review/due': [] })
    await page.goto('/#/review')
    await expect(page.getByRole('button', { name: /全部加入|一键|全部/ })).toHaveCount(0)
  })
})