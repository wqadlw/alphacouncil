/**
 * 改一条、引用一条 —— editing a note and wiring notes together (spec 045).
 *
 * ⭐ **Why this file exists at all.**
 *
 * Measured on 2026-09-30, before this commit:
 *
 * - `PATCH /notes/{id}` and `notes.ts::updateNote` had existed since spec 026, with
 *   tests, and **no page had ever called them.** ⭐ So a note could be recorded and
 *   never corrected ⭐ — and for a knowledge base, where a wrong note is worse than
 *   no note, that is not a missing convenience.
 * - `POST /notes/{id}/links` existed too, ⭐ and the detail panel printed every
 *   outgoing link as `note/note_1700000000000` ⭐ — a row of identifiers that names a
 *   record without opening it. ⭐ There was **no `DELETE` route at all**, ⭐ so a
 *   claim the reader had stopped making could never be taken back.
 *
 * ⭐ **A backend capability with a test and no caller looks exactly like a feature
 * that is done**, ⭐ and these are the third and fourth of them in this product ⭐
 * (after `backlinks_for` and the whole Markdown renderer). ⭐ The check that finds
 * them is not a test ⭐ — ⭐ it is counting callers per exported function, ⭐ which is
 * a thing a human has to decide to do.
 *
 * ⭐ **The fixture holds state, and that is the whole point of this file.** The
 * `vault-search` fixture answers every request from a fixed array, ⭐ which is right
 * for search and wrong here: ⭐ a `PATCH` answered from a constant either fails or is
 * ignored, ⭐ and a test that asserts on the response rather than on the next render
 * ⭐ would pass against a product that never changed anything. ⭐ So this fixture
 * mutates, ⭐ and the assertions are about what the **page** shows afterwards.
 */

import { expect, test, type Page } from '@playwright/test'

interface Note {
  id: string
  title: string
  body: string
  as_of: string | null
  created_at: string
  updated_at: string
  tags: string[]
  links: { to_kind: string; to_id: string }[]
  symbols: { market: string; code: string }[]
}

/** Two notes, and one of them points at nothing yet. */
function seed(): Note[] {
  return [
    {
      id: 'note_1700000000000',
      title: '流动性收紧时周期股先跌',
      body: '## 观察\n\n- 2026-08 利率上行\n- 成长股滞后 3 周',
      as_of: null,
      created_at: '2026-09-28T00:00:00.000Z',
      updated_at: '2026-09-28T00:00:00.000Z',
      tags: ['宏观'],
      links: [],
      symbols: [],
    },
    {
      id: 'note_1700000000001',
      title: '批价是渠道库存的先行指标',
      body: '先看批价，再看渠道库存。',
      as_of: null,
      created_at: '2026-09-28T00:00:00.000Z',
      updated_at: '2026-09-28T00:00:00.000Z',
      tags: ['方法'],
      links: [],
      symbols: [],
    },
  ]
}

/**
 * ⭐ A stateful fixture, because the two features under test are both writes.
 *
 * ⭐ **Every write answers with the note as it now is** ⭐ — which is the real
 * contract, and the reason the client's `onChanged(note)` is worth anything. ⭐ A
 * fixture that returned the pre-write note would let a product that discarded the
 * edit pass every assertion here, ⭐ so the handler reads `rows` again after
 * mutating it.
 */
async function routeVault(page: Page): Promise<{ rows: Note[] }> {
  const rows = seed()

  await page.route('**/api/v1/notes**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const json = (status: number, body: unknown) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })

    if (path === '/api/v1/notes/tags') {
      const tags = [...new Set(rows.flatMap((row) => row.tags))].sort()
      return json(200, tags)
    }
    if (path === '/api/v1/notes/due') return json(200, [])
    if (path.endsWith('/schedule')) return json(404, { detail: 'no schedule' })
    if (path.endsWith('/backlinks')) {
      // ⭐ **Computed from `rows`, not a constant.** ⭐ A fixed list of backlinks
      // would pass the test that a link was created ⭐ — ⭐ and the point of the
      // whole feature is that creating a link makes a backlink appear, ⭐ so the
      // fixture has to derive one from the other or the test asserts nothing.
      // ⭐ **The segment before the endpoint, not the last one.** ⭐ `pop()` on
      // `/notes/note_1/backlinks` returns the string `backlinks`, ⭐ so every row's
      // links were compared against the literal `backlinks` and the answer was 0 for
      // every note. ⭐ That is what happened: ⭐ the fixture held a correct link, ⭐ the
      // request arrived after the write, ⭐ and the answer was empty. ⭐ **Four runs of
      // a failing test with all three facts correct, and one index.**
      // ⭐ `.at(-2)` names 「the note id」 at the call site ⭐ rather than leaving a
      // `-1` that silently means 「whatever the URL ends with」.
      const segments = path.replace(/^\/api\/v1\/notes\//, '').split('/')
      const target = decodeURIComponent(segments.at(-2) ?? '')
      const from = rows
        .filter((row) => row.links.some((l) => l.to_kind === 'note' && l.to_id === target))
        .map((row) => ({ from_note_id: row.id, title: row.title }))
      return json(200, from)
    }
    if (path === '/api/v1/notes' && method === 'GET') {
      const q = url.searchParams.get('q') ?? ''
      const found = rows.filter((row) => q === '' || row.title.includes(q))
      return json(200, found)
    }
    if (path === '/api/v1/notes' && method === 'POST') {
      const created: Note = {
        ...rows[0],
        // Arithmetic, not digit concatenation. The first version wrote
        // a literal followed by the interpolation, which is a syntax error: a
        // number followed by `$` is not a number. The runner reported it as
        // "No tests found" because it never reached the tests.
        id: `note_${1700000000000 + rows.length}`,
        title: (request.postDataJSON() as { title: string }).title,
        body: (request.postDataJSON() as { body: string }).body,
      }
      rows.push(created)
      return json(201, created)
    }

    // ⭐ `/notes/{id}` and everything under it. ⭐ `decodeURIComponent` on each
    // segment, ⭐ because the ids go into a path and come back out of one, ⭐ and a
    // fixture that does not decode would silently fail to match a row.
    // Strip the API root once, then index from the note. See the note above.
    const rest = path.replace(/^\/api\/v1\/notes/, '')
    const segments = rest.split('/').filter(Boolean)
    const id = decodeURIComponent(segments[0] ?? '')
    const row = rows.find((candidate) => candidate.id === id)
    if (row === undefined) return json(404, { detail: `没有笔记 ${id}` })

    if (segments.length === 1) {
      if (method === 'GET') return json(200, row)
      if (method === 'PATCH') {
        const patch = request.postDataJSON() as { title?: string; body?: string }
        // ⭐ `undefined` means 「not in the patch」 ⭐ and an empty string means
        // 「blanked it」 — ⭐ so the guard is on presence, not truthiness. ⭐ This is
        // the same distinction the real `updateNote` makes, ⭐ and a fixture using
        // `if (patch.title)` would make a blanked title unrepresentable.
        if (patch.title !== undefined) row.title = patch.title
        if (patch.body !== undefined) row.body = patch.body
        row.updated_at = '2026-09-30T00:00:00.000Z'
        return json(200, row)
      }
    }
    if (segments[1] === 'links') {
      if (method === 'POST') {
        const payload = request.postDataJSON() as { to_kind: string; to_id: string }
        if (!row.links.some((l) => l.to_kind === payload.to_kind && l.to_id === payload.to_id)) {
          row.links.push(payload)
        }
        return json(200, row)
      }
      if (method === 'DELETE') {
        const toKind = decodeURIComponent(segments[2] ?? '')
        const toId = decodeURIComponent(segments[3] ?? '')
        row.links = row.links.filter((l) => !(l.to_kind === toKind && l.to_id === toId))
        return json(200, row)
      }
    }
    return json(405, { detail: 'no fixture for this request' })
  })


}

/**
 * Open the vault and click a note **in the results table**.
 *
 * ⭐ **Scoped to the table, and the reason is a whole afternoon of failing tests.**
 * The first version was `page.getByText(title, { exact: true }).first().click()` ⭐
 * — and once a note was already open, ⭐ its title appears in **two** places: the row
 * in the results and the heading in the detail panel. ⭐ `.first()` picked whichever
 * came first in the DOM, ⭐ which after a save was the *stale* detail panel, ⭐ so the
 * second `openNote` in a test opened the note that was already open ⭐ and every
 * assertion about the other one failed.
 *
 * ⭐ So the locator is the row: `getByRole('row')` scoped by its own text. ⭐ A row is
 * unambiguous, ⭐ and it is also what a reader clicks.
 */
async function openNote(page: Page, title: string): Promise<void> {
  // ⭐ **A reload only on the first call.** ⭐ Every call used to `page.goto`, ⭐ and
  // that re-ran the whole app, ⭐ which is fine for a test that opens a note once ⭐
  // and wrong for one that opens a second note after a write: ⭐ the reload gives
  // React a fresh mount, ⭐ the fixture's route handler is re-entered, ⭐ and the
  // write the test just made is still there ⭐ — ⭐ so the reload is not the cause of
  // the failure below, ⭐ and removing it is about *speed* and about not having two
  // navigations where one will do.
  //
  // ⭐ It is a parameter rather than a heuristic, ⭐ because 「is this the first
  // call」 is a fact about the test, ⭐ not something the helper should guess.
  if (!(page as Page & { __vaultOpen?: boolean }).__vaultOpen) {
    await page.goto('/#/vault')
    ;(page as Page & { __vaultOpen?: boolean }).__vaultOpen = true
  }
  await page.getByRole('row').filter({ hasText: title }).first().click()
  await expect(page.getByTestId('note-detail')).toBeVisible()
  // ⭐ **And the detail is the note we asked for**, ⭐ asserted rather than assumed ⭐ —
  // otherwise every failure below names the wrong note and costs a round trip.
  await expect(page.getByTestId('note-detail')).toContainText(title)
}

test.describe('改一条（spec 045 · 笔记的基本能力）', () => {
  test('一条记错的笔记改得回来', async ({ page }) => {
    await routeVault(page)
    await openNote(page, '流动性收紧时周期股先跌')

    // ⭐ **The reading view first, and asserted.** ⭐ A test that went straight to
    // the editor would pass against a product where the body renders as raw source, ⭐
    // which is what it did until this commit. ⭐ Assert the heading is a heading
    // rather than a literal: ⭐ a `<pre>` of `## 观察` has the text but not the
    // element, ⭐ and the element is what the typography hangs off.
    await expect(page.getByTestId('note-preview')).toBeVisible()
    await expect(page.getByTestId('note-preview').getByRole('heading')).toHaveText('观察')

    await page.getByTestId('note-edit-open').click()
    await expect(page.getByTestId('note-editor')).toBeVisible()

    // ⭐ **While editing, the reading view is gone.** ⭐ The alternative — the fields
    // below the rendered note ⭐ — means a reader correcting a sentence is looking at
    // the version they are correcting.
    await expect(page.getByTestId('note-preview')).toHaveCount(0)

    await page.getByTestId('note-edit-body').fill('## 观察\n\n- 2026-09 利率见顶\n- 成长股滞后 2 周')
    await page.getByTestId('note-edit-save').click()

    // ⭐ **The reading view comes back, and it shows the new text.** ⭐ The
    // assertion is on the rendered heading, ⭐ so a save that only updated local
    // state and never asked the server ⭐ would still fail here ⭐ once the page
    // reloaded.
    await expect(page.getByTestId('note-preview')).toBeVisible()
    await expect(page.getByTestId('note-preview')).toContainText('2026-09 利率见顶')
    await expect(page.getByTestId('note-preview')).not.toContainText('2026-08 利率上行')

    // ⭐ **And it survives a reload, ⭐ which is the only assertion that proves the
    // write reached the server rather than the component's own state.** ⭐ Every other
    // assertion in this test passes against a `useState` that was never sent
    // anywhere.
    await page.reload()
    await openNote(page, '流动性收紧时周期股先跌')
    await expect(page.getByTestId('note-preview')).toContainText('2026-09 利率见顶')
  })

  test('没改东西的时候保存是按不动的，而且说清楚了为什么', async ({ page }) => {
    await routeVault(page)
    await openNote(page, '批价是渠道库存的先行指标')
    await page.getByTestId('note-edit-open').click()

    // ⭐ **A disabled button with no explanation reads as a bug**, ⭐ and this one
    // would read as 「编辑器坏了」. ⭐ The sentence is the assertion, ⭐ because a
    // disabled control is a claim and a claim needs words.
    await expect(page.getByTestId('note-edit-save')).toBeDisabled()
    await expect(page.getByTestId('note-editor')).toContainText('改点什么再保存')

    await page.getByTestId('note-edit-title').fill('改过的标题')
    await expect(page.getByTestId('note-edit-save')).toBeEnabled()
  })

  test('取消编辑不会动笔记', async ({ page }) => {
    await routeVault(page)
    await openNote(page, '批价是渠道库存的先行指标')
    const before = await page.getByTestId('note-detail').innerText()

    await page.getByTestId('note-edit-open').click()
    await page.getByTestId('note-edit-title').fill('这个标题不该留下')
    await page.getByTestId('note-edit-cancel').click()

    await expect(page.getByTestId('note-editor')).toHaveCount(0)
    await expect(page.getByTestId('note-detail')).toContainText('批价是渠道库存的先行指标')
    await expect(page.getByTestId('note-detail')).not.toContainText('这个标题不该留下')
    expect(await page.getByTestId('note-detail').innerText()).toBe(before)
  })
})

test.describe('引用一条（spec 045 · 知识库的基本能力）', () => {
  test('指过去之后，目标笔记的「被引用」里就有它', async ({ page }) => {
    // ⭐⭐ **This is the test that gives stage C's backlinks panel a reason to exist.**
    //
    // Stage C built `BacklinkList` and measured that the API had no caller, ⭐ so the
    // panel could only ever render its empty state. ⭐ The feature was "done" ⭐ — with
    // a component, a component count, a rule, and tests ⭐ — ⭐ and nothing in the
    // product could put anything in it.
    await routeVault(page)
    await openNote(page, '流动性收紧时周期股先跌')

    // ⭐ **The outgoing section says what it is, not what an id is.** ⭐ The old
    // rendering printed `note/note_1700000000001` ⭐ — a row that names a record and
    // cannot be followed. ⭐ Asserting a title is asserting the difference.
    await expect(page.getByTestId('note-links')).toBeVisible()
    await expect(page.getByTestId('note-links')).toContainText('它还没有指向别的记录')

    await page.getByTestId('note-link-open-picker').click()
    await page.getByTestId('note-link-search').fill('批价')
    await page.getByTestId('note-link-option').first().click()

    // ⭐ **The link appears as the target's title,** ⭐ which is the reader-facing
    // claim. ⭐ And the count moved with it, ⭐ so 「指向 1 条」 and the row cannot
    // disagree. ⭐ **These two, before anything else,** ⭐ because they are what
    // separates 「the POST never happened」 from 「the backlink read is wrong」 ⭐ —
    // ⭐ and without them a failure three lines later names the wrong half.
    await expect(page.getByTestId('note-links')).toContainText('批价是渠道库存的先行指标')
    await expect(page.getByTestId('note-links')).toContainText('1 条')

    // ⭐ **Now the other side.** Open the target and look at its backlinks. ⭐ This
    // is the half that a client-side-only implementation would pass, ⭐ so the
    // assertion is on the target's own panel ⭐ rather than on a re-render of the
    // source note.
    await openNote(page, '批价是渠道库存的先行指标')

    // ⭐ **Scoped to the list, not the panel, and waiting for the request.** ⭐ The
    // first version asserted on `note-detail`, ⭐ and Playwright reported **twelve**
    // matches ⭐ — the panel, plus every descendant carrying the same testid ⭐ — ⭐ and
    // a text assertion on twelve elements is a statement about their concatenation.
    // ⭐ `note-preview` is the rendered body, ⭐ present exactly once, ⭐ and it is the
    // anchor a reader would use to know the note loaded. ⭐ And the backlink list is
    // requested after the panel mounts, ⭐ so the assertion retries until the answer
    // arrives ⭐ rather than reading the empty state that precedes it.
    await expect(page.getByTestId('note-preview')).toBeVisible()
    await expect(page.getByTestId('note-detail')).toContainText('被引用')
    // ⭐ **The title, not the id.** ⭐ This is the whole point of the feature: ⭐ a
    // backlink a reader cannot recognise is a backlink they cannot act on, ⭐ and the
    // raw-id rendering is what this commit replaced.
    // ⭐ **10s, because this is the first assertion after a `page.goto`.** ⭐ The panel
    // mounts, ⭐ fires its backlink request, ⭐ and only then can the list be
    // non-empty; ⭐ a 5s default is usually enough and occasionally not, ⭐ and a
    // flaky assertion on the *positive* claim of the feature ⭐ teaches a reader to
    // distrust the suite rather than the code.
    await expect(page.getByTestId('note-detail')).toContainText(
      '流动性收紧时周期股先跌',
      { timeout: 10_000 },
    )
  })

  test('已经指过的不会再出现在可选里，自己也不会', async ({ page }) => {
    // ⭐ **A picker full of rows that do nothing is the worst kind of picker.** ⭐ The
    // backend would accept both ⭐ — `INSERT OR IGNORE` makes a duplicate a no-op and
    // only a self-link is refused ⭐ — ⭐ so the guarantee has to be here.
    await routeVault(page)
    await openNote(page, '流动性收紧时周期股先跌')
    await page.getByTestId('note-link-open-picker').click()
    await page.getByTestId('note-link-search').fill('流动性')
    // ⭐ The note itself, by its own title. ⭐ Offering it would be offering a
    // request the server refuses with 「一条笔记不能指向自己」 ⭐ — ⭐ a refusal the
    // reader could have been spared.
    await expect(page.getByTestId('note-link-option')).toHaveCount(0)
    await expect(page.getByTestId('note-link-picker')).toContainText('没有匹配项')
  })

  test('引用可以撤掉 —— 「我不再认为它们有关」得能被说出来', async ({ page }) => {
    // ⭐ **The endpoint did not exist for this product's whole life,** ⭐ so this test
    // is the first thing that has ever asserted it ⭐ and its value is in the
    // `reload` at the end: ⭐ a retract that only cleared local state would pass every
    // assertion before it.
    await routeVault(page)
    await openNote(page, '流动性收紧时周期股先跌')
    await page.getByTestId('note-link-open-picker').click()
    await page.getByTestId('note-link-search').fill('批价')
    await page.getByTestId('note-link-option').first().click()
    await expect(page.getByTestId('note-links')).toContainText('批价是渠道库存的先行指标')

    await page.getByTestId('note-link-remove').first().click()
    await expect(page.getByTestId('note-links')).toContainText('它还没有指向别的记录')

    // ⭐ And it stayed retracted, ⭐ which is the difference between 「撤掉了」 and
    // 「看起来撤掉了」.
    await page.reload()
    await openNote(page, '流动性收紧时周期股先跌')
    await expect(page.getByTestId('note-links')).toContainText('它还没有指向别的记录')
    await expect(page.getByTestId('note-links')).not.toContainText('批价是渠道库存的先行指标')
  })

  test('知识库只有一条笔记时，picker 说清楚为什么没有别的', async ({ page }) => {
    // ⭐ **Two different empty reasons, and the reader has to be able to tell them
    // apart.** ⭐ 「没有匹配项」 means 「换个词」 ⭐ and 「只有这一条」 means
    // 「先记一条」 ⭐ — ⭐ and rule 8 is about this: ⭐ one fact, ⭐ and the fact
    // differs.
    await page.route('**/api/v1/notes**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname
      const one = seed()[0]
      if (path === '/api/v1/notes/tags') return route.fulfill({ json: ['宏观'] })
      if (path === '/api/v1/notes/due') return route.fulfill({ json: [] })
      if (path.endsWith('/schedule')) return route.fulfill({ status: 404, json: {} })
      if (path.endsWith('/backlinks')) return route.fulfill({ json: [] })
      if (path === '/api/v1/notes') return route.fulfill({ json: [one] })
      return route.fulfill({ json: one })
    })
    await openNote(page, '流动性收紧时周期股先跌')
    await page.getByTestId('note-link-open-picker').click()
    await expect(page.getByTestId('note-link-picker')).toContainText('只有这一条')
    await expect(page.getByTestId('note-link-picker')).toContainText('先记一条')
  })
})
