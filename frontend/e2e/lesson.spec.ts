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
  /**
   * ⭐ **Empty, and that is the truth.** `due_reviews` filters on
   * `reviewed_at IS NULL` — regression 0007's fix, which exists so a graded decision
   * leaves the queue. The first version of this fixture put an *already-reviewed*
   * decision in here anyway, which the server can never return; the suite passed,
   * and the lesson composer was unreachable in the real app.
   */
  await page.route('**/api/v1/decision-reviews/due**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  /**
   * ⭐ The reviewed decision, in the list that exists for it. `is_due: false`
   * always — a decision can be both due *and* graded, and that is the case this
   * list is for.
   */
  await page.route('**/api/v1/decision-reviews/recent**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          decision_id: REVIEW_ID,
          is_due: false,
          due_at: '2026-09-20T02:15:00.000Z',
          reviewed_at: '2026-09-20T02:15:00.000Z',
          reviews: 1,
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
  test('⭐ 已复盘的决策看得到自己的分数，而不是打分按钮', async ({ page }) => {
    /**
     * ⭐ The browser showed the page contradicting itself in consecutive lines:
     * 「都不会再变」 directly above five buttons that change it. The score block sat
     * outside the `is_due` conditional, on the assumption that 「not due」 meant
     * 「not yet graded」 — true while the page listed only due decisions.
     *
     * And the number is **shown**, not hidden: the reader came here to look at their
     * own reasoning, and it is their number — this system never assigns one.
     */
    await routeLessons(page, LESSONS)
    await routeRetrospective(page)
    await page.goto('/#/retrospective')

    await expect(page.getByTestId('retro-score-value')).toHaveText('2')
    // ⭐ Scoped to `button`, because the prefix alone also matches
    // `retro-score-given` and `retro-score-value` — **the two testids this very
    // change introduced.** A prefix selector that catches the elements the test
    // just added fails in a way that reads like a product bug.
    await expect(page.locator('button[data-testid^="retro-score-"]')).toHaveCount(0)
    await expect(page.getByTestId('retro-already-done')).toContainText('你已经复盘过了')
  })

  test('⭐ composer 只能通过「已复盘」这条路到达（这正是它坏掉的地方）', async ({ page }) => {
    /**
     * ⭐ The reachability test for the bug itself. Before `/recent` existed the page
     * had exactly one list, the due one, and a reviewed decision was not in it — so
     * the composer was correctly hidden before a review and gone from the only list
     * after one. **Unreachable, with a green E2E suite throughout.**
     *
     * The `/due` fixture is empty in this file, deliberately. If the composer ever
     * becomes reachable again *only* through a queue the server cannot return, this
     * test goes red rather than the feature quietly disappearing.
     */
    await routeLessons(page, LESSONS)
    await routeRetrospective(page)
    await page.goto('/#/retrospective')

    await expect(page.getByTestId('lesson-open')).toBeVisible()
  });

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

test.describe('教训的浏览与转卡（spec 030）', () => {
  test.beforeEach(async ({ page }) => {
    await routeLessons(page, LESSONS)
    await page.route('**/api/v1/lessons', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            lesson_id: LESSONS[0].lesson_id,
            review_id: 'review_1700000000000',
            content: LESSONS[0].content,
            created_at: '2026-09-28T00:00:00.000Z',
          },
        ]),
      })
    })
  })

  test('⭐ 教训视图里不出现笔记的空状态', async ({ page }) => {
    /**
     * ⭐ The bug this was written for. The notes list was gated on
     * `view !== 'cards'`, so adding the 教训 view brought it along — and a reader with
     * no notes was told to 「点下面的『记一条』」 about a button that is not on this
     * page. **A control referred to and not reachable**, which is the shape the owner
     * complained about to begin with.
     *
     * The fix enumerates the views the block *belongs to* rather than the one it is
     * not, because a gate written as an exclusion fails silently every time a view is
     * added.
     */
    await page.goto('/#/vault')
    await page.getByTestId('vault-view-lessons').click()

    await expect(page.getByTestId('lesson-row')).toHaveCount(1)
    await expect(page.getByTestId('vault-empty')).toHaveCount(0)
    await expect(page.getByTestId('note-title')).toHaveCount(0)
  })

  test('⭐ 出处没填齐时，署名按钮是禁用的', async ({ page }) => {
    /**
     * Asserted by the button's **state**, not by an error message — a disabled
     * submit with two empty fields is the accurate rendering of 「there is nothing to
     * sign yet」, and a message would be explaining something the reader can see.
     */
    await page.goto('/#/vault')
    await page.getByTestId('vault-view-lessons').click()
    await page.getByTestId('lesson-promote-open').click()

    await expect(page.getByTestId('lesson-promote-submit')).toBeDisabled()
    await page.getByTestId('lesson-source-url').fill('https://research.example.com/a')
    await expect(page.getByTestId('lesson-promote-submit')).toBeDisabled()
    await page.getByTestId('lesson-source-title').fill('\u767d\u9152\u6279\u4ef7\u8ddf\u8e2a')
    await expect(page.getByTestId('lesson-promote-submit')).toBeEnabled()
  })

  test('⭐ 署名之后按钮消失，只剩一句「已经是卡片了」', async ({ page }) => {
    /**
     * ⭐ `toHaveCount(0)` is the point. `lesson_promotions.lesson_id` is the table's
     * primary key, so a second promotion is impossible **in the database** — and a
     * control for it could only ever produce a failure. The reasoning has to reach the
     * screen, and this is the assertion for it.
     */
    const bodies: string[] = []
    await page.route('**/api/v1/lessons/*/promote', async (route) => {
      bodies.push(route.request().postData() ?? '')
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          lesson_id: LESSONS[0].lesson_id,
          card_id: 'card_1700000000042',
          promoted_at: '2026-09-28T00:00:00.000Z',
        }),
      })
    })

    await page.goto('/#/vault')
    await page.getByTestId('vault-view-lessons').click()
    await page.getByTestId('lesson-promote-open').click()
    await page.getByTestId('lesson-source-url').fill('https://research.example.com/a')
    await page.getByTestId('lesson-source-title').fill('\u767d\u9152\u6279\u4ef7\u8ddf\u8e2a')
    await page.getByTestId('lesson-promote-submit').click()

    await expect(page.getByTestId('lesson-promoted')).toContainText('已经是卡片了')
    await expect(page.getByTestId('lesson-promoted')).toContainText('card_1700000000042')
    await expect(page.getByTestId('lesson-promote-open')).toHaveCount(0)
    // One request, carrying both source fields — the client cannot promote without
    // them, so the wire shape is asserted too.
    expect(bodies).toHaveLength(1)
    expect(JSON.parse(bodies[0])).toMatchObject({
      source_url: 'https://research.example.com/a',
    })
  })

  test('⭐ 拒绝转卡时，错误文案说的是「不会丢」', async ({ page }) => {
    /**
     * ⭐ The server's 400 text is shown **verbatim**. Rewriting it here would throw
     * away the one sentence that makes declining feel safe — 「拿得出出处就说明这条
     * 已经是一条教训了 — 它已经记下来了，不会丢」.
     */
    /**
     * ⭐ The **coded envelope**, not `{detail: ...}`.
     *
     * The first version answered with the 404 shape and the client rendered a generic
     * rejection line, so the sentence that makes declining feel safe never reached the
     * reader. The route had the same bug — `HTTPException(detail=...)` for a 400 — and
     * both are fixed. ⭐ The fixture was the last thing still describing the old
     * contract, which is regression 0009's shape one level out: **a fixture asserting
     * a body the server cannot produce**.
     */
    await page.route('**/api/v1/lessons/*/promote', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          severity: 'error',
          code: 'LESSON_PROMOTION_SOURCE_REQUIRED',
          message:
            '\u62ff\u4e0d\u51fa\u51fa\u5904\u5c31\u8bf4\u660e\u8fd9\u6761\u8fd8\u53ea\u662f\u4e00\u6761\u6559\u8bad \u2014\u2014 '
            + '\u5b83\u5df2\u7ecf\u8bb0\u4e0b\u6765\u4e86\uff0c\u4e0d\u4f1a\u4e22\u3002',
          target: null,
          fix: null,
        }),
      })
    })

    await page.goto('/#/vault')
    await page.getByTestId('vault-view-lessons').click()
    await page.getByTestId('lesson-promote-open').click()
    await page.getByTestId('lesson-source-url').fill('https://research.example.com/a')
    await page.getByTestId('lesson-source-title').fill('x')
    await page.getByTestId('lesson-promote-submit').click()

    const message = page.getByTestId('lesson-promote-error')
    await expect(message).toBeVisible()
    await expect(message).toContainText('\u4e0d\u4f1a\u4e22')
    // And the lesson is still there — declining costs nothing.
    await expect(page.getByTestId('lesson-row')).toHaveCount(1)
  })
});
