/**
 * The note recall queue in the browser (spec 028).
 *
 * The FSRS behaviour is pinned by pytest. What only a rendered page can show is
 * the **copy**, and copy is where this feature's real decisions live:
 *
 * ⭐ `again` is 「我的想法变了」 — the one answer that means the note has been
 * overtaken by the reader's own thinking. Dressing it as a lapse would teach them
 * to avoid it.
 * ⭐ **No count, anywhere.** A digit-free assertion over the whole rendered queue,
 * because the number is the thing a well-meaning 「还剩 N 条」 would add, and it is
 * the one value that turns "some things I wrote need revisiting" into a tally.
 * ⭐ Enrolment is a **decision**, offered on the note — never automatic, and
 * never with a list of the notes that have not been enrolled yet.
 */

import { expect, test, type Page } from '@playwright/test'

/** One due note, with the note itself served when the reader opens it. */
const DUE = {
  note_id: 'note_1700000000000',
  state: 'review',
  due_at: '2026-09-20T00:00:00.000Z',
  enrolled_at: '2026-08-20T00:00:00.000Z',
  updated_at: '2026-09-18T00:00:00.000Z',
}

const NOTE = {
  id: DUE.note_id,
  title: '流动性收紧时周期股先跌',
  body: '## 观察\n\n- 利率上行先杀周期股\n- 成长股滞后三周',
  as_of: null,
  created_at: '2026-08-20T00:00:00.000Z',
  updated_at: '2026-09-18T00:00:00.000Z',
  tags: ['宏观'],
  links: [],
  symbols: [],
}

interface Seen {
  method: string
  path: string
  query: URLSearchParams
}

/**
 * Route the queue, the note, and the answer verbs.
 *
 * `enrolled` flips when the reader enrols, so the second half of the test can
 * watch the button become a statement without reloading.
 */
async function routeRecall(
  page: Page,
  options: { due?: typeof DUE[]; enrolled?: boolean } = {},
): Promise<Seen[]> {
  const seen: Seen[] = []
  let enrolled = options.enrolled ?? false

  await page.route('**/api/v1/notes**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()
    seen.push({ method, path, query: url.searchParams })

    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })

    if (path.endsWith('/due')) return json(options.due ?? [])
    if (path.endsWith('/tags')) return json(['宏观'])
    if (path === `/api/v1/notes/${NOTE.id}/schedule`) {
      if (method === 'POST') {
        enrolled = true
        return json({ ...DUE, note_id: NOTE.id, state: 'learning' })
      }
      if (!enrolled) return json({ detail: '没有排程' }, 404)
      return json(DUE)
    }
    if (path === `/api/v1/notes/${NOTE.id}/reviews`) return json([])
    if (path === `/api/v1/notes/${NOTE.id}/review` || path.endsWith('/defer')) {
      return json({
        id: 'note_review_1',
        note_id: NOTE.id,
        outcome: path.endsWith('/defer') ? 'deferred' : 'reviewed',
        rating: null,
        reviewed_at: '2026-09-28T00:00:00.000Z',
        duration_ms: null,
        from_due_at: DUE.due_at,
        to_due_at: '2026-10-28T00:00:00.000Z',
        from_state: 'review',
        to_state: 'review',
      })
    }
    if (path === `/api/v1/notes/${NOTE.id}`) return json(NOTE)
    if (path === '/api/v1/notes') return json([NOTE])
    return json({ detail: `e2e fixture missing for ${path}` }, 404)
  })

  return seen
}

async function openRecall(page: Page): Promise<void> {
  await page.goto('/#/vault')
  await expect(page.getByTestId('vault-view-recall')).toBeVisible()
  await page.getByTestId('vault-view-recall').click()
}

test.describe('笔记的复习队列（spec 028）', () => {
  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('⭐ 那个答案是「我的想法变了」，不是「忘了」', async ({ page }) => {
    await routeRecall(page, { due: [DUE] })
    await openRecall(page)
    await page.getByTestId('recall-item').click()
    await expect(page.getByTestId('recall-active')).toBeVisible()

    const again = page.getByTestId('recall-again')
    await expect(again).toBeVisible()
    // ⭐ The forbidden words, checked on the rendered button rather than the
    // constant, so a reword in the component is what fails.
    for (const word of ['忘', '失败', '重来', '错误']) {
      await expect(again, `按钮上出现了「${word}」`).not.toContainText(word)
    }
  })

  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('⭐ 复习时看到的是全文，不是一个让人猜的标题', async ({ page }) => {
    await routeRecall(page, { due: [DUE] })
    await openRecall(page)
    await page.getByTestId('recall-item').click()

    // A note's title is not a prompt — 「关于流动性的一点想法」 only tests
    // whether the reader can guess from their own headline. A card's claim *is* a
    // prompt, which is why cards may hide it and notes may not.
    const active = page.getByTestId('recall-active')
    await expect(active).toContainText('利率上行先杀周期股')
    await expect(active).toContainText('成长股滞后三周')
  })

  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('⭐ 整个队列页面上不出现任何数字', async ({ page }) => {
    /**
     * Asserted over the rendered queue, not over a constant, because the failure
     * being guarded against is a well-meaning 「还剩 3 条」 added to the heading or
     * the empty state — neither of which is a string any unit test holds.
     */
    await routeRecall(page, { due: [DUE, { ...DUE, note_id: 'note_1700000000002' }] })
    await openRecall(page)
    await expect(page.getByTestId('recall-item')).toHaveCount(2)

    const text = await page.getByTestId('recall-empty').or(page.locator('body')).first().innerText()
    const chrome = await page.locator('body').innerText()
    // Only the queue's own area, minus the note list behind it.
    const queueArea = chrome.split('记一条')[0] ?? chrome
    expect(queueArea).not.toMatch(/\d+\s*条/)
    for (const word of ['还剩', '还有', '共', '待复习']) {
      expect(queueArea, `队列区出现了「${word}」`).not.toContain(word)
    }
    expect(text.length).toBeGreaterThan(0)
  })

  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('空队列说的是状态，不是欠账', async ({ page }) => {
    await routeRecall(page, { due: [] })
    await openRecall(page)

    await expect(page.getByTestId('recall-empty')).toBeVisible()
    await expect(page.getByTestId('recall-empty')).not.toContainText(/\d/)
    for (const word of ['欠', '剩', '还有', '待办']) {
      await expect(page.getByTestId('recall-empty')).not.toContainText(word)
    }
  })

  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('⭐ 入队是一个决定，而且就放在那条笔记上', async ({ page }) => {
    const seen = await routeRecall(page, { due: [], enrolled: false })
    await page.goto('/#/vault')
    await page.getByTestId('data-row').first().click()
    await expect(page.getByTestId('note-detail')).toBeVisible()

    // Offered, not reported as a debt — and with no count of what is not yet
    // enrolled, because computing one would mean inventing a tally to refuse.
    const enrol = page.getByTestId('note-enrol')
    await expect(enrol).toBeVisible()
    await expect(enrol).not.toContainText(/\d/)
    await enrol.click()

    await expect(page.getByTestId('note-enrolled')).toBeVisible()
    expect(seen.some((r) => r.method === 'POST' && r.path.endsWith('/schedule'))).toBe(true)
  })

  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('「还没想清楚」推后，且不评分', async ({ page }) => {
    const seen = await routeRecall(page, { due: [DUE] })
    await openRecall(page)
    await page.getByTestId('recall-item').click()
    await page.getByTestId('recall-defer').click()

    await expect(page.getByTestId('recall-active')).toHaveCount(0)
    const call = seen.find((r) => r.path.endsWith('/defer'))
    expect(call?.method).toBe('POST')
  })

  test.beforeEach(async ({ page }) => {
    await routeLessonQueue(page)
  })

  test('评分之后回到队列，而队列仍然没有数字', async ({ page }) => {
    const seen = await routeRecall(page, { due: [DUE] })
    await openRecall(page)
    await page.getByTestId('recall-item').click()
    await page.getByTestId('recall-good').click()

    await expect(page.getByTestId('recall-active')).toHaveCount(0)
    expect(seen.some((r) => r.path.endsWith('/review') && r.method === 'POST')).toBe(true)
    await expect(page.locator('body')).not.toContainText(/\d+\s*条/)
  })
})

/**
 * The lesson queue, which fetches on mount (spec 030).
 *
 * ⭐ Added because the suite was green **and** printing `ECONNREFUSED` for
 * `/api/v1/lessons/due`: nothing here mocks it, so the request fell through the dev
 * proxy to a backend that is not running, and no assertion looked at the queue. A
 * bare array, because the server returns one — a fixture that invented a wrapper
 * would make any count assertion vacuous.
 */
async function routeLessonQueue(page: Page): Promise<void> {
  await page.route('**/api/v1/lessons**', async (route) => {
    const url = new URL(route.request().url())
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(url.pathname === '/api/v1/lessons/due' ? [] : []),
    })
  })
}
