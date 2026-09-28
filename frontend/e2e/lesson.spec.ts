/**
 * The lesson side of the knowledge layer (spec 030).
 *
 * ⭐ **The first version of this file did not exist, and the E2E run passed anyway.**
 * `LessonRecallView` fetches `/api/v1/lessons/due` on mount, nothing mocked it, the
 * request fell through the dev proxy to a backend that was not running, and the run
 * reported `ECONNREFUSED` in the log while exiting 0 — because no assertion looked at
 * the queue. That is this project's own harness failure mode in its purest form: a
 * green result and an unmocked network call in the same run.
 *
 * So the queue is mocked here, and the tests below assert the two properties that are
 * the product rather than the wiring:
 *
 * 1. **no count anywhere** — the server returns a bare array, and the number of
 *    things you owe is the one thing this page must not render;
 * 2. **no title per row** — the row shows the lesson's own sentence, because a
 *    scannable list of things you owe is a to-do list.
 *
 * Plus the composer: it must not exist before a review has been written, and it must
 * say plainly that there is no 「入队」 button, because a reader told 「已经在队列上」
 * who then cannot find a queue will reasonably ask.
 */

import { expect, test, type Page } from '@playwright/test'

const LESSONS = [
  {
    lesson_id: 'lesson_1700000000001',
    state: 'learning',
    due_at: '2026-09-20T00:00:00.000Z',
    content: '先看批价再看渠道库存 —— 批价是先行指标',
  },
  {
    lesson_id: 'lesson_1700000000002',
    state: 'review',
    due_at: '2026-08-28T00:00:00.000Z',
    content: '仓位别一次打满，留一半给第二种可能',
  },
]

/**
 * The retrospective page's own data.
 *
 * ⭐ The composer renders only when a review exists, and a review existing is the
 * **server's** rule (`LESSON_REVIEW_MISSING` is a 409) rather than a UI preference —
 * so a fixture with no review has no composer, and the three tests that wait for
 * `lesson-open` time out instead of failing on an assertion. The first run of this
 * file did exactly that, with a green queue suite in the same output.
 */
const REVIEW_ID = '2026-09-20T02:15:00.000Z'

async function routeRetrospective(page: Page): Promise<void> {
  const decision = {
    decision_id: REVIEW_ID,
    market: 'sh',
    code: '600519',
    action: 'buy',
    rationale: '高端酒提价能力可持续，渠道库存处于低位',
    counter_evidence: '批价可能因春节压货而短期回落',
    kill_criteria: [],
    created_at: REVIEW_ID,
  }
  await page.route('**/api/v1/decision-reviews/due**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          decision_id: REVIEW_ID,
          is_due: false,
          due_at: '2026-09-20T02:15:00.000Z',
          latest: null,
        },
      ]),
    })
  })
  await page.route(`**/api/v1/decision-reviews/${REVIEW_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        state: { decision_id: REVIEW_ID, is_due: false, due_at: REVIEW_ID, latest: null },
        // A review that has already been written — which is the only state in which
        // the composer exists at all.
        latest: {
          decision_id: REVIEW_ID,
          process_score: 2,
          outcome: null,
          reviewed_at: REVIEW_ID,
          due_at: REVIEW_ID,
          note: null,
        },
        decision,
      }),
    })
  })
  await page.route('**/api/v1/notes**', async (route) => {
    const url = new URL(route.request().url())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(url.pathname.endsWith('/tags') ? [] : []),
    })
  })
}

async function routeLessons(page: Page, rows: typeof LESSONS): Promise<void> {
  await page.route('**/api/v1/lessons**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/lessons/due') {
      // ⭐ A **bare array**, no wrapper and no count — because the server returns
      // one, and a fixture that added a count would make the no-count assertions
      // below vacuous.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rows),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })
}

test.describe('教训队列（spec 030）', () => {
  test.beforeEach(async ({ page }) => {
    await routeLessons(page, LESSONS)
  })

  test('⭐ 到期的教训出现在「该复习」里', async ({ page }) => {
    await page.goto('/#/vault')
    await page.getByTestId('vault-view-recall').click()

    await expect(page.getByTestId('lesson-queue-item')).toHaveCount(2)
    // ⭐ The lesson's own sentence, not a label for it.
    await expect(page.getByTestId('lesson-queue-item').first()).toContainText('批价是先行指标')
  })

  test('⭐ 页面上不渲染任何计数', async ({ page }) => {
    /**
     * The product rule, and the easiest place in the app to break it by accident:
     * a queue heading is exactly where a count gets added because every other table
     * in the product has one.
     */
    await page.goto('/#/vault')
    await page.getByTestId('vault-view-recall').click()
    await expect(page.getByTestId('lesson-queue-item')).toHaveCount(2)

    const heading = await page.getByTestId('lesson-queue').innerText()
    for (const word of ['共', '条', '还剩', '欠']) {
      expect(heading, `队列里出现了「${word}」`).not.toContain(word)
    }
  })

  test('⭐ 队列行没有标题', async ({ page }) => {
    /**
     * ⭐ A title would make the list scannable, and a scannable list of things you
     * owe is a to-do list — which `项目总纲` §2.1⑤ rules out. The row carries
     * `content` because the reader has to read something.
     */
    await page.goto('/#/vault')
    await page.getByTestId('vault-view-recall').click()
    await expect(page.getByTestId('lesson-queue-item').first()).toBeVisible()

    const row = page.getByTestId('lesson-queue-item').first()
    await expect(row).not.toContainText('标题')
    // And the relative time is there, because 「多久以前」 is the one fact in the
    // row that makes the visit feel like a re-read rather than an item to clear.
    await expect(row).toContainText(/\d+ (天|个月|年)前|今天/)
  })

  test('⭐ 四个评分按钮，第一个不是「忘了」', async ({ page }) => {
    /**
     * For a lesson `again` means 「我的想法变了」 — the same decision spec 028 made
     * for a note's `again`, and the reader meets both queues. 「我忘了」 would be
     * wrong for both: it labels the most valuable answer this queue collects as a
     * lapse.
     */
    await page.goto('/#/vault')
    await page.getByTestId('vault-view-recall').click()

    const row = page.getByTestId('lesson-queue-item').first()
    await expect(row.getByTestId('lesson-rate-again')).toHaveText('我的想法变了')
    const whole = await row.innerText()
    expect(whole).not.toContain('忘了')
  })

  test('⏱ 评分会发出请求，然后这一条离开队列', async ({ page }) => {
    const seen: string[] = []
    await page.route('**/api/v1/lessons/*/review', async (route) => {
      seen.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      })
    })

    await page.goto('/#/vault')
    await page.getByTestId('vault-view-recall').click()
    await expect(page.getByTestId('lesson-queue-item')).toHaveCount(2)

    await page.getByTestId('lesson-queue-item').first().getByTestId('lesson-rate-good').click()
    expect(seen, '评分没有发请求').toHaveLength(1)
  })
})

test.describe('记一条教训（spec 030）', () => {
  test('⭐ 表单里说清楚「没有入队按钮」', async ({ page }) => {
    /**
     * ⭐ The sentence has to be on the screen. There is no 「入队」 button — there
     * cannot be, the endpoint does not exist — and a reader who has just been told
     * 「已经在队列上」 and can see no queue will ask. One line removes the only
     * question this screen can raise.
     */
    await routeLessons(page, LESSONS)
    await routeRetrospective(page)
    await page.goto('/#/retrospective')

    await page.getByTestId('lesson-open').click()
    await expect(page.getByTestId('lesson-auto-note')).toContainText('没有「入队」这个按钮可点')
    // And nothing anywhere on the page is offering one.
    await expect(page.getByTestId('lesson-enrol')).toHaveCount(0)
  })

  test('空白的教训不能提交', async ({ page }) => {
    await routeLessons(page, LESSONS)
    await routeRetrospective(page)
    await page.goto('/#/retrospective')
    await page.getByTestId('lesson-open').click()

    await expect(page.getByTestId('lesson-submit')).toBeDisabled()
    await page.getByTestId('lesson-body').fill('   ')
    await expect(page.getByTestId('lesson-submit')).toBeDisabled()
    await page.getByTestId('lesson-body').fill('先看批价')
    await expect(page.getByTestId('lesson-submit')).toBeEnabled()
  })

  test('⭐ 提交只发一次请求，且没有第二个调用', async ({ page }) => {
    /**
     * ⭐ **One call, asserted by counting.** The whole of red line 7 from the
     * client's side is that recording a lesson and scheduling it are the same
     * request — a two-step "record then enrol" client is a client that can leave an
     * unscheduled lesson behind, which is the failure the red line is about.
     */
    const bodies: string[] = []
    await page.route(`**/api/v1/reviews/${encodeURIComponent(REVIEW_ID)}/lesson`, async (route) => {
      bodies.push(route.request().postData() ?? '')
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          lesson: {
            lesson_id: 'lesson_1700000000009',
            review_id: 'review_1700000000000',
            content: '先看批价',
            created_at: '2026-09-28T00:00:00.000Z',
          },
          state: 'learning',
          due_at: '2026-09-28T00:00:00.000Z',
        }),
      })
    })
    let enqueueCalls = 0
    await page.route('**/api/v1/lessons/*/enrol*', async (route) => {
      enqueueCalls += 1
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    })

    await routeLessons(page, LESSONS)
    await routeRetrospective(page)
    await page.goto('/#/retrospective')
    await page.getByTestId('lesson-open').click()
    await page.getByTestId('lesson-body').fill('先看批价')
    await page.getByTestId('lesson-submit').click()

    await expect(page.getByTestId('lesson-notice')).toContainText('已经在队列上')
    expect(bodies, '应该只发一次请求').toHaveLength(1)
    expect(enqueueCalls, '不应该存在「入队」这一步 —— 它没有端点').toBe(0)
  })
})
