/**
 * The review queue (K3) — and the red lines that only exist on this page.
 *
 * Most of these assertions are **negative**: the page must not contain a
 * percentage, a streak, a progress bar, or a word of consolation. A negative
 * assertion in a browser test is the only place these can be enforced, because
 * they are properties of what is *absent* from the rendered surface — and the
 * backend cannot check them, since it never sends a score at all.
 *
 * That split is deliberate and worth stating: red line 9 is enforced in two
 * places, once as a contract (`test_reviews_api.py` enumerates the response
 * fields) and once as a surface (here). Either alone would be enough to stop a
 * single accident; only together do they stop a habit.
 */

import { expect, test } from '@playwright/test'
import { routeApi } from './fixtures'

const CARD_ID = 'card_1790560000000'

const SCHEDULE = {
  card_id: CARD_ID,
  state: 'learning',
  due_at: '2026-09-28T09:00:00+00:00',
}

const CARD = {
  id: CARD_ID,
  content: '渠道库存是白酒的先行指标，通常领先报表 1–2 个季度。',
  claim_type: 'supporting',
  source_url: 'https://example.com/report/123',
  source_title: '白酒渠道深度调研',
  captured_at: '2026-08-14T00:00:00.000Z',
  as_of: null,
  origin: 'user_written',
  priority: 3,
  status: 'active',
  created_at: '2026-08-14T00:00:00.000Z',
  symbols: [],
  events: [],
}

function queue(handlers: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    'GET /api/v1/review/due': [SCHEDULE],
    [`GET /api/v1/cards/${CARD_ID}`]: CARD,
    'POST /api/v1/review/card_1790560000000': {
      card_id: CARD_ID,
      outcome: 'reviewed',
      next_due_at: '2026-10-05T09:00:00+00:00',
      state: 'review',
    },
    ...handlers,
  }
}

test.describe('复习页（spec 019 · 红线 9 / 11 / 13）', () => {
  test('the claim and its source are both on screen', async ({ page }) => {
    await routeApi(page, queue())
    await page.goto('#/review')

    await expect(page.getByTestId('review-claim')).toContainText('渠道库存')
    // The source is always visible, not behind a hover: a claim you cannot
    // check against where it came from is recitation, not review.
    await expect(page.getByTestId('review-source')).toBeVisible()
    await expect(page.getByText('白酒渠道深度调研')).toBeVisible()
  })

  test('no score appears anywhere（红线 9）', async ({ page }) => {
    await routeApi(page, queue())
    await page.goto('#/review')
    await expect(page.getByTestId('review-claim')).toBeVisible()

    const text = await page.locator('body').innerText()
    for (const forbidden of ['%', '正确率', '记住率', '掌握度', '评分', '得分']) {
      await expect(text).not.toContain(forbidden)
    }
  })

  test('no streak and no progress bar（红线 11）', async ({ page }) => {
    await routeApi(page, queue())
    await page.goto('#/review')
    await expect(page.getByTestId('review-claim')).toBeVisible()

    const text = await page.locator('body').innerText()
    for (const forbidden of ['连续', '打卡', 'streak', '/ 1', '已复习']) {
      await expect(text).not.toContain(forbidden)
    }
  })

  test('the page reports a count but never a progress fraction', async ({ page }) => {
    await routeApi(page, queue())
    await page.goto('#/review')
    // "3 张" is a fact about the queue. "2 / 8" would be a gameable number,
    // and red line 11 objects to the game more than to the backlog.
    await expect(page.getByText('今天要过一遍的 1 张')).toBeVisible()
    await expect(page.locator('body')).not.toContainText('/ 8')
  })

  test('postponing is a first-class button, not a hidden menu（红线 14）', async ({
    page,
  }) => {
    await routeApi(page, queue())
    await page.goto('#/review')

    // SuperMemo S-05: "暂不处理是特性不是拖延". If answering honestly cost the
    // user something, the honest options are lying "记得" or abandoning the
    // queue — both caused by the product.
    await expect(page.getByTestId('rate-defer')).toBeVisible()
    await expect(page.getByTestId('rate-again')).toBeVisible()
    await expect(page.getByTestId('rate-hard')).toBeVisible()
    await expect(page.getByTestId('rate-good')).toBeVisible()
    await expect(page.getByTestId('rate-easy')).toBeVisible()
  })

  test('after forgetting, the page says when it returns and nothing about you（红线 13）', async ({
    page,
  }) => {
    await routeApi(page, queue())
    await page.goto('#/review')
    await page.getByTestId('rate-again').click()

    await expect(page.getByTestId('review-receipt')).toBeVisible()
    const text = await page.locator('body').innerText()

    // The one thing it says: a date.
    expect(text).toContain('2026-10-05')

    // And nothing at all about how that went. No consolation, no red, no count
    // of past failures — the product records the interaction and does not
    // comment on the person.
    for (const forbidden of [
      '没关系',
      '别灰心',
      '正常',
      '继续加油',
      '你忘记了',
      '已忘记',
      '第 3 次',
      '答错',
    ]) {
      expect(text).not.toContain(forbidden)
    }
  })

  test('postponing produces a receipt and no rating', async ({ page }) => {
    const posted: string[] = []
    await routeApi(
      page,
      queue({
        'POST /api/v1/review/card_1790560000000': {
          card_id: CARD_ID,
          outcome: 'deferred',
          next_due_at: '2026-10-05T09:00:00+00:00',
          state: 'deferred',
        },
      }),
    )
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().includes('/api/v1/review/')) {
        posted.push(request.postData() ?? '')
      }
    })

    await page.goto('#/review')
    await page.getByTestId('rate-defer').click()
    await expect(page.getByTestId('review-receipt')).toBeVisible()

    // The body carries no `rating`: a postponement recalls nothing, and the
    // server rejects a body that claims otherwise.
    expect(posted.join('')).not.toContain('rating')
    expect(posted.join('')).toContain('deferred')
  })

  test('an empty queue says so and offers a way out', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/review/due': [] })
    await page.goto('#/review')
    await expect(page.getByText('今天没有到期的卡片')).toBeVisible()
    // ⚠️ **The second sentence changed on 2026-10-02 (spec 048), and this assertion is
    // what made that visible rather than silent.**
    //
    // It said 「还没加入复习的卡片不会出现在这里。到期的会自己回来。」 — true, and it
    // explained why *this queue* is empty. Measured against an empty database it was
    // **62 characters** of prose against 今日's 360, because for a brand-new reader the
    // reason the queue is empty is an **upstream** fact they were never told.
    //
    // It now says where the queue comes from **and names the control that fills it** —
    // which is only true because `CardSection` grew a 「加入复习」 button in the same
    // change. **Before that button existed, this sentence was correct and useless;
    // pointing at an action that does not exist is worse than saying nothing.**
    await expect(page.getByText('队列来自你自己写下的卡片')).toBeVisible()
    await expect(page.getByText('加入复习')).toBeVisible()
  })
})
