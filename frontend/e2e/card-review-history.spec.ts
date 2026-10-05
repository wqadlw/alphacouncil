/**
 * 卡片的复习历史：被复习过这件事，读者看不看得见（spec 055）
 *
 * ⭐⭐⭐ **这个 spec 存在的原因和 `card-enrolment.spec.ts` 是同一条死结，只是深一层。**
 *
 * ```
 *   grep list_reviews            -> scheduling.py:402 有实现、有 __all__ 导出、有测试
 *   grep listCardReviews         -> api.ts 有定义，调用者 0 个
 *   GET /api/v1/cards/{id}/reviews -> 404（2026-10-05 之前连路由都没有）
 *   GET /api/v1/notes/{id}/reviews -> 200          ← 笔记有
 * ```
 *
 * **⇒ 卡片只能靠写代码看到自己的复习历史。** spec 028 提出过那个问题
 * ——「我复习过 5 次，为什么今天又来了」—— ⭐ 而它在笔记那边被修好了，
 * 在卡片这边一个字都没修，**而卡片是 K3 的主体**。
 *
 * ⚠️ **这一轮真正的缺陷比「少一条端点」深一层**（spec 055 §1.3）：
 * `ratings.ts` 有 `NOTE_RATINGS` 与 `LESSON_RATINGS`，**没有 `CARD_RATINGS`** ——
 * 卡片的四个评分标签是 `ReviewPage.tsx` 里第五处硬编码。
 * ⇒ 所以历史行要说「复习过 · 有点难」，而那个「有点难」**必须和读者按下的按钮同词**，
 * 否则历史回答不了「我当时按的是哪个」。词汇表的守卫在 `ratings.test.ts`，
 * 本 spec 只断言它**出现在屏幕上**。
 *
 * ⭐ **取数条件是三态推出来的，不是猜的**（spec 055 §2.5）：
 * 一条复习记录不可能在没有入队的情况下存在（`record_review` 先读 schedule），
 * 所以「确定没入队」就已经回答了「有没有历史」，**不必发那个请求**。
 * 本 spec 用请求计数把这条钉住 —— 它是本轮最容易悄悄退化的地方。
 */

import { expect, test } from '@playwright/test'
import {
  CARD_NOT_SCHEDULED,
  aCardDeferral,
  aCardReview,
  anInstrumentCard,
  cardSchedule,
  instrumentDetail,
  quoteResult,
  routeApi,
} from './fixtures'

const CARD_ID = 'card_1700000000000'

/** One instrument page with one active card on it. */
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

/** Count every request whose path mentions `reviews`, so "did not ask" is measurable. */
function watchReviewReads(page: Parameters<typeof routeApi>[0]): string[] {
  const reads: string[] = []
  page.on('request', (r) => {
    if (r.method() === 'GET' && r.url().includes('/reviews')) reads.push(r.url())
  })
  return reads
}

test.describe('复习历史 · 卡片（spec 055）', () => {
  test('B1 · 入队且答过之后，历史出现在那张卡片上', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      [`GET /api/v1/cards/${CARD_ID}/schedule`]: cardSchedule(),
      [`GET /api/v1/cards/${CARD_ID}/reviews`]: [aCardReview(), aCardDeferral()],
    })

    await page.goto('/#/i/sh/600519')

    const history = page.getByTestId('card-review-history')
    await expect(history).toBeVisible()
    // ⭐ **The grade on screen is the reader's own word for the button they pressed.**
    // 「有点难」 is `ReviewPage.tsx`'s label for `hard`, and `ratings.test.ts` is what holds
    // the two surfaces to one table — this assertion is the screen half of that.
    await expect(history).toContainText('有点难')
    // ⭐ **And the postponement says the reader's word too**, not 「延期」 — a scheduler's
    // vocabulary, in a sentence the reader is reading about themselves.
    await expect(history).toContainText('我说以后再看')
    // ⚠️ **Not a count.** 「已复习 2 次」 is a number about the reader that they could try to
    // climb (红线 11), so the history is a list of rows and never a tally.
    await expect(history).not.toContainText('2 次')
    await expect(history).not.toContainText('复习过 2')
  })

  test('B2 · 每次交互一行，且带上下次到期日', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      [`GET /api/v1/cards/${CARD_ID}/schedule`]: cardSchedule(),
      [`GET /api/v1/cards/${CARD_ID}/reviews`]: [aCardReview(), aCardDeferral()],
    })

    await page.goto('/#/i/sh/600519')

    const history = page.getByTestId('card-review-history')
    await expect(history).toBeVisible()
    // ⭐ **The detail line is the new due date, and it is the reader's question answered.**
    // Either half alone leaves them guessing, which is why both are on one row.
    await expect(history).toContainText('下一次 2026-10-16')
    await expect(history).toContainText('下一次 2026-10-23')
    // Two rows, and they are ordered — 「我复习过 2 次」 is a claim about a sequence.
    await expect(history.locator('li')).toHaveCount(2)
    // ⭐ **The wire value must never reach the screen.** `hard` is what the server sends;
    // 「有点难」 is what the reader pressed, and B1 asserts that one. A history that renders
    // `hard` has leaked the enum — which is what `CARD_RATING_LABEL` exists to prevent, and
    // this is the screen-level half of that guard.
    await expect(history).not.toContainText('hard')
    await expect(history).not.toContainText('deferred')
    await expect(history).not.toContainText('reviewed')
  })

  test('B3 · 未入队 ⇒ 不请求、不渲染', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      [`GET /api/v1/cards/${CARD_ID}/schedule`]: {
        status: 409,
        body: CARD_NOT_SCHEDULED,
      },
    })
    const reads = watchReviewReads(page)

    await page.goto('/#/i/sh/600519')

    await expect(page.getByTestId('card-schedule-out')).toBeVisible()
    await expect(page.getByTestId('card-review-history')).toHaveCount(0)
    // ⭐ **The assertion this spec exists for.** A review cannot exist without an enrolment
    // (`record_review` reads the schedule first), so 「确定没入队」 settles the history
    // question without asking it. ⭐ If a future change fetches it anyway, this is a
    // **request count**, so the regression shows up as traffic rather than as a slower page
    // nobody measured.
    expect(reads, '没入队的卡片不发历史请求').toHaveLength(0)
  })

  test('B4 · 复习状态读不到 ⇒ 不请求、不渲染、也不显示那个会失败的按钮', async ({ page }) => {
    await instrumentWithCard(page)
    await page.route('**/api/v1/cards/*/schedule', (route) => route.abort('failed'))
    const reads = watchReviewReads(page)

    await page.goto('/#/i/sh/600519')

    await expect(page.getByTestId('card-schedule-unknown')).toBeVisible()
    await expect(page.getByTestId('card-review-history')).toHaveCount(0)
    expect(reads, '「不知道」不等于「没有」，所以也不去问历史').toHaveLength(0)
    // ⭐ The button must not appear: it is guaranteed to fail.
    await expect(page.getByRole('button', { name: '加入复习' })).toHaveCount(0)
  })

  test('B5 · 入队但从未作答 ⇒ 有「已加入复习」而没有历史', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      [`GET /api/v1/cards/${CARD_ID}/schedule`]: cardSchedule(),
      // ⭐ **The measured case** (spec 055 §1.5): enrolment inserts a schedule row and
      // nothing else, so an enrolled-and-never-answered card has **zero** history rows.
      // The read is stubbed rather than omitted, because an unstubbed read would 404 and
      // this test would pass for the wrong reason — the mistake
      // `card-enrolment.spec.ts:156` records by name.
      [`GET /api/v1/cards/${CARD_ID}/reviews`]: [],
    })

    await page.goto('/#/i/sh/600519')

    await expect(page.getByTestId('card-schedule-in')).toContainText('已加入复习')
    // ⚠️ **Nothing is rendered for an empty list** — not an empty timeline, not a sentence.
    // 「已加入复习」 already says it, and a second sentence would be the same fact twice.
    await expect(page.getByTestId('card-review-history')).toHaveCount(0)
    await expect(page.getByText('它没有回来过')).toHaveCount(0)
  })

  test('B6 · 读不到历史时说一句话，且不装作没有', async ({ page }) => {
    await instrumentWithCard(page)
    await routeApi(page, {
      [`GET /api/v1/cards/${CARD_ID}/schedule`]: cardSchedule(),
      [`GET /api/v1/cards/${CARD_ID}/reviews`]: { status: 500, body: { message: 'boom' } },
    })

    await page.goto('/#/i/sh/600519')

    await expect(page.getByTestId('card-review-history-error')).toContainText('复习流水取不到')
    // ⭐ Red line 6 in the interface's own words: an unripe result shows empty, and
    // **「取不到」 is not 「没有」** — the two must not collapse into one sentence.
    await expect(page.getByText('它没有回来过')).toHaveCount(0)
  })

  test('B7 · 收敛的卡片不给按钮，但留住它挣来的历史', async ({ page }) => {
    // ⚠️⚠️ **The case that makes this more than a mirror of the note history.**
    //
    // A card can be enrolled, reviewed, and then converged. ⭐ The 409 is stubbed so the
    // control has somewhere to go: without it the read 404s, the row lands in 「不知道」,
    // and **this test would pass for a reason that has nothing to do with convergence** —
    // the vacuity `card-enrolment.spec.ts:156` found by mutation and wrote down.
    await routeApi(page, {
      'GET /api/v1/instruments/sh/600519': {
        ...instrumentDetail(),
        cards: [anInstrumentCard({ status: 'converged' })],
      },
      'GET /api/v1/instruments/sh/600519/quote': quoteResult(1237.0, -0.0114),
      'GET /api/v1/decisions': [],
      [`GET /api/v1/cards/${CARD_ID}/schedule`]: cardSchedule(),
      [`GET /api/v1/cards/${CARD_ID}/reviews`]: [aCardReview()],
    })

    await page.goto('/#/i/sh/600519')

    // The button is gone — a retired claim is not queued into review.
    await expect(page.getByRole('button', { name: '加入复习' })).toHaveCount(0)
    // ⭐⭐ **And the history is still there.** Hiding it because the claim changed would
    // delete a record that happened, ⭐ which is the one thing this product does not do.
    await expect(page.getByTestId('card-review-history')).toBeVisible()
    await expect(page.getByTestId('card-review-history')).toContainText('有点难')
  })
})