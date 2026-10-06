import { expect, test, type Page } from '@playwright/test'
import { acknowledgeLaunch, routeApi } from './fixtures'

/**
 * Changing what a live component is looking at, without remounting it.
 *
 * ## Why this file exists, and what it is deliberately not about
 *
 * A first version of this test navigated between two instruments and asserted
 * that the second one's record replaced the first one's. It passed against code
 * that still had the defect, and the reason is worth keeping because the mistake
 * generalises: `App.tsx` renders `<InstrumentPage key={market/code}>`, so switching
 * instruments *remounts* the page, the hook starts with no previous content, and
 * there is nothing to leak. The defect was real inside the shared runner and
 * unreachable from that page. Reading a hook in isolation is not the same as
 * reading what a page does with it.
 *
 * So this file targets a page with no `key`: the vault. It is one long-lived
 * component whose notes request is keyed on `[tag, query]`, both of which change
 * at runtime — clicking a tag filter, typing in the search box. Nothing remounts
 * it, so this is where a runner that cannot tell "the same question failed" from
 * "a different question is loading" actually reaches the reader.
 *
 * ## What unfixed looks like
 *
 * Click 方法 and the list keeps showing the previous tag's notes until 方法's notes
 * arrive. The reader reads the old list as the answer to the new filter. That is a
 * stale answer rather than a wrong one, and a far smaller harm than showing one
 * company's decisions under another's name — but it is the same mechanism, and it
 * is why `RequestRunner` now carries a resource key instead of depending on every
 * caller remembering to add a React `key`.
 */

const MACRO = {
  id: 'note-macro',
  title: '宏观：地产周期见底了吗',
  body: '宏观笔记的正文，只有宏观这一栏该出现它。',
  tags: ['宏观'],
  symbols: [],
  created_at: '2026-10-01T00:00:00.000Z',
  updated_at: '2026-10-01T00:00:00.000Z',
}
const METHOD = {
  id: 'note-method',
  title: '方法：先看渠道再看报表',
  body: '方法笔记的正文，只有方法这一栏该出现它。',
  tags: ['方法'],
  symbols: [],
  created_at: '2026-10-01T00:00:00.000Z',
  updated_at: '2026-10-01T00:00:00.000Z',
}

const ALL = [MACRO, METHOD]

/**
 * Answer the vault's own endpoints from one table, the way `vault-search.spec.ts`
 * does. `/api/v1/notes` filters by the `tag` the client sends, so the tag filter
 * is genuinely exercised rather than simulated by returning everything always.
 */
async function vaultApi(
  page: Page,
  options: { failAfterFirst?: boolean; delayMs?: number; gate?: Gate } = {},
) {
  let listCalls = 0
  await page.route('**/api/v1/notes**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/notes/tags') {
      await route.fulfill({ json: ['宏观', '方法'] })
      return
    }
    if (url.pathname === '/api/v1/notes/due') {
      await route.fulfill({ json: [] })
      return
    }
    listCalls += 1
    if (options.gate && listCalls > 1) {
      await options.gate.wait()
    }
    /**
     * A real network takes time, and that time is the whole window in which stale
     * content is on screen.
     *
     * Measured twice, and the second measurement is the one that matters: a plain
     * `delay` is **not** enough, because Playwright's assertions retry until they
     * see a steady state, so a transient wrong frame is never observed. A test
     * that waits for the right answer cannot tell "never wrong" from "wrong for a
     * moment". Holding the response open with a gate the test opens itself is what
     * makes the intermediate state observable.
     */
    await new Promise((resolve) => setTimeout(resolve, options.delayMs ?? 0))
    if (options.failAfterFirst && listCalls > 1) {
      await route.fulfill({
        status: 503,
        json: { code: 'NOTE_LIST_UNAVAILABLE', message: '取不到笔记' },
      })
      return
    }
    const tag = url.searchParams.get('tag')
    const q = url.searchParams.get('q')
    let rows = ALL
    if (tag) rows = rows.filter((n) => n.tags.includes(tag))
    if (q) rows = rows.filter((n) => (n.title + n.body).includes(q))
    await route.fulfill({ json: rows })
  })
  await page.route('**/api/v1/lessons**', (route) => route.fulfill({ json: [] }))
  await acknowledgeLaunch(page)
}

/** A response the test holds shut until it says otherwise. */
export interface Gate {
  wait: () => Promise<void>
  open: () => void
}

function makeGate(): Gate {
  // Sticky: once opened, every later request passes straight through. A gate that
  // only released its first waiter deadlocked the second request, which is the
  // test hanging rather than the product failing.
  let opened = false
  const waiting: Array<() => void> = []
  const wait = () =>
    opened
      ? Promise.resolve()
      : new Promise<void>((resolve) => {
          waiting.push(resolve)
        })
  const open = () => {
    opened = true
    while (waiting.length > 0) waiting.shift()?.()
  }
  return { wait, open }
}

test.beforeEach(async ({ page }) => {
  await routeApi(page, {
    'GET /api/v1/today': {
      attention: [],
      due: { cards: { queue: 'cards', count: 0 }, reviews: { queue: 'reviews', count: 0 } },
    },
  })
})

test.describe('换筛选条件时不重挂载（回归 · 2026-10-06）', () => {
  test('the list shown is the one the filter asked for', async ({ page }) => {
    const gate = makeGate()
    await vaultApi(page, { gate })
    await page.goto('/#/vault')

    await expect(page.getByText('宏观：地产周期见底了吗')).toBeVisible()

    await page.getByTestId('vault-tag-方法').click()

    // ⭐ **While the new answer is still in flight, the old list must already be
    // gone.** The response is held shut by the gate, so this asserts a real
    // intermediate frame rather than waiting for a steady state. A plain delay was
    // measured and did not work: Playwright retries its assertions, so a transient
    // wrong frame is never seen. This is the assertion that fails against a runner
    // which republishes the previous resource.
    await expect(page.getByText('宏观：地产周期见底了吗')).toHaveCount(0)

    gate.open()
    // ...and once it arrives, it is the requested tag's note.
    await expect(page.getByText('方法：先看渠道再看报表')).toBeVisible()
    await expect(page.getByText('宏观：地产周期见底了吗')).toHaveCount(0)
  })

  test('going back to a tag shows that tag again', async ({ page }) => {
    const gate = makeGate()
    await vaultApi(page, { gate })
    await page.goto('/#/vault')

    await page.getByTestId('vault-tag-方法').click()
    // The gate is shut, so this request has not answered yet. Open it before
    // waiting on the answer -- asserting first would wait forever.
    gate.open()
    await expect(page.getByText('方法：先看渠道再看报表')).toBeVisible()

    // The gate is sticky from here, so this request flows straight through.
    await page.getByTestId('vault-tag-宏观').click()

    await expect(page.getByText('宏观：地产周期见底了吗')).toBeVisible()
    await expect(page.getByText('方法：先看渠道再看报表')).toHaveCount(0)
  })

  test('a filter that fails does not leave the previous filter on screen', async ({ page }) => {
    /**
     * The half a fix which only clears on load would miss. If the request fails and
     * the runner republishes its previous content, the reader is looking at the
     * previous tag's notes while the interface shows the new tag as selected — a
     * stale list presented as the answer to a filter that failed.
     */
    await vaultApi(page, { failAfterFirst: true })
    await page.goto('/#/vault')
    await expect(page.getByText('宏观：地产周期见底了吗')).toBeVisible()

    await page.getByTestId('vault-tag-方法').click()

    await expect(page.getByText(/取不到笔记|无法读取/)).toBeVisible()
    await expect(page.getByText('宏观：地产周期见底了吗')).toHaveCount(0)
  })
})
