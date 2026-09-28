/**
 * Searching the vault, in the browser (spec 027).
 *
 * The FTS5 behaviour itself is pinned by pytest — trigram's floor, the
 * `instr`/`LIKE` difference, the index following an edit. None of that can be
 * observed here, because the fixtures answer `/api/v1/**` from a table.
 *
 * So these tests are about the half that *is* the browser's: that the box sends
 * what was typed, that two characters are not quietly dropped on the way out,
 * that a tag and a query travel together, and — the one that matters for trust —
 * that 「没找到」 reads differently from 「你还没有笔记」.
 *
 * ⭐ A search box that returns an indistinguishable empty state is worse than no
 * search box: a reader who half-remembers a note types a word, sees nothing,
 * and concludes the note was never written. The two empties are separated here
 * so that cannot happen quietly.
 */

import { expect, test, type Page } from '@playwright/test'

interface Recorded {
  path: string
  query: URLSearchParams
}

/** Answer `/api/v1/notes` from a small table, and record what was asked for. */
async function routeNotes(
  page: Page,
  rows: { title: string; body: string; tags: string[] }[],
): Promise<Recorded[]> {
  const seen: Recorded[] = []

  await page.route('**/api/v1/notes**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/notes/tags') {
      const tags = [...new Set(rows.flatMap((r) => r.tags))].sort()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(tags),
      })
      return
    }
    seen.push({ path: url.pathname, query: url.searchParams })

    const q = url.searchParams.get('q') ?? ''
    const tag = url.searchParams.get('tag') ?? ''
    // A substring match, which is what the real short path does — close enough
    // for the UI assertions and honest about being a fixture.
    const found = rows
      .filter((r) => q === '' || r.title.includes(q) || r.body.includes(q))
      .filter((r) => tag === '' || r.tags.includes(tag))
      .map((r, index) => ({
        id: `note_${1700000000000 + index}`,
        title: r.title,
        body: r.body,
        as_of: null,
        created_at: '2026-09-28T00:00:00.000Z',
        updated_at: '2026-09-28T00:00:00.000Z',
        tags: r.tags,
        links: [],
        symbols: [],
      }))

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(found),
    })
  })

  return seen
}

/**
 * ⭐ The third row carries the tag `宏观` but **not** the searched text.
 *
 * Without it, "filter by tag then ignore the query" and "search then filter by
 * tag" return the same rows, and the composition test passes with the query
 * silently dropped. A mutation check on the API caught exactly that. Every
 * composition assertion below therefore has a note that the tag matches and the
 * text does not.
 */
const VAULT: { title: string; body: string; tags: string[] }[] = [
  { title: '利率上行的观察', body: '## 观察\n\n- 利率上行先杀周期股', tags: ['宏观'] },
  { title: '宏观但正文无关', body: '完全另一件事', tags: ['宏观'] },
  { title: '白酒行业产能出清', body: '批价是先行指标', tags: ['行业'] },
  { title: '估值要看现金流', body: '自由现金流优先，不要看利润', tags: ['估值'] },
]

async function openVault(page: Page): Promise<void> {
  await page.goto('/#/vault')
  await expect(page.getByTestId('vault-search')).toBeVisible()
}

test.describe('搜索知识库（spec 027 · 检索）', () => {
  test('⭐ 两个字也照发 —— 中文最常搜的就是两个字', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-search').fill('利率')
    await page.getByTestId('vault-search-submit').click()
    await expect(page.getByTestId('data-row')).toHaveCount(1)

    // ⭐ The property, asserted on the wire rather than on the result: a client
    // that imposed its own three-character minimum would still return the right
    // row here, because the fixture is a substring match. Only the request
    // distinguishes the two implementations.
    const last = seen[seen.length - 1]
    expect(last?.query.get('q')).toBe('利率')
    expect(last?.query.get('q')).toHaveLength(2)
  })

  test('一个词搜到一行，并且列出的是标题', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-search').fill('利率上行')
    await page.getByTestId('vault-search-submit').click()

    await expect(page.getByTestId('data-row')).toHaveCount(1)
    await expect(page.getByTestId('data-row')).toContainText('利率上行的观察')
  })

  test('未搜索时整个库都在（记 4 条，不是 3 条）', async ({ page }) => {
    // ⭐ Every count below depends on the fixture having four rows. The
    // 「宏观但正文无关」 row is what makes a tag wider than a query.
    await routeNotes(page, VAULT)
    await openVault(page)
    await expect(page.getByTestId('data-row')).toHaveCount(4)
  })

  test('⭐ 搜不到与「你还没有笔记」是两句话', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)

    // First: the vault is not empty, so the "write one" copy must not appear.
    await expect(page.getByTestId('data-row')).toHaveCount(4)
    await expect(page.getByTestId('vault-empty')).toHaveCount(0)

    await page.getByTestId('vault-search').fill('一个不存在的词')
    await page.getByTestId('vault-search-submit').click()

    await expect(page.getByTestId('vault-no-match')).toBeVisible()
    await expect(page.getByTestId('vault-no-match')).toContainText('一个不存在的词')
    // ⭐ And the two never appear together — a reader must not be told to write a
    // note that already exists.
    await expect(page.getByTestId('vault-empty')).toHaveCount(0)
  })

  test('空库说的是另一句话', async ({ page }) => {
    await routeNotes(page, [])
    await openVault(page)

    await expect(page.getByTestId('vault-empty')).toBeVisible()
    await expect(page.getByTestId('vault-empty')).toContainText('这里还没有笔记')
    await expect(page.getByTestId('vault-no-match')).toHaveCount(0)
  })

  test('标签和检索一起发，两个条件同时生效', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    // ⭐ `先行` appears in one note, tagged 行业. Adding the 宏观 tag must empty
    // the list — and it does so *because the two filters compose*. A note tagged
    // 宏观 exists in the fixture, so "the tag won and the query was dropped" would
    // return a row instead of nothing, which is the failure this test exists for.
    await page.getByTestId('vault-search').fill('先行')
    await page.getByTestId('vault-search-submit').click()
    await expect(page.getByTestId('data-row')).toHaveCount(1)

    await page.getByTestId('vault-tag-宏观').click()
    await expect(page.getByTestId('vault-no-match')).toBeVisible()

    const last = seen[seen.length - 1]
    expect(last?.query.get('q')).toBe('先行')
    expect(last?.query.get('tag')).toBe('宏观')
  })

  test('只点标签不搜，就是那个标签下的全部', async ({ page }) => {
    // The other side of the same property: the tag alone is *wider* than the
    // combined query, so the two cannot be producing the same answer by accident.
    await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-tag-宏观').click()
    await expect(page.getByTestId('data-row')).toHaveCount(2)
    // Scoped with `filter` rather than asserted on the whole locator: two rows
    // match `data-row`, and `toContainText` on a multi-element locator is a
    // strict-mode violation rather than a failure — which reads as a harness
    // problem instead of an assertion one.
    await expect(
      page.getByTestId('data-row').filter({ hasText: '宏观但正文无关' }),
    ).toHaveCount(1)
  })

  test('清除把列表恢复成全部，而不是留在空结果上', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-search').fill('一个不存在的词')
    await page.getByTestId('vault-search-submit').click()
    await expect(page.getByTestId('vault-no-match')).toBeVisible()

    await page.getByTestId('vault-search-clear').click()
    await expect(page.getByTestId('data-row')).toHaveCount(4)
    await expect(page.getByTestId('vault-search')).toHaveValue('')

    const last = seen[seen.length - 1]
    // ⭐ Clearing sends **no** `q` at all rather than `q=`. Both mean "everything",
    // but only one of them is unambiguous at the call site, and the server treats
    // a whitespace-only query as no query — so this is the behaviour worth pinning.
    expect(last?.query.get('q')).toBeNull()
  })

  test('框里的字改了但没回车，就还没搜', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-search').fill('利率')
    await page.getByTestId('vault-search-submit').click()
    const afterSubmit = seen.length

    await page.getByTestId('vault-search').fill('改成了别的词')
    // Typing is not searching: one request per character would make the list
    // flicker through four states while a four-character word is typed.
    await expect(page.getByTestId('data-row')).toHaveCount(1)
    expect(seen.length).toBe(afterSubmit)
    await expect(page.getByTestId('vault-search-note')).toContainText('回车')
  })

  test('搜索框读标题与正文，不读标签 —— 而且界面上说清楚', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-search').fill('估值')
    await page.getByTestId('vault-search-submit').click()

    await expect(page.getByTestId('vault-search-note')).toContainText('标签不参与这次搜索')
  })

  test('页面里不渲染任何检索计数', async ({ page }) => {
    /**
     * ⭐ Consistent with `nav.spec.ts`: the product's own rule is 「一句陈述，无推送、
     * 无红点、无催促词」. A 「找到 3 条」 line turns a search into a scoreboard,
     * and the note count is one of the few numbers a reader could start climbing.
     * Asserted on the whole page rather than the nav, because a count added later
     * would more likely land next to the search box than in the sidebar.
     */
    await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-search').fill('利率')
    await page.getByTestId('vault-search-submit').click()
    await expect(page.getByTestId('data-row')).toHaveCount(1)

    const chrome = await page.getByTestId('vault-search-note').innerText()
    expect(chrome).not.toMatch(/[0-9]/)
  })
})
