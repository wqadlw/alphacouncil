/**
 * The knowledge vault (specs 026-028) — **cards and notes, side by side**.
 *
 * ## Why this page exists at all
 *
 * The product is 「面向实战的股市知识管理系统」 and until spec 026 it had no place
 * to write things down. The whole knowledge layer was one `cards` table whose every
 * row required an `http` source and carried a single instrument — so a macro view,
 * a method, a lesson or a reading note could not be recorded at all. The product
 * could **review** knowledge but not **record** it.
 *
 * ⭐ **Notes and cards are listed together, and that is the point.** They are two
 * different things under one roof: a card is a claim you sign your name to (and it
 * must say where it came from), a note is something you wrote down (and it need
 * not). Separate screens would recreate the split that made the vault impossible.
 *
 * ## ⭐ The layout, and why it is this way (spec 029)
 *
 * Two rounds were spent writing down that this layout was wrong and changing
 * nothing. The owner's verdict — 「我对这个布局不是很满意」 — settled it, so here is
 * the reasoning rather than a diff:
 *
 * **The page used to read: filters → a 200px form → results.** For a page whose
 * main job is 「找到我写过什么」 that order is backwards: the results are below the
 * fold because of a control that is used *occasionally*.
 *
 * So, in order:
 *
 * 1. **filters** — what you are looking at (view · search · tag)
 * 2. **results** — the actual content
 * 3. **the note you opened** — the thing you clicked
 * 4. **记一条** — a single row, collapsed
 *
 * ⭐ **The recording affordance is permanent but not permanent-open.** Earlier
 * drafts proposed collapsing it, and the objection recorded at the time was the
 * right one: the owner's complaint *was* 「记录功能去哪里了」, so hiding it behind
 * a control is walking back the fix. The resolution is that the control is
 * **always one visible row reading 记一条** — never hidden, never a menu — and
 * only the *form* behind it is transient.
 *
 * ⭐ **It opens by itself when the vault is empty.** Not an effect: `open` is
 * *derived* (`composing || nothing written yet`), so there is no state to keep in
 * step. A first-time reader gets the form; a returning one gets one row.
 *
 * ## Search is select-to-search (spec 027/029)
 *
 * The first version needed Enter. A search field where you must remember a key is
 * a search field some people never use, and the 「（改完文字要按回车才搜）」 hint was
 * a workaround for a decision rather than a reason. Now it searches ~150ms after
 * the last keystroke, which is what every other program does, and the hint is gone
 * because there is nothing to warn about.
 *
 * ## What is not here
 *
 * Full-text search is FTS5 (spec 027).
 *
 * ⭐⭐ **This paragraph used to say two things that stopped being true, and one of
 * them was this file's own doing.** ⭐ It said 「the body is still shown as source
 * rather than rendered」 ⭐ — ⭐ and the Markdown renderer landed in the previous
 * commit ⭐, ⭐ so the note body is now rendered ⭐ and the sentence was describing
 * a version of this page that no longer existed. ⭐ ⭐ **A prose claim in a module
 * header is the one kind of documentation no test checks** ⭐, ⭐ and a later
 * commit falsifying it is silent ⭐ — ⭐ so the two sentences that are still true
 * are the two that name a gate or a decision.
 *
 * The editor is still a plain textarea ⭐ — and that is now a **decided-pending**
 * state rather than a shrug: ⭐ `@milkdown/*` is approved, installed, imported by
 * nothing, and shipped at 0 bytes ⭐, ⭐ so `styleguide.test.ts`'s **V-16** reports
 * it unless an exemption says why. ⭐ The exemption carries the measured cost
 * (**+362.82 kB / +110.59 kB gzip**) ⭐ and the fact that the three approved
 * packages cannot read Markdown back out ⭐ without a fourth. ⭐ See
 * `.ai/memory/decisions.md` ADR-0032 ⭐ — ⭐ **it is the owner's call, and this
 * comment is where a reader lands when they ask why.**
 */

import { useCallback, useEffect, useState } from 'react'
import {
  addNoteTag,
  createNote,
  enrollNote,
  listNoteBacklinks,
  listNoteTags,
  listNoteReviews,
  listNotes,
  type Note,
  type NoteDraft,
  readNoteSchedule,
  removeNoteTag,
} from './notes'
import { BacklinkCount, BacklinkList } from './components/knowledge/BacklinkList'
import { Markdown } from './components/knowledge/Markdown'
import { NoteEditor } from './components/knowledge/NoteEditor'
import { NoteLinks } from './components/knowledge/NoteLinks'
import { NoteReviewTimeline } from './components/data/timelineAdapters'
import LessonList from './components/knowledge/LessonList'
import LessonRecallView from './components/knowledge/LessonRecallView'
import RecallView from './components/knowledge/RecallView'
import { displayCode, formatMoment } from './format'
import { ApiError } from './api'
import { Badge, Button, Input, Rule, Textarea } from './components/ui'
import { DataTable, type Column } from './components/data/DataTable'
import { useResource } from './useResource'

/** The three things a note may be, in the order a reader looks for them. */
type View = 'notes' | 'cards' | 'lessons' | 'all' | 'recall'

const VIEWS: { key: View; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'notes', label: '笔记' },
  { key: 'cards', label: '卡片' },
  // ⭐ 教训 (spec 030): a **browsable** list, not a queue. Promotion is not tied to
  // being due — a lesson written last month and never asked about is the one most
  // likely to be ready to sign, because the reader has had time to sit with it. So it
  // cannot live in the recall view, which shows what *came back*.
  //
  // Placed **before** 该复习, and that order is a claim: the recall view is the one
  // you are interrupted by rather than the one you go to read.
  { key: 'lessons', label: '教训' },
  // ⭐ A filter, not a route. The queue is notes; the vault is where notes live.
  // A separate `#/recall` would split one subject across two URLs and two nav
  // entries, and the nav is deliberately count-free and short.
  { key: 'recall', label: '该复习' },
]

/**
 * ⭐ Select-to-search, not press-Enter-to-search.
 *
 * 150ms is long enough to coalesce a burst of keystrokes into one request and short
 * enough that the list does not feel stuck. The value is deliberately not
 * configurable: a setting for "how long until I search" is a setting nobody changes
 * and everybody wonders about.
 */
const SEARCH_DEBOUNCE_MS = 150

export default function VaultPage() {
  const [view, setView] = useState<View>('all')
  const [tag, setTag] = useState<string | null>(null)
  const [searchText, setSearchText] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Note | null>(null)
  const [composing, setComposing] = useState(false)

  const describe = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取知识库。'),
    [],
  )
  const describeTags = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取标签。'),
    [],
  )

  useEffect(() => {
    const handle = setTimeout(() => setQuery(searchText.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [searchText])

  // Both are dependencies, so narrowing re-runs the fetch rather than filtering
  // client-side — the server is the only place that knows the exact-tag rule and
  // the trigram floor, and a client that reimplemented either would be a second
  // implementation to keep in step.
  const notes = useResource<Note[]>(
    useCallback(() => listNotes({ tag, q: query }), [tag, query]),
    [tag, query],
    describe,
  )
  const tags = useResource<string[]>(listNoteTags, [], describeTags)

  /**
   * Select a note the reader did not click in the list.
   *
   * ⭐ **This exists because a backlink is an id and `selected` is a `Note`.** The
   * lookup goes through the list already in hand rather than fetching, and ⭐ the two
   * failures it could have are both handled by doing nothing visible: an id that is
   * not in the current list (it is filtered out by the search box) and an id that is
   * gone entirely. ⭐ Neither is worth an error message — the reader pressed a link to
   * a note they were already looking at, and 「无法打开」 would be a false alarm.
   *
   * ⭐ **And the current search box stays as it is.** Clearing it would be a bigger
   * behaviour change than this stage is for, and the note appears either way; the
   * list below is not re-filtered, so the target can be selected while invisible in
   * the list, ⭐ which is slightly odd and much better than refusing to open it.
   *
   * ⭐ **Declared after `notes` rather than beside the other callbacks**, because the
   * first version sat above it and `useCallback`'s dependency array read `notes.data`
   * before `notes` existed. ⭐ That is a runtime-shaped mistake caught by `tsc` — the
   * kind that reads as a missing-import problem until you look at the line numbers.
   */
  const openNoteById = useCallback(
    (noteId: string) => {
      const found = (notes.data ?? []).find((candidate) => candidate.id === noteId)
      if (found) setSelected(found)
    },
    [notes.data],
  )

  /**
   * ⭐ Derived, **and latched**.
   *
   * The form opens when the reader asked for it **or** when there is nothing to
   * read, so a first-time reader lands on a form rather than an empty table.
   *
   * ⭐ The derivation was **wrong the first time**, and the browser found it in one
   * pass: purely derived, the form closes itself after the *first* note —
   *
   *     empty vault -> the form shows
   *     first note  -> the vault is no longer empty -> formOpen is false
   *
   * — so a reader typing their first note had the form disappear under them
   * mid-sentence, punished for using it. `onRecorded` therefore sets `composing`,
   * which latches it open. Still no effect: the change happens in the event
   * handler that caused it, which is what the `set-state-in-effect` rule asks for.
   */
  const vaultIsEmpty = (notes.data ?? []).length === 0 && !notes.loading
  const formOpen = composing || vaultIsEmpty

  return (
    <div className="pb-8">
      <p className="border-b border-rule px-4 py-2.5 type-prose text-ink-faint">
        卡片是<span className="text-ink-soft">你愿意署名的判断</span>，必须有出处；
        笔记是<span className="text-ink-soft">你写下来的东西</span>，可以没有。
        <span className="text-ink-faint"> 两者都在这里，因为它们是一件事的两面。</span>
      </p>

      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-2">
        {VIEWS.map((entry) => (
          <Button
            key={entry.key}
            size="sm"
            variant={view === entry.key ? 'primary' : 'ghost'}
            onClick={() => setView(entry.key)}
            data-testid={`vault-view-${entry.key}`}
 >
            {entry.label}
          </Button>
        ))}

        <span className="mx-1 h-4 w-px bg-rule" aria-hidden="true" />

        {/*
          ⭐ No form, no submit button. The first version wrapped this in a
          `<form>` and required Enter, with a 「（改完文字要按回车才搜）」 hint
          explaining the rule. The hint was a workaround for a decision, not a
          reason: a search field where you must remember a key is a field some
          people never use. It now searches as you type.
        */}
        <Input
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          placeholder="搜标题与正文"
          aria-label="搜索笔记"
          className="w-[220px]"
          data-testid="vault-search"
        />
        {searchText !== '' ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSearchText('')}
            data-testid="vault-search-clear"
 >
            清除
          </Button>
        ) : null}

        <span className="mx-1 h-4 w-px bg-rule" aria-hidden="true" />

        <Button
          size="sm"
          variant={tag === null ? 'primary' : 'ghost'}
          onClick={() => setTag(null)}
          data-testid="vault-tag-none"
 >
          不限标签
        </Button>
        {(tags.data ?? []).map((name) => (
          <Button
            key={name}
            size="sm"
            variant={tag === name ? 'primary' : 'ghost'}
            onClick={() => setTag(name)}
            data-testid={`vault-tag-${name}`}
 >
            {name}
          </Button>
        ))}
      </div>

      {/*
        ⭐ What the search box does and does not read, in the place a reader who
        just got an empty result will look.

        It reads the **title and the body**. It does **not** read tags — a tag is a
        button one row up, and indexing tags would mean rebuilding the index on
        every tag change as well as every note edit. Saying so beats letting
        someone conclude the note does not exist.
      */}
      {query !== '' ? (
        <p className="px-4 pt-2 type-prose text-ink-faint" data-testid="vault-search-note">
          正在标题与正文里找「{query}」。标签不参与这次搜索 —— 标签用它上面的按钮筛。
        </p>
      ) : null}

      {notes.error ? (
        <p className="px-4 py-2 type-prose text-[color:var(--color-up)]" data-testid="vault-error">
          {notes.error}
        </p>
      ) : null}

      {/*
        ── 1. results ──────────────────────────────────────────────────
        Above the composer, which is the whole point of the reorder: the reader
        came here to read, and the thing that pushed the reading below the fold
        was a form used occasionally.
      */}
      {/*
        ⭐ **One 「该复习」 for both kinds, not two views.** Two queues to visit is
        the fragmentation this product refuses everywhere else, and the reader does
        not experience a note and a lesson as different *kinds of interruption* —
        both are 「something you wrote came back」.

        The difference is in **why**, and it is a label on the row rather than a
        second page: a note is here because the reader asked to be reminded of it, a
        lesson because red line 7 made the enrolment automatic. Rendering them as
        one undifferentiated list would make an un-asked-for interruption look like
        a forgotten errand — the 「你欠 N 条」 feeling reached by a different road.

        Notes first, then lessons, and each group keeps its own `due_at` ordering.
        Merging them into one date-sorted list would claim the two are
        interchangeable, which the label says they are not.
      */}
      {view === 'recall' ? (
        <>
          <RecallView onDone={() => void notes.reload()} />
          <LessonRecallView onDone={() => void notes.reload()} />
        </>
      ) : notes.loading ? (
        <p className="px-4 py-3 type-prose text-ink-faint">读取中…</p>
      ) : (
        <>
          {/*
            ⭐ **The set of views this block belongs to**, not 「not cards».

            The condition used to be `view !== 'cards'`, so when the 教训 view was
            added the notes list came with it — onto a page about lessons, telling
            the reader to 「点下面的『记一条』」 about a button that is not there. ⭐ That
            is the shape the owner complained about to begin with: a control referred
            to and not reachable, and here it points *down* at something absent.

            ⭐ **Enumerating membership rather than exclusion** is the point: a gate
            written as 「not the one other view」 fails every time a view is added, and
            it fails silently — the page renders.
          */}
          {view === 'all' || view === 'notes' ? (
            <NoteList
              notes={notes.data ?? []}
              selected={selected}
              onSelect={setSelected}
              query={query}
            />
          ) : null}
          {/*
            ⭐ Only in the 卡片 view. The screenshot showed this line sitting
            between the notes and 记一条, pushing the recorder down for a sentence
            that is an **answer** — and it only answers a question someone asked by
            choosing 卡片. In 全部 it is a distraction, and 全部 without it is
            cleanly "notes".
          */}
          {view === 'cards' ? <CardList /> : null}
          {/*
            ⭐ The 教训 list is **not** part of 全部. In 全部 the two kinds that read as
            knowledge sit together — notes beside cards — and a lesson is neither: it
            is something that came out of a mistake, and the reader came here to read
            what they wrote down, not to grade themselves. It has its own view, and
            promoting happens there.
          */}
          {view === 'lessons' ? <LessonList /> : null}
        </>
      )}

      {/* ── 2. the note you opened ─────────────────────────────────────── */}
      {selected ? (
        <NoteDetail
          note={selected}
          onChanged={notes.reload}
          onSelectNote={openNoteById}
          // ⭐ The list the picker offers. ⭐ It is the **filtered** list, ⭐ so a
          // reader who has typed into the search box can only link to something they
          // can see ⭐ — ⭐ and a picker offering notes hidden by the filter would
          // produce links the reader cannot trace back to where they made them.
          siblings={notes.data ?? []}
          onShow={setSelected}
        />
      ) : null}

      {/* ── 3. 记一条 ──────────────────────────────────────────────────── */}
      {view === 'recall' || view === 'lessons' ? null : (
        <div className="px-4 py-3">
          <NoteComposer
            open={formOpen}
            onToggle={() => setComposing((value) => !value)}
            onRecorded={() => {
              // Latch the form open. Without this it closes itself the moment the
              // first note makes the vault non-empty — see the note on `formOpen`.
              setComposing(true)
              void notes.reload()
              void tags.reload()
            }}
          />
        </div>
      )}
    </div>
  )
}

/* ── writing ────────────────────────────────────────────────────────────── */

function NoteComposer({
  open,
  onToggle,
  onRecorded,
}: {
  open: boolean
  onToggle: () => void
  onRecorded: () => void
}) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [tagText, setTagText] = useState('')
  const [symbols, setSymbols] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const titleMissing = title.trim() === ''
  const bodyMissing = body.trim() === ''

  async function submit() {
    if (titleMissing || bodyMissing || busy) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const draft: NoteDraft = {
        title: title.trim(),
        // ⭐ Body verbatim, not trimmed. The backend promises byte-for-byte
        // storage and there is a test for it; trimming here would make the UI
        // quietly disagree with the contract, and the disagreement would be
        // invisible until someone compared the two.
        body,
        tags: tagText
          .split(/[,，\s]+/)
          .map((t) => t.trim())
          .filter((t) => t !== ''),
        symbols: symbols
          .split(/[,，\s]+/)
          .map((s) => s.trim())
          .filter((s) => s !== ''),
      }
      const created = await createNote(draft)
      setNotice(`已记下（${created.id}）—— 正文按原样存，不会被改写。`)
      setTitle('')
      setBody('')
      setTagText('')
      setSymbols('')
      onRecorded()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '写入失败。')
    } finally {
      setBusy(false)
    }
  }

  // ⭐ The collapsed state. One row, always visible, never a menu — the recording
  // function is the thing the owner said was missing, so it is not hidden behind a
  // control that has to be discovered.
  if (!open) {
    return (
      <div>
        <Rule />
        <Button size="sm" onClick={onToggle} data-testid="note-compose-open">
          记一条
        </Button>
        <p className="mt-1.5 type-prose text-ink-faint">
          宏观判断、方法、教训、读书笔记 —— 都不用出处。
        </p>
      </div>
    )
  }

  return (
    <section className="max-w-[720px]" data-testid="note-composer">
      <div className="flex items-baseline gap-2 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">记一条</h2>
        {/*
          The close control. Present even when the form opened by itself, because a
          reader who landed on it by accident needs a way out that is not "reload
          the page".
        */}
        <button
          type="button"
          onClick={onToggle}
          className="type-badge text-ink-faint hover:text-ink-soft data-[motion=l1]"
          data-testid="note-compose-close"
 >
          收起
        </button>
      </div>
      <Rule />
      <div className="mt-1.5 flex flex-col gap-1.5">
        <Input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="标题 · 例如「流动性收紧时周期股先跌」"
          aria-label="笔记标题"
          data-testid="note-title"
        />
        <Textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          rows={4}
          placeholder={
            '正文（Markdown）· 例如：\n## 观察\n\n- 2026-08 利率上行\n- 成长股滞后 3 周'
          }
          aria-label="笔记正文"
          data-testid="note-body"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Input
            size="sm"
            value={tagText}
            onChange={(event) => setTagText(event.target.value)}
            placeholder="标签 · 空格分隔"
            className="w-[180px]"
            aria-label="标签"
            data-testid="note-tags"
          />
          <Input
            size="sm"
            value={symbols}
            onChange={(event) => setSymbols(event.target.value)}
            placeholder="标的 · 可留空"
            className="num w-[160px]"
            aria-label="标的"
            data-testid="note-symbols"
          />
          <Button variant="primary" disabled={titleMissing || bodyMissing || busy} onClick={() => void submit()} data-testid="note-submit">
            {busy ? '写入中…' : '记下'}
          </Button>
        </div>
      </div>

      <p className="mt-1 type-prose text-ink-faint">
        {titleMissing || bodyMissing
          ? '标题和正文都要有 —— 「我先记一句免得忘了」是可以的，正文不能全空。'
          : '没有出处也能记。卡片才需要出处，因为它是一条你愿意署名的判断。'}
      </p>

      {error ? (
        <p className="mt-1.5 border-l-2 border-l-[color:var(--color-up)] py-1 type-prose text-[color:var(--color-up)]" data-testid="note-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mt-1.5 border-l-2 border-l-navy py-1 type-prose text-navy" data-testid="note-notice">
          {notice}
        </p>
      ) : null}
    </section>
  )
}

/* ── listing ────────────────────────────────────────────────────────────── */

function NoteList({
  notes,
  selected,
  onSelect,
  query,
}: {
  notes: Note[]
  selected: Note | null
  onSelect: (note: Note) => void
  query: string
}) {
  const columns: Column<Note>[] = [
    { key: 'title', header: '标题', width: '42%', sortValue: (n) => n.title, render: (n) => <span className="text-ink">{n.title}</span> },
    {
      key: 'tags',
      header: '标签',
      render: (n) => (
        <span className="flex flex-wrap gap-1">
          {n.tags.length === 0 ? <span className="text-ink-faint">—</span> : null}
          {n.tags.map((t) => (
            <Badge key={t}>{t}</Badge>
          ))}
        </span>
      ),
    },
    {
      key: 'symbols',
      header: '标的',
      width: '120px',
      render: (n) => (
        <span className="num type-meta text-ink-soft">
          {n.symbols.length === 0 ? '—' : n.symbols.map((s) => displayCode(s.market, s.code)).join(' ')}
        </span>
      ),
    },
    { key: 'updated', header: '改于', numeric: true, sortValue: (n) => n.updated_at, render: (n) => <span className="type-meta text-ink-faint">{formatMoment(n.updated_at)}</span> },
  ]

  if (notes.length === 0) {
    // ⭐ Two different empties, and conflating them is how a search feature gets
    // distrusted. 「这里还没有笔记」 tells the reader to go write something;
    // 「没找到」 tells them the note they half-remember is not here. Only the
    // first is true, and the reader cannot tell which they are looking at unless
    // the message says so.
    return (
      <section className="mt-3">
        <Rule />
        {query !== '' ? (
          <div className="px-4 py-3" data-testid="vault-no-match">
            <p className="type-prose text-ink-soft">
              标题与正文里没有「{query}」。
            </p>
            <p className="mt-1 type-prose text-ink-faint">
              搜索不读标签 —— 换个标签按钮试试，或者把词写得更长一点
              （两个字也能搜，但「流动性」比「流动」更容易命中）。
            </p>
          </div>
        ) : (
          <p className="px-4 py-3 type-prose text-ink-soft" data-testid="vault-empty">
            这里还没有笔记。点下面的「记一条」—— 宏观判断、方法、教训、读书笔记，都不用出处。
          </p>
        )}
      </section>
    )
  }

  return (
    <section className="mt-3">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">笔记</h2>
        <span className="num type-badge text-ink-faint">{notes.length}</span>
      </div>
      <Rule />
      <DataTable<Note>
        dense
        columns={columns}
        rows={notes}
        rowKey={(n) => n.id}
        onRowClick={onSelect}
        selectedKey={selected?.id ?? null}
      />
    </section>
  )
}

function CardList() {
  return (
    <section className="mt-3">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">卡片</h2>
      </div>
      <Rule />
      <p className="px-4 py-3 type-prose text-ink-soft">
        卡片在标的页上写 —— 那里知道它说的是哪只票。有出处的判断才进卡片层。
      </p>
    </section>
  )
}

/* ── reading ────────────────────────────────────────────────────────────── */

function NoteDetail({
  note,
  onChanged,
  onSelectNote,
  siblings,
  onShow,
}: {
  note: Note
  onChanged: () => void
  onSelectNote: (noteId: string) => void
  /**
   * Show a note the server just returned.
   *
   * This exists because `selected` is separate state from the list.
   * Reloading the list refreshes the table and leaves `selected` holding the
   * object it was given when the reader clicked, so after a save the panel
   * kept showing the old text. Re-looking the id up did not help, because the
   * lookup ran against the pre-reload list.
   */
  onShow: (note: Note) => void
  /** ⭐ Every note the reader can see, ⭐ which is the link picker's only source. ⭐
   * Passed in rather than fetched: ⭐ the vault already holds this list, ⭐ and a
   * second request for it would be the same data in two places. */
  siblings: readonly Note[]
}) {
  const [newTag, setNewTag] = useState('')
  const [error, setError] = useState<string | null>(null)
  // `null` = not asked yet, `false` = not on the queue, `true` = on it. Three
  // states because "we have not looked" and "it is not enrolled" call for
  // different copy, and collapsing them means showing a button that then fails.
  const [enrolled, setEnrolled] = useState<boolean | null>(null)
  // ⭐ **Editing is local state, and it resets when the note changes.** ⭐ A reader who
  // opens note A, presses 改这条, and then clicks note B in the list ⭐ should be
  // reading note B ⭐ — ⭐ and an `editing` flag that outlives the note would drop
  // them into an editor seeded with A's text. ⭐ The effect is the one place a
  // `setState`-in-effect is right: ⭐ it is synchronising with **which record is on
  // screen**, ⭐ which is an external fact and not a derivation.
  const [editing, setEditing] = useState(false)
  useEffect(() => {
    setEditing(false)
  }, [note.id])

  /**
   * ⭐ **The note's review history, fetched per note for the same reason the
   * backlinks are.** ⭐ Its dependency is `note.id`, ⭐ so opening another note asks
   * again; ⭐ and the history is only rendered when the note is on the queue, ⭐ which
   * is decided by a *different* request ⭐ — ⭐ so this one is created unconditionally
   * and the render decides whether to show it, ⭐ rather than a conditional hook
   * whose call order would depend on a network answer.
   */
  const reviews = useResource(
    useCallback(() => listNoteReviews(note.id), [note.id]),
    [note.id],
    useCallback(
      (cause: unknown) =>
        cause instanceof ApiError ? cause.message : '无法读取复习流水。',
      [],
    ),
  )

  /**
   * ⭐ **Backlinks, and a resource that is re-created per note.**
   *
   * `useResource` takes a fetcher and a dependency list; ⭐ passing `note.id` as the
   * dependency is what makes it ask again when the reader opens a different note. ⭐
   * The alternative — fetching all of them once — is not available because there is no
   * such endpoint, and adding one to avoid a re-request would put every note's backlink
   * list in the payload of a page that renders one note.
   */
  const backlinks = useResource(
    useCallback(() => listNoteBacklinks(note.id), [note.id]),
    [note.id],
    useCallback(
      (cause: unknown) =>
        cause instanceof ApiError ? cause.message : '无法读取反链。',
      [],
    ),
  )

  const refresh = useCallback(async () => {
    onChanged()
  }, [onChanged])

  useEffect(() => {
    // Asking whether a note is on the queue is a read, and the answer decides
    // which button the reader sees, so it happens when the note changes rather
    // than on every render.
    let live = true
    void readNoteSchedule(note.id)
      .then(() => live && setEnrolled(true))
      .catch(() => live && setEnrolled(false))
    return () => {
      live = false
    }
  }, [note.id])

  async function enrol() {
    setError(null)
    try {
      await enrollNote(note.id)
      setEnrolled(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '加入复习队列失败。')
    }
  }

  async function addTag() {
    if (newTag.trim() === '') return
    setError(null)
    try {
      await addNoteTag(note.id, newTag.trim())
      setNewTag('')
      await refresh()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '加标签失败。')
    }
  }

  async function dropTag(tag: string) {
    setError(null)
    try {
      await removeNoteTag(note.id, tag)
      await refresh()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '删标签失败。')
    }
  }

  return (
    <section className="mt-4 border-t border-rule pt-3" data-testid="note-detail">
      {/* ⭐ **The header is the same in both modes, and the 改这条 control sits in it.**
          ⭐ Putting it beside the title ⭐ — rather than at the bottom of a long note,
          or inside a menu ⭐ — means it is where the eye already is. */}
      <div className="flex flex-wrap items-baseline gap-2 px-4 pb-1.5">
        <h2 className="serif type-claim text-ink">{note.title}</h2>
        <span className="num ml-auto type-badge text-ink-faint">
          写于 {formatMoment(note.created_at)}
          {note.as_of ? ` · 数据截至 ${note.as_of}` : ''}
        </span>
        {/* ⭐ **「改这条」 and why it is a plain button rather than an icon.** ⭐ The
            icon registry has five entries ⭐ and all five are *views* ⭐ — a view is
            something you go to, ⭐ and 「改这条」 is not a place, ⭐ it is an action on
            the thing already on screen. ⭐ Putting it in the registry would make it
            the sixth kind of thing there, ⭐ which is the 「先注册再说」 mistake again. */}
        {editing ? null : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="type-badge text-ink-faint hover:text-ink-soft data-[motion=l1]"
            data-testid="note-edit-open"
          >
            改这条
          </button>
        )}
      </div>
      <Rule />

      {/* ⭐ **Editing replaces reading, rather than sitting below it.**
          ⭐ The alternative ⭐ — the fields appear under the rendered note ⭐ — means
          that while correcting a sentence the reader is looking at the wrong version
          of it, ⭐ and a long note pushes the fields below the fold entirely. ⭐ The
          editor carries its own live preview ⭐ (`NoteEditor`), ⭐ so nothing is lost
          by hiding the reading view: ⭐ what you were checking against is the second
          thing on the same screen. */}
      {editing ? (
        <div className="px-4 pt-2">
          <NoteEditor
            note={note}
            onCancel={() => setEditing(false)}
            onSaved={(saved) => {
              // The note the server sent, not a re-lookup. See `onShow`.
              setEditing(false)
              onShow(saved)
              onChanged()
            }}
          />
        </div>
      ) : (
        <div className="px-4 pt-2">
        {/*
          The body is shown as **source**, not rendered.

          ⭐ That is a real limitation and it is honest about itself rather than
          hidden behind a half-working renderer: no Markdown renderer is
          installed, and shipping an unverified one would risk rewriting exactly
          the bytes the backend promises to preserve. The text you wrote is the
          text you see back, and `test_the_markdown_comes_back_byte_for_byte`
          holds both ends.
        */}
        {/* ⭐ **Rendered, not source.** This was a `<pre>` of the raw body, ⭐ which
            meant a note read as `## 观察` and `- 利率上行` — ⭐ the page said
            「the body is still shown as source rather than rendered」 in its own header,
            ⭐ and a knowledge base whose notes display their own markup is a text file
            with a sidebar. ⭐ `Markdown` builds React nodes, ⭐ so nothing is parsed
            as HTML, and the bytes the backend preserved are still exactly the bytes
            the editor holds. */}
        <div className="mt-1" data-testid="note-preview">
          <Markdown source={note.body} />
        </div>

        {/* ── backlinks (§8.2 · 「知识库像知识库的地方」) ─────────────────────
            ⭐ **Placed after the body and before the tags.** The body is what the
            reader opened this note for; the tags are chrome they came to edit. ⭐ The
            backlinks answer a question neither of those answers — 「我说过它吗」 — and
            they are the one part of this panel that is about **other records**, so
            they sit after everything about *this* note.

            ⭐ **No loading state, and that is deliberate rather than an omission.**
            The first version of this block had three branches — error, loading, list —
            ⭐ and named components (`ErrorNote`, `Skeleton`) **that do not exist in this
            repository**; the house style is a bare `<p>` in the tone colour, as at
            `vault-error` above. ⭐ Two reasons there is no spinner: a backlink list is
            one request against a local database and the list is empty more often than
            not, ⭐ so a placeholder that flashes for 30 ms is worse than nothing; and
            rendering 「没有别的记录指向它」 before the request returns would be a **false
            statement about a note**, which rule 8 is about in spirit if not in its
            wording. ⭐ So the label row appears only once there is an answer. */}
        {!backlinks.loading && !backlinks.error ? (
          <div className="mt-3">
            <div className="flex items-baseline gap-2">
              <span className="type-meta caps text-ink-faint">被引用</span>
              <BacklinkCount count={backlinks.data?.length ?? 0} />
            </div>
            <div className="mt-1">
              <BacklinkList
                backlinks={backlinks.data ?? []}
                onSelect={onSelectNote}
              />
            </div>
          </div>
        ) : null}

        {backlinks.error ? (
          <p className="mt-3 type-prose text-ink-faint">{backlinks.error}</p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="type-meta caps text-ink-faint">标签</span>
          {note.tags.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => void dropTag(t)}
              className="rounded-[2px] border border-rule px-1.5 py-px type-badge text-ink-soft data-[motion=l1] hover:border-[color:var(--color-up)] hover:text-[color:var(--color-up)]"
              title="点击移除"
              data-testid={`note-tag-${t}`}
 >
              {t} ×
            </button>
          ))}
          <Input
            size="sm"
            value={newTag}
            onChange={(event) => setNewTag(event.target.value)}
            placeholder="加标签"
            className="w-[110px]"
            aria-label="新标签"
            data-testid="note-new-tag"
          />
          <Button size="sm" onClick={() => void addTag()} data-testid="note-add-tag">
            加
          </Button>
        </div>

        {/* ⭐ **`NoteLinks` replaces a paragraph of raw identifiers**, ⭐ and the
            paragraph is worth naming because it is what this product had for its
            whole life: ⭐ every outgoing link printed as `note/note_1700000000000` —
            ⭐ a row that names a record, does not open it, and does not say what it
            is. ⭐ 「知识库像知识库的地方」 (§8.2) is a reader being able to follow a
            thought, ⭐ and this was the opposite of that. */}
        <div className="mt-3">
          <NoteLinks
            note={note}
            candidates={siblings}
            onChanged={(updated) => {
              // Same reason as the editor's save: the link list is rendered from the
              // prop, so without this the row stays until the reader reopens the note.
              onShow(updated)
              onChanged()
            }}
            onOpen={onSelectNote}
          />
        </div>

        <div className="mt-3 border-t border-rule-soft pt-2">
          {/*
            ⭐ **Enrolment is explicit, so the control lives here.** The spec's
            reasoning: enrolling every note the reader ever wrote builds a backlog
            nobody drains, and 「你欠 N 条」 is the feeling the red lines reject.

            Two things this control deliberately lacks: a count of notes *not* yet
            enrolled (the vault never computes one, because computing it would
            mean inventing a tally in order to refuse to show it), and an
"enrol all" (which would undo the per-note decision the design is for).
          */}
          {enrolled === null ? (
            <span className="type-meta text-ink-faint">在查它是不是在队列上…</span>
          ) : enrolled ? (
            <p className="type-prose text-ink-soft" data-testid="note-enrolled">
              这条在复习队列上 —— 到时候它会自己回来找你。
            </p>
          ) : (
            <Button size="sm" onClick={() => void enrol()} data-testid="note-enrol">
              到时候提醒我再读一遍
            </Button>
          )}

          {/* ── 复习流水 ────────────────────────────────────────────────────
              ⭐⭐ **This closes a question spec 028 opened two releases ago.**

              spec 028 made 「改写笔记」 a `reset` rather than quietly moving the due
              date, ⭐ and gave the reason as 「**我复习过 5 次，为什么今天又来了**」 —
              ⭐ a question about *this note's history*. ⭐ The mechanism was built
              (`note_reviews` is append-only, `reset` is an outcome, ⭐ and the API has
              returned the whole history since) ⭐ and ⭐ **nothing ever displayed it**:
              ⭐ `listNoteReviews` had zero callers, ⭐ so the answer existed and there
              was no place to read it. ⭐ A note you edited would reappear on schedule
              ⭐ and you would have no way to learn that you were looking at a
              **second** pass over different text.

              ⭐ **Only rendered once the note is on the queue**, ⭐ because a note that
              was never enroled has no history ⭐ and 「它没有回来过」 ⭐ would be a
              true statement about the wrong thing. ⭐ The enrolment line above already
              answers 「它在不在队列上」, ⭐ and this answers 「它什么时候回来的、为什么」.

              ⭐ **Fetched per note, not with the rest**, ⭐ for the same reason the
              backlinks are: ⭐ there is no 「all reviews」 endpoint, ⭐ and adding one
              to avoid a second request would put every note's review history into the
              payload of a page that renders one note. */}
          {enrolled ? (
            <div className="mt-3">
              <div className="flex items-baseline gap-2">
                <span className="type-meta caps text-ink-faint">复习流水</span>
                <span className="num type-meta text-ink-faint">
                  {reviews.data?.length ?? 0} 次
                </span>
              </div>
              {reviews.error ? (
                <p className="mt-1 type-prose text-ink-faint">{reviews.error}</p>
              ) : reviews.loading ? null : (
                <div className="mt-1">
                  <NoteReviewTimeline reviews={reviews.data ?? []} />
                </div>
              )}
            </div>
          ) : null}
        </div>

        {error ? <p className="mt-1 type-prose text-[color:var(--color-up)]">{error}</p> : null}
      </div>
      )}
    </section>
  )
}
