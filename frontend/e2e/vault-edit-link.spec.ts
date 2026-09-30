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
  links: { to_kind: string; to_id: string; to_title: string | null }[]
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
          // The fixture resolves the target's title the way the backend does,
          // because a mock that echoes the request back without it would render a
          // raw id and the two tests below would fail for the wrong reason. This
          // is the shape of the bug that was fixed: a link row can only be named
          // when the server fills the name in, not when the client asks for one.
          const target = rows.find((candidate) => candidate.id === payload.to_id)
          row.links.push({
            ...payload,
            to_title: target === undefined ? null : target.title,
          })
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

    // ⭐⭐ **The comparison is over the note's own text, and it used to be over the
    // whole panel — which is a different test and a worse one.**
    //
    // ⭐ The panel is not one thing: ⭐ it holds 「这条笔记是什么」 ⭐ (title, body,
    // tags) ⭐ and 「关于这条笔记还知道些什么」 ⭐ (enrolment, the review history, the
    // outgoing links, the backlinks). ⭐ The second half is **filled in by requests
    // that were still in flight when this test took its snapshot** ⭐ — ⭐ the panel
    // said 「在查它是不是在队列上…」 ⭐ and said 「它没有回到我面前」 ⭐ a moment before,
    // ⭐ and then said both of them differently. ⭐ A byte-for-byte comparison over
    // that region is a comparison of two moments in a race, ⭐ which is why it only
    // happened to pass: ⭐ the two moments landed close together on a quiet machine.
    //
    // ⭐ Adding the review history made the race lose, ⭐ because there is now a
    // second request whose answer appears *inside* the snapshot window. ⭐ ⭐ The
    // test was not wrong about the product; ⭐ it was wrong about its scope, ⭐ and a
    // correct feature is the thing that exposes it.
    //
    // ⭐ `readNote` is the scope the assertion meant all along: ⭐ 「取消」 ⭐ must leave
    // **the note** ⭐ exactly as it was, ⭐ and the other four regions are answers to
    // other questions ⭐ that this test never made.
    const readNote = async (target: Page) => ({
      title: await target.getByTestId('note-detail').locator('h2').innerText(),
      body: await target.getByTestId('note-preview').innerText(),
    })
    const before = await readNote(page)

    await page.getByTestId('note-edit-open').click()
    await page.getByTestId('note-edit-title').fill('这个标题不该留下')
    await page.getByTestId('note-edit-cancel').click()

    await expect(page.getByTestId('note-editor')).toHaveCount(0)
    await expect(page.getByTestId('note-detail')).toContainText('批价是渠道库存的先行指标')
    await expect(page.getByTestId('note-detail')).not.toContainText('这个标题不该留下')
    expect(await readNote(page)).toEqual(before)

    // ⭐ **And the panel is still there afterwards**, ⭐ because a test that stopped
    // comparing it could also stop checking that cancelling did not unmount the
    // note. ⭐ One assertion, ⭐ not the whole text.
    await expect(page.getByTestId('note-preview')).toBeVisible()
  })
})

test.describe('复习流水（spec 045 · 补上 spec 028 留下的问题）', () => {
  test('「我复习过 5 次，为什么今天又来了」有一个答案', async ({ page }) => {
    // ⭐⭐ **This is the test that closes a question spec 028 opened and left open.**
    //
    // spec 028 made 「改写笔记」 a `reset` rather than quietly moving the due date,
    // and gave the reason as 「我复习过 5 次，为什么今天又来了」. ⭐ The mechanism was
    // built — `note_reviews` is append-only, `reset` is one of its outcomes, ⭐ and
    // `GET /notes/{id}/reviews` has returned the whole history since. ⭐ Nothing ever
    // *displayed* it, ⭐ so the answer existed and there was no place to read it: ⭐ a
    // note you edited would reappear on schedule ⭐ and you would have no way to learn
    // you were looking at a second pass over different text.
    //
    // ⭐ **The assertion is on the `reset` row specifically**, ⭐ not on 「there is a
    // history」. ⭐ A history that renders only the ordinary reviews answers the count
    // and still hides the edit — ⭐ and the edit is the part that is surprising.
    await page.route('**/api/v1/notes**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname
      const json = (status: number, body: unknown) =>
        route.fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify(body),
        })

      const note = { ...seed()[0], links: [], schedule: null }
      void note

      if (path === '/api/v1/notes/tags') return json(200, ['宏观'])
      if (path === '/api/v1/notes/due') return json(200, [])
      if (path.endsWith('/backlinks')) return json(200, [])

      if (path.endsWith('/schedule')) {
        // ⭐ **The note IS on the queue** ⭐ — the history is only rendered for an
        // enrolled note, ⭐ and a fixture answering 404 here would exercise the wrong
        // branch and pass for the wrong reason.
        return json(200, {
          note_id: 'note_1700000000000',
          state: 'review',
          due_at: '2026-10-03T00:00:00.000Z',
          enrolled_at: '2026-09-01T00:00:00.000Z',
          updated_at: '2026-09-29T00:00:00.000Z',
        })
      }
      if (path.endsWith('/reviews')) {
        // ⭐ **Four rows, and the two unusual ones are the point.** ⭐ Two ordinary
        // reviews, one `reset`, ⭐ and — ⭐ **added because a mutation check found the
        // fixture had no `deferred` row at all** ⭐ — one `defer`. ⭐ Written
        // newest-first, which is the order the product's own list uses, ⭐ so the test
        // would fail if the panel re-sorted them.
        return json(200, [
          {
            id: 'rev_4',
            note_id: 'note_1700000000000',
            outcome: 'reset',
            rating: null,
            reviewed_at: '2026-09-29T00:00:00.000Z',
            duration_ms: 0,
            from_due_at: '2026-09-30T00:00:00.000Z',
            to_due_at: '2026-10-03T00:00:00.000Z',
            from_state: 'review',
            to_state: 'review',
          },
          {
            // ⭐⭐ **`deferred`, and it is here for a measured reason.** ⭐ The first
            // version of this fixture had three rows ⭐ — ⭐ two `reviewed` and one
            // `reset` ⭐ — ⭐ and a mutant that dropped the `outcome === 'reviewed'`
            // half of the rating guard **survived**, ⭐ because with no `deferred` row
            // in the fixture there was nothing for it to mis-render. ⭐
            //
            // ⭐ **A fixture that only holds the cases the code handles is a fixture
            // that agrees with the code.** ⭐ The three outcomes exist, ⭐ and the one
            // that carries no rating is the one that proves the guard.
            //
            // ⭐ `rating: null` is not a choice here: ⭐ `defer` in spec 028 is 「我的
            // 想法变了，以后再说」 ⭐ and asking for a grade with that is asking the
            // reader to score a decision they explicitly declined to make.
            id: 'rev_3',
            note_id: 'note_1700000000000',
            outcome: 'deferred',
            rating: null,
            reviewed_at: '2026-09-20T00:00:00.000Z',
            duration_ms: 0,
            from_due_at: '2026-09-22T00:00:00.000Z',
            to_due_at: '2026-10-01T00:00:00.000Z',
            from_state: 'review',
            to_state: 'review',
          },
          {
            id: 'rev_2',
            note_id: 'note_1700000000000',
            outcome: 'reviewed',
            rating: 'good',
            reviewed_at: '2026-09-12T00:00:00.000Z',
            duration_ms: 4000,
            from_due_at: '2026-09-12T00:00:00.000Z',
            to_due_at: '2026-09-22T00:00:00.000Z',
            from_state: 'review',
            to_state: 'review',
          },
          {
            id: 'rev_1',
            note_id: 'note_1700000000000',
            outcome: 'reviewed',
            rating: 'again',
            reviewed_at: '2026-09-05T00:00:00.000Z',
            duration_ms: 3000,
            from_due_at: '2026-09-05T00:00:00.000Z',
            to_due_at: '2026-09-12T00:00:00.000Z',
            from_state: 'review',
            to_state: 'review',
          },
        ])
      }
      if (path === '/api/v1/notes') return json(200, [seed()[0]])
      return json(200, seed()[0])
    })

    await openNote(page, '流动性收紧时周期股先跌')

    // ⭐ **The count, so 「4 次」 is a claim about the rows and not about a label.**
    await expect(page.getByTestId('note-detail')).toContainText('复习流水')
    await expect(page.getByTestId('note-detail')).toContainText('4 次')

    // ⭐ **The edit is named, in the reader's words.** ⭐ 「排程从头开始」 rather than
    // 「RESET」 ⭐ — ⭐ the row has to say what happened to the *schedule*, ⭐ which is
    // the thing the reader cannot see and the question they are asking about.
    await expect(page.getByTestId('note-detail')).toContainText('这条被我改过，排程从头开始')

    // ⭐ **A grade, in the spec's words, and the four forbidden words are absent.**
    // ⭐ `recall.spec.ts` asserts 「忘」/「失败」/「重来」/「错误」 never appear in the
    // review flow, ⭐ and the first version of the adapter's labels was written without
    // reading that. ⭐ `again` is 「我的想法变了」 — ⭐ which is what spec 028 says it
    // means for a note.
    await expect(page.getByTestId('note-detail')).toContainText('我的想法变了')
    for (const forbidden of ['忘了', '失败', '重来', '错误']) {
      await expect(page.getByTestId('note-detail')).not.toContainText(forbidden)
    }

    // ⭐ **And the new due date, because 「什么时候」 is half the question.** ⭐ The
    // date is truncated to a day on purpose ⭐ — ⭐ a review history shown to the
    // millisecond is a log, ⭐ and a log is not what a reader checks a schedule in.
    await expect(page.getByTestId('note-detail')).toContainText('下一次 2026-10-03')

    // ⭐⭐ **A `defer` row carries no grade, and the assertion is on the four labels
    // rather than on the row's whole text.**
    //
    // ⭐ The first version of this asserted the row's `innerText` exactly ⭐ and it
    // **should not have.** ⭐ The row is 「标签 · 时间戳 · 明细」 ⭐ and the timestamp
    // is rendered in **local time** ⭐ — ⭐ `2026-09-20T00:00:00Z` is `2026-09-20 08:00`
    // in UTC+8 and `2026-09-19 17:00` in UTC-7, ⭐ so an exact match would make this
    // test pass in Shanghai and fail in San Francisco. ⭐ `palette.spec.ts` and the
    // other timestamp assertions here already learned to assert the *day* ⭐; the row
    // text is where that habit was missing.
    //
    // ⭐ **What the guard is for, stated honestly.** ⭐ `deferred` and `reset` both
    // carry `rating: null`, ⭐ and the adapter guards on
    // `outcome === 'reviewed' && rating !== null`. ⭐ ⭐ **A mutant that weakens the
    // `rating` half is rejected by `tsc`** ⭐ — ⭐ `rating` is `ReviewRating | null`,
    // ⭐ so `rating !== undefined` does not narrow away `null` ⭐ and
    // `RATING_LABEL[review.rating]` will not type-check. ⭐ ⭐ That is **not** the same
    // as a test killing it, ⭐ and it is reported as its own verdict: ⭐ the type
    // system is a real guard here, ⭐ it is simply not a test.
    //
    // ⭐ **So the `deferred` row earns its place on coverage, not on the guard.** ⭐
    // Two of the three outcomes were rendered by this file before it; ⭐ 「我说以后再看」
    // — ⭐ spec 028's word for 「我的想法变了，以后再说」 ⭐ — ⭐ was in the source and
    // in no test, ⭐ so a typo in it would have shipped. ⭐ The four labels below are
    // the assertion: ⭐ none of them may appear on a row the reader declined to grade.
    const deferRow = page
      .getByTestId('note-detail')
      .locator('ol li')
      .filter({ hasText: '我说以后再看' })
    expect(await deferRow.count(), '应当有一行讲「我说以后再看」').toBe(1)
    await expect(deferRow).toContainText('下一次 2026-10-01')
    for (const grade of ['我的想法变了', '想起来了，但慢', '记得', '不用想']) {
      await expect(
        deferRow,
        `「我说以后再看」不该带评分「${grade}」`,
      ).not.toContainText(grade)
    }

    // ⭐ **The duration is not shown.** The table has it, ⭐ and `duration_ms` is the
    // one field a self-scoring instinct says to display — ⭐ but 「你复习了 3 秒」
    // invites the reader to optimise their own recall instead of reading, ⭐ and
    // spec 028's copy work is entirely about moving them away from that.
    await expect(page.getByTestId('note-detail')).not.toContainText('4000')

    // ⭐⭐ **The `reset` row is marked, and the assertion is on a computed style.**
    //
    // ⭐ Rule 7 puts meaning in colour ⭐ and rule 5 says a category is marked with a
    // 2px rule rather than a pill ⭐ — ⭐ so the contract is a **2px left rule in a
    // different colour**, ⭐ and this is the one place in the product where it decides
    // something: ⭐ 「这条被我改过」 is the only event in a review history whose
    // consequence differs, ⭐ because it wiped the schedule.
    //
    // ⭐ **Computed style, not a class name** — ⭐ the pattern `palette.spec.ts` set for
    // the 2px brass cursor. ⭐ A class assertion passes just as happily on a renamed
    // utility as on the intended border, ⭐ and this row's whole point is that it looks
    // different from the three rows above it.
    // ⭐ ⭐ **And that is not a hypothetical.** ⭐ `globals.css`'s `.mark` sets
    // `border-left: 2px solid var(--color-rule)` in a rule outside every `@layer`, ⭐
    // so it beat the utility classes ⭐ and **every row of every log rendered with the
    // same left rule** ⭐ for as long as those rows carried it. ⭐ No class-name
    // assertion could have seen that, ⭐ because the class was present ⭐ and correct ⭐
    // — ⭐ it was the cascade that was wrong.
    const ruleColours = await page
      .getByTestId('note-detail')
      // ⭐ **Scoped to the list that follows the 复习流水 heading**, ⭐ not to every
      // `li` with a 2px border. ⭐ The naive version found **five**: ⭐ the three review
      // rows ⭐ plus the outgoing-link rows ⭐ and the link picker's ⭐ — ⭐ and the
      // assertion 「every row is unmarked except one」 ⭐ would then be about four
      // components at once. ⭐ The review history is an `<ol>`, ⭐ and the other two
      // are `<ul>`s ⭐ — ⭐ which is not a coincidence: ⭐ 「次序是重点」 is the reason
      // that list is an ordered one.
      .locator('ol li')
      .evaluateAll((els) =>
        els.map((el) => {
          const style = getComputedStyle(el)
          return {
            label: (el.textContent ?? '').slice(0, 12),
            width: style.borderLeftWidth,
            colour: style.borderLeftColor,
          }
        }),
      )
    expect(ruleColours.length, '每条流水都应该是一行').toBe(4)
    const reset = ruleColours.find((row) => row.label.includes('改过'))
    const ordinary = ruleColours.filter((row) => !row.label.includes('改过'))
    expect(reset, '应当有一行讲「这条被我改过」').toBeTruthy()
    // ⭐ **Transparency matched as a shape, not as one string** ⭐ — ⭐ the first
    // version compared `borderLeftColor` to the literal `rgba(0, 0, 0, 0)` ⭐ and
    // failed, ⭐ because Tailwind v4 emits the keyword `transparent`, ⭐ which the
    // browser reports back as `rgba(0, 0, 0, 0)` in some engines and as `transparent`
    // in others. ⭐ `palette.spec.ts` already learned this for the brass cursor ⭐ and
    // the answer is a pattern, ⭐ not a literal ⭐ — ⭐ and a literal here would have
    // been a test that passes on one browser and fails on another.
    const isTransparent = (colour: string) =>
      /^rgba\(0,\s*0,\s*0,\s*0\)$/.test(colour) || colour === 'transparent'
    for (const row of ordinary) {
      expect(row.width, '未标记的行也保留 2px，避免文字跳动').toBe('2px')
      expect(isTransparent(row.colour), `未标记的行左规应当是透明的，实得 ${row.colour}`).toBe(
        true,
      )
    }
    // ⭐ And the marked row is **2px in a different colour**, ⭐ not 「some other
    // class」 ⭐ — ⭐ which is the difference between asserting the design and
    // asserting the implementation.
    expect(reset?.width).toBe('2px')
    expect(
      isTransparent(reset?.colour ?? ''),
      '「这条被我改过」应当有色左规',
    ).toBe(false)
  })

  test('没入队的笔记不显示流水 —— 「它没有回来过」不是关于这条笔记的事实', async ({
    page,
  }) => {
    // ⭐ **The branch, not the other one.** ⭐ A note that was never enroled has no
    // review history, ⭐ and 「它没有回来过」 ⭐ would be a true statement about the
    // wrong thing — ⭐ it says the note has never come back, ⭐ when the truth is that
    // nobody ever asked it to.
    await page.route('**/api/v1/notes**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname
      const json = (status: number, body: unknown) =>
        route.fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify(body),
        })
      if (path === '/api/v1/notes/tags') return json(200, ['宏观'])
      if (path === '/api/v1/notes/due') return json(200, [])
      if (path.endsWith('/backlinks')) return json(200, [])
      // ⭐ 404 = not enrolled, which is the product's own answer for this.
      if (path.endsWith('/schedule')) return json(404, { detail: 'no schedule' })
      if (path === '/api/v1/notes') return json(200, [seed()[0]])
      return json(200, seed()[0])
    })

    await openNote(page, '流动性收紧时周期股先跌')
    await expect(page.getByTestId('note-enrol')).toBeVisible()
    // ⭐ And the enrolment control is *the* thing on screen, ⭐ because 「请它回来」
    // is the only action this note offers.
    await expect(page.getByTestId('note-detail')).not.toContainText('复习流水')
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

  test('搜不到目标笔记时，已有的引用仍然显示它的标题', async ({ page }) => {
    // The defect this pins. The detail panel used to resolve a target's name from
    // the notes currently loaded, so a link the reader had written turned into a
    // raw id the moment the search box narrowed the list. A row's rendering was
    // depending on unrelated screen state.
    //
    // The mechanism is the same search box used in the test above, run *after* the
    // link exists. Nothing about the link changed; only what the list holds.
    await routeVault(page)
    await openNote(page, '流动性收紧时周期股先跌')
    await page.getByTestId('note-link-open-picker').click()
    await page.getByTestId('note-link-search').fill('批价')
    await page.getByTestId('note-link-option').first().click()
    await expect(page.getByTestId('note-links')).toContainText('批价是渠道库存的先行指标')

    // The detail panel survives the list narrowing, so the way to prove the target
    // is not in the list is to assert the list no longer holds it. Counting rows
    // would pin the search's own result count, which is a different fact and
    // would make this test fail for an unrelated reason.
    await page.keyboard.press('Escape')
    const vaultSearch = page.getByPlaceholder('搜标题与正文')
    await vaultSearch.fill('流动性')
    await expect(page.getByRole('row').filter({ hasText: '批价' })).toHaveCount(0)

    // The row is still there and still named. Under the old code this was the id.
    await expect(page.getByTestId('note-links')).toContainText('批价是渠道库存的先行指标')
    await expect(page.getByTestId('note-link-id')).toHaveCount(0)
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
