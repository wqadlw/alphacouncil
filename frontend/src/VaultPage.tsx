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
 * Full-text search is FTS5 (spec 027). The editor is still a plain textarea and the
 * body is still shown as source rather than rendered — see `docs/FRONTEND_STYLE_GUIDE.md`
 * and the spec for why an unverified WYSIWYG editor is worse than a plain one.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  addNoteTag,
  createNote,
  enrollNote,
  listNoteTags,
  listNotes,
  type Note,
  type NoteDraft,
  readNoteSchedule,
  removeNoteTag,
} from './notes'
import LessonRecallView from './components/knowledge/LessonRecallView'
import RecallView from './components/knowledge/RecallView'
import { displayCode, formatMoment } from './format'
import { ApiError } from './api'
import { Badge, Button, Input, Rule, Textarea } from './components/ui'
import { DataTable, type Column } from './components/data/DataTable'
import { useResource } from './useResource'

/** The three things a note may be, in the order a reader looks for them. */
type View = 'notes' | 'cards' | 'all' | 'recall'

const VIEWS: { key: View; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'notes', label: '笔记' },
  { key: 'cards', label: '卡片' },
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
      <p className="border-b border-rule px-4 py-2.5 text-[12px] text-ink-faint">
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
        <p className="px-4 pt-2 text-[12px] text-ink-faint" data-testid="vault-search-note">
          正在标题与正文里找「{query}」。标签不参与这次搜索 —— 标签用它上面的按钮筛。
        </p>
      ) : null}

      {notes.error ? (
        <p className="px-4 py-2 text-[13px] text-[color:var(--color-up)]" data-testid="vault-error">
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
        <p className="px-4 py-3 text-[13px] text-ink-faint">读取中…</p>
      ) : (
        <>
          {view !== 'cards' ? (
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
        </>
      )}

      {/* ── 2. the note you opened ─────────────────────────────────────── */}
      {selected ? (
        <NoteDetail note={selected} onChanged={notes.reload} />
      ) : null}

      {/* ── 3. 记一条 ──────────────────────────────────────────────────── */}
      {view === 'recall' ? null : (
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
        <p className="mt-1.5 text-[12px] text-ink-faint">
          宏观判断、方法、教训、读书笔记 —— 都不用出处。
        </p>
      </div>
    )
  }

  return (
    <section className="max-w-[720px]" data-testid="note-composer">
      <div className="flex items-baseline gap-2 pb-1.5">
        <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">记一条</h2>
        {/*
          The close control. Present even when the form opened by itself, because a
          reader who landed on it by accident needs a way out that is not "reload
          the page".
        */}
        <button
          type="button"
          onClick={onToggle}
          className="text-[11px] text-ink-faint hover:text-ink-soft"
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

      <p className="mt-1 text-[12px] text-ink-faint">
        {titleMissing || bodyMissing
          ? '标题和正文都要有 —— 「我先记一句免得忘了」是可以的，正文不能全空。'
          : '没有出处也能记。卡片才需要出处，因为它是一条你愿意署名的判断。'}
      </p>

      {error ? (
        <p className="mark mt-1.5 border-l-2 border-l-[color:var(--color-up)] py-1 text-[13px] text-[color:var(--color-up)]" data-testid="note-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mark mt-1.5 border-l-2 border-l-navy py-1 text-[13px] text-navy" data-testid="note-notice">
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
        <span className="num text-[12px] text-ink-soft">
          {n.symbols.length === 0 ? '—' : n.symbols.map((s) => displayCode(s.market, s.code)).join(' ')}
        </span>
      ),
    },
    { key: 'updated', header: '改于', numeric: true, sortValue: (n) => n.updated_at, render: (n) => <span className="text-[12px] text-ink-faint">{formatMoment(n.updated_at)}</span> },
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
            <p className="text-[13px] text-ink-soft">
              标题与正文里没有「{query}」。
            </p>
            <p className="mt-1 text-[12px] text-ink-faint">
              搜索不读标签 —— 换个标签按钮试试，或者把词写得更长一点
              （两个字也能搜，但「流动性」比「流动」更容易命中）。
            </p>
          </div>
        ) : (
          <p className="px-4 py-3 text-[13px] text-ink-soft" data-testid="vault-empty">
            这里还没有笔记。点下面的「记一条」—— 宏观判断、方法、教训、读书笔记，都不用出处。
          </p>
        )}
      </section>
    )
  }

  return (
    <section className="mt-3">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">笔记</h2>
        <span className="num text-[11px] text-ink-faint">{notes.length}</span>
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
        <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">卡片</h2>
      </div>
      <Rule />
      <p className="px-4 py-3 text-[13px] text-ink-soft">
        卡片在标的页上写 —— 那里知道它说的是哪只票。有出处的判断才进卡片层。
      </p>
    </section>
  )
}

/* ── reading ────────────────────────────────────────────────────────────── */

function NoteDetail({ note, onChanged }: { note: Note; onChanged: () => void }) {
  const [newTag, setNewTag] = useState('')
  const [error, setError] = useState<string | null>(null)
  // `null` = not asked yet, `false` = not on the queue, `true` = on it. Three
  // states because "we have not looked" and "it is not enrolled" call for
  // different copy, and collapsing them means showing a button that then fails.
  const [enrolled, setEnrolled] = useState<boolean | null>(null)

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
      <div className="flex flex-wrap items-baseline gap-2 px-4 pb-1.5">
        <h2 className="serif text-[15px] text-ink">{note.title}</h2>
        <span className="num ml-auto text-[11px] text-ink-faint">
          写于 {formatMoment(note.created_at)}
          {note.as_of ? ` · 数据截至 ${note.as_of}` : ''}
        </span>
      </div>
      <Rule />

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
        <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-ink" data-testid="note-preview">
          {note.body}
        </pre>

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">标签</span>
          {note.tags.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => void dropTag(t)}
              className="rounded-[2px] border border-rule px-1.5 py-px text-[11px] text-ink-soft data-[motion=l1] hover:border-[color:var(--color-up)] hover:text-[color:var(--color-up)]"
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

        {note.links.length > 0 ? (
          <p className="mt-2 text-[12px] text-ink-soft">
            指向：
            {note.links.map((l) => (
              <span key={`${l.to_kind}:${l.to_id}`} className="num ml-1 text-ink-faint">
                {l.to_kind}/{l.to_id}
              </span>
            ))}
          </p>
        ) : null}

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
            <span className="text-[12px] text-ink-faint">在查它是不是在队列上…</span>
          ) : enrolled ? (
            <p className="text-[12px] text-ink-soft" data-testid="note-enrolled">
              这条在复习队列上 —— 到时候它会自己回来找你。
            </p>
          ) : (
            <Button size="sm" onClick={() => void enrol()} data-testid="note-enrol">
              到时候提醒我再读一遍
            </Button>
          )}
        </div>

        {error ? <p className="mt-1 text-[12px] text-[color:var(--color-up)]">{error}</p> : null}
      </div>
    </section>
  )
}
