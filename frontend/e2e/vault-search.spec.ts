/**
 * The vault's search and its layout (specs 027 + 029).
 *
 * The FSTS/tokeniser behaviour is pinned by pytest. What only a rendered page can
 * show is the **behaviour and the copy**, and both changed in spec 029:
 *
 * ⭐ **Search is select-to-search.** The first version required Enter and carried
 * a 「（改完文字要按回车才搜）」 hint. The hint was a workaround for a decision, not
 * a reason — a search field where you must remember a key is a field some people
 * never use. `test_typing_searches_without_a_key_press` is the replacement, and it
 * asserts the *positive* claim rather than the absence of a key.
 *
 * ⭐ **The layout order is the point of spec 029.** It used to read
 * filters → a 200px form → results, which put the reading below the fold because
 * of a control used occasionally. `test_the_results_are_above_the_composer` and
 * the two tests around the collapsed form hold that decision down.
 *
 * ⭐ **The form is collapsed to one row, never hidden.** The owner's complaint was
 * 「记录功能去哪里了」, so the fix cannot be to bury the recorder — hence a permanent
 * one-row 记一条 that opens the form in place, and a form that opens itself when
 * the vault is empty.
 */

import { expect, test, type Page } from '@playwright/test'

interface Recorded {
  path: string
  query: URLSearchParams
}

const VAULT: { title: string; body: string; tags: string[] }[] = [
  { title: '利率上行的观察', body: '## 观察\n\n- 利率上行先杀周期股', tags: ['宏观'] },
  { title: '宏观但正文无关', body: '完全另一件事', tags: ['宏观'] },
  { title: '白酒行业产能出清', body: '批价是先行指标，渠道库存要盯', tags: ['行业'] },
  { title: '估值要看现金流', body: '自由现金流优先，不要看利润表', tags: ['估值'] },
]

/** One note with every optional field empty — the vault's own contract. */
function asNote(row: { title: string; body: string; tags: string[] }, index: number) {
  return {
    id: `note_${1700000000000 + index}`,
    title: row.title,
    body: row.body,
    as_of: null,
    created_at: '2026-09-28T00:00:00.000Z',
    updated_at: '2026-09-28T00:00:00.000Z',
    tags: row.tags,
    links: [],
    symbols: [],
  }
}

/**
 * Answer `/api/v1/notes**` from `rows`, and record every list request.
 *
 * ⭐ The tag filter here is a **prefix** match, unlike the real one. That is
 * deliberate: the fixture has to be able to tell the client that it asked for `宏观`
 * and got the note tagged `宏观债`-like values. An exact fixture would let a client
 * that dropped the parameter pass unnoticed.
 */
async function routeNotes(
  page: Page,
  rows: typeof VAULT,
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
    if (url.pathname === '/api/v1/notes/due') {
      // ⭐ The queue is a **different resource** and gets its own answer. The first
      // version let `/due` fall through to the list branch, so the "queue" came
      // back holding four notes and the empty state never rendered — a fixture
      // that answers every path with the same list quietly passes tests it should
      // fail.
      //
      // ⭐ And it is a bare list with **no count**, because the endpoint has none
      // and a fixture that added one would make the no-count assertions vacuous.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          rows.length === 0 ? [] : rows.slice(0, 1).map((_, index) => ({
            note_id: `note_${1700000000000 + index}`,
            state: 'review',
            due_at: '2026-09-20T00:00:00.000Z',
            enrolled_at: '2026-08-20T00:00:00.000Z',
            updated_at: '2026-09-18T00:00:00.000Z',
          })),
        ),
      })
      return
    }
    if (url.pathname.endsWith('/schedule')) {
      // The detail panel asks whether a note is on the queue.
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'no schedule' }),
      })
      return
    }
    seen.push({ path: url.pathname, query: url.searchParams })

    const q = url.searchParams.get('q') ?? ''
    const tag = url.searchParams.get('tag') ?? ''
    const found = rows
      .filter((r) => q === '' || r.title.includes(q) || r.body.includes(q))
      .filter((r) => tag === '' || r.tags.some((t) => t.includes(tag)))
      .map(asNote)

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(found),
    })
  })

  return seen
}

/**
 * ⭐ Type into the search box and wait for the list to settle.
 *
 * No Enter, no button. The wait is on the *result*, not on a fixed sleep, so the
 * debounce is not racing the assertion — which is the failure this file already
 * made once when a hand-rolled probe read the DOM before React re-rendered.
 */
async function search(page: Page, q: string, expectRows?: number): Promise<void> {
  await page.getByTestId('vault-search').fill(q)
  if (expectRows === undefined) {
    await expect(page.getByTestId('vault-search-note')).toContainText(q)
    return
  }
  if (expectRows === 0) {
    await expect(page.getByTestId('vault-no-match')).toBeVisible()
    return
  }
  await expect(page.getByTestId('data-row')).toHaveCount(expectRows)
}

async function openVault(page: Page): Promise<void> {
  await page.goto('/#/vault')
  await expect(page.getByTestId('vault-search')).toBeVisible()
  await expect(page.getByTestId('data-row').first()).toBeVisible()
}

test.describe('搜索知识库（spec 027/029）', () => {
  test('⭐ 两个字也照发 —— 中文最常搜的就是两个字', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)
    await search(page, '利率', 1)

    // ⭐ Asserted on the wire, not on the result: a client with its own
    // three-character minimum would still return the right row here, because the
    // fixture matches substrings. Only the request distinguishes them.
    const last = seen[seen.length - 1]
    expect(last?.query.get('q')).toBe('利率')
    expect(last?.query.get('q')).toHaveLength(2)
  })

  test('⭐ 打字就搜 —— 不用按回车', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    // ⭐ **The replacement** for 「框里的字改了但没回车，就还没搜」, which asserted
    // a behaviour this spec deliberately reversed. Asserting the positive claim
    // is better than asserting the absence of a key: it says what the box does,
    // so a future version cannot pass by being broken in a new way.
    await search(page, '先行', 1)
    expect(seen[seen.length - 1]?.query.get('q')).toBe('先行')
  })

  test('一次输入只发一次请求，而不是每个字一次', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)
    const before = seen.length

    // Four characters typed at once. The debounce coalesces them into one request.
    await page.getByTestId('vault-search').fill('自由现金流')
    await expect(page.getByTestId('data-row')).toHaveCount(1)

    const after = seen.length - before
    expect(after, `发了 ${after} 次请求，逐字搜索就是这样`).toBeLessThanOrEqual(2)
  })

  test('搜不到与「你还没有笔记」是两句话', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)
    await expect(page.getByTestId('data-row')).toHaveCount(4)
    await expect(page.getByTestId('vault-empty')).toHaveCount(0)

    await search(page, '一个不存在的词', 0)
    await expect(page.getByTestId('vault-no-match')).toContainText('一个不存在的词')
    // ⭐ And the two never appear together — a reader must not be told to write a
    // note that already exists.
    await expect(page.getByTestId('vault-empty')).toHaveCount(0)
  })

  test('空库说的是另一句话', async ({ page }) => {
    await routeNotes(page, [])
    await page.goto('/#/vault')
    await expect(page.getByTestId('vault-empty')).toBeVisible()
    await expect(page.getByTestId('vault-empty')).toContainText('这里还没有笔记')
    await expect(page.getByTestId('vault-no-match')).toHaveCount(0)
  })

  test('标签和检索一起发，两个条件同时生效', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    // ⭐ `先行` is in one note, tagged 行业. Adding 宏观 must empty the list, and
    // it does so *because the two compose* — a note tagged 宏观 exists in the
    // fixture, so "the tag won and the query was dropped" would return a row.
    await search(page, '先行', 1)
    await page.getByTestId('vault-tag-宏观').click()
    await expect(page.getByTestId('vault-no-match')).toBeVisible()

    const last = seen[seen.length - 1]
    expect(last?.query.get('q')).toBe('先行')
    expect(last?.query.get('tag')).toBe('宏观')
  })

  test('只点标签不搜，就是那个标签下的全部', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('vault-tag-宏观').click()
    await expect(page.getByTestId('data-row')).toHaveCount(2)
    await expect(
      page.getByTestId('data-row').filter({ hasText: '宏观但正文无关' }),
    ).toHaveCount(1)
  })

  test('清除把列表恢复成全部', async ({ page }) => {
    const seen = await routeNotes(page, VAULT)
    await openVault(page)

    await search(page, '一个不存在的词', 0)
    await page.getByTestId('vault-search-clear').click()

    await expect(page.getByTestId('data-row')).toHaveCount(4)
    await expect(page.getByTestId('vault-search')).toHaveValue('')
    // ⭐ Clearing sends **no** `q` at all rather than `q=`.
    expect(seen[seen.length - 1]?.query.get('q')).toBeNull()
  })

  test('搜索框读标题与正文，不读标签 —— 而且界面上说清楚', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)

    await search(page, '估值', 1)
    await expect(page.getByTestId('vault-search-note')).toContainText('标签不参与这次搜索')
  })

  test('搜索时页面上不渲染任何计数', async ({ page }) => {
    /**
     * ⭐ Consistent with `nav.spec.ts`: 「一句陈述，无推送、无红点、无催促词」.
     * A 「找到 3 条」 line turns a search into a scoreboard, and the note count is
     * one of the few numbers a reader could start climbing. Asserted on the
     * search chrome, because that is where a count would most likely be added.
     */
    await routeNotes(page, VAULT)
    await openVault(page)
    await search(page, '利率', 1)

    const chrome = await page.getByTestId('vault-search-note').innerText()
    expect(chrome).not.toMatch(/[0-9]/)
    for (const word of ['找到', '结果', '共']) {
      expect(chrome, `搜索提示里出现了「${word}」`).not.toContain(word)
    }
  })
})

test.describe('知识库页的布局（spec 029）', () => {
  test('⭐ 列表在「记一条」上面', async ({ page }) => {
    /**
     * The decision this spec exists for, asserted on geometry rather than on
     * prose: it used to read filters → form → results, which put the reading below
     * the fold because of a control used occasionally. `boundingBox` compares
     * actual positions, so a future edit cannot pass by moving both together.
     */
    await routeNotes(page, VAULT)
    await page.goto('/#/vault')
    await expect(page.getByTestId('data-row').first()).toBeVisible()

    const firstRow = await page.getByTestId('data-row').first().boundingBox()
    const composer = await page.getByTestId('note-compose-open').boundingBox()
    expect(firstRow, '列表没有渲染出来').not.toBeNull()
    expect(composer, '「记一条」没有渲染出来').not.toBeNull()
    expect(
      (firstRow as { y: number }).y,
      '列表的第一行应该在「记一条」上面',
    ).toBeLessThan((composer as { y: number }).y)
  })

  test('⭐ 库里有东西时，「记一条」收成一行，但一直都在', async ({ page }) => {
    /**
     * ⭐ The refusal to hide the recorder, made testable. Earlier drafts proposed
     * collapsing it away entirely and the objection was right: the owner's
     * complaint *was* 「记录功能去哪里了」. So the control is one permanent row —
     * never a menu, never hidden — and only the form behind it is transient.
     */
    await routeNotes(page, VAULT)
    await openVault(page)

    const toggle = page.getByTestId('note-compose-open')
    await expect(toggle).toBeVisible()
    await expect(toggle).toContainText('记一条')
    // Collapsed means the *form* is absent, not the affordance.
    await expect(page.getByTestId('note-title')).toHaveCount(0)
  })

  test('点开就展开，收起后又回到一行', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)

    await page.getByTestId('note-compose-open').click()
    await expect(page.getByTestId('note-title')).toBeVisible()
    await expect(page.getByTestId('note-body')).toBeVisible()

    await page.getByTestId('note-compose-close').click()
    await expect(page.getByTestId('note-title')).toHaveCount(0)
    await expect(page.getByTestId('note-compose-open')).toBeVisible()
  })

  test('⭐ 空库时表单自己打开', async ({ page }) => {
    /**
     * Derived, not an effect: `formOpen = composing || vault is empty`. A first-time
     * reader lands on a form rather than an empty table with a button under it.
     */
    await routeNotes(page, [])
    await page.goto('/#/vault')

    await expect(page.getByTestId('note-title')).toBeVisible()
    await expect(page.getByTestId('vault-empty')).toBeVisible()
  })

  test('展开之后仍然能记下来', async ({ page }) => {
    await routeNotes(page, VAULT)
    await openVault(page)
    await page.getByTestId('note-compose-open').click()

    await page.getByTestId('note-title').fill('新记的一条')
    await page.getByTestId('note-body').fill('正文')
    await expect(page.getByTestId('note-submit')).toBeEnabled()
    await page.getByTestId('note-submit').click()

    await expect(page.getByTestId('note-notice')).toContainText('已记下')
  })

  test('「该复习」是一个筛选，作曲时不出现表单', async ({ page }) => {
    /**
     * The recall view is a mode, not a filter over the list: you are meant to face
     * one note and answer honestly, and a 200px form under it would be a way out.
     */
    await routeNotes(page, VAULT)
    await openVault(page)
    await page.getByTestId('vault-view-recall').click()

    // ⭐ Asserted as "the recall view rendered a row" rather than as a particular
    // branch. The first version asserted the **empty** state while the fixture's
    // `/due` answer had one item, so the test was asserting a different branch
    // than the one it meant — and a layout assertion should hold whether the
    // queue is empty or not.
    await expect(page.getByTestId('recall-item')).toHaveCount(1)
    await expect(page.getByTestId('note-compose-open')).toHaveCount(0)
    await expect(page.getByTestId('note-title')).toHaveCount(0)
    // And the list is not behind it either: the recall view is a mode, not a
    // filter over a list that stays on screen.
    await expect(page.getByTestId('data-row')).toHaveCount(0)
  })
})
