/**
 * The knowledge vault (spec 026) — **cards and notes, side by side**.
 *
 * ## Why this page exists at all
 *
 * The product is 「面向实战的股市知识管理系统」 and until this page it had no
 * place to write things down. The whole knowledge layer was one `cards` table
 * whose every row required an `http` source and carried a single instrument —
 * so a macro view, a method, a lesson or a reading note could not be recorded at
 * all. The product could **review** knowledge but not **record** it.
 *
 * ⭐ **Notes and cards are listed together, and that is the point.** They are
 * two different things under one roof: a card is a claim you sign your name to
 * (and it must say where it came from), a note is something you wrote down (and
 * it need not). Putting them in separate screens would recreate the split that
 * made the vault impossible; putting them in one list, with the difference
 * visible, is what 「知识库」 means.
 *
 * ## The editor is a plain textarea, deliberately — for now
 *
 * `references/research/09` lists 「Markdown 编辑器」 as gap #1, and the owner
 * approved **Milkdown** (MIT, verified) this round. It is installed and
 * licence-checked. **It is not wired into this page yet**, and the reason is
 * worth stating rather than hiding: a WYSIWYG editor that has not been verified
 * is worse than a plain textarea, because it looks finished and stores
 * something unexpected.
 *
 * So this page stores **Markdown source, byte-for-byte**, through the same
 * `Textarea` the rest of the app uses — which is exactly what the backend
 * contract promises (`test_the_markdown_comes_back_byte_for_byte`). Swapping in
 * Milkdown changes how the text is *typed*, not what is *stored*, so it is a
 * contained change to this file.
 *
 * ## What is not here
 *
 * Full-text search (SQLite FTS5, next round), the note recall queue, and
 * backlinks rendered as a panel. The **data** for the last two exists and is
 * queryable; the panels are not built. See `.ai/specs/026-knowledge-vault/spec.md` §6.
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

export default function VaultPage() {
  const [view, setView] = useState<View>('all')
  const [tag, setTag] = useState<string | null>(null)
  // `query` is the *submitted* search; `searchText` is what is in the box. They
  // are separate on purpose: searching on every keystroke would issue a request
  // per character, and a reader typing 「流动性」 would see the list flicker
  // through four intermediate states. Enter (or Clear) is the commit.
  const [searchText, setSearchText] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Note | null>(null)

  const describe = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取知识库。'),
    [],
  )
  const describeTags = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取标签。'),
    [],
  )

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

        <form
          className="flex items-center gap-1.5"
          onSubmit={(event) => {
            event.preventDefault()
            setQuery(searchText.trim())
          }}
        >
          <Input
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="搜标题与正文 · 回车"
            aria-label="搜索笔记"
            className="w-[220px]"
            data-testid="vault-search"
          />
          <Button size="sm" type="submit" data-testid="vault-search-submit">
            搜
          </Button>
          {query !== '' ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setSearchText('')
                setQuery('')
              }}
              data-testid="vault-search-clear"
            >
              清除
            </Button>
          ) : null}
        </form>

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

        It reads the **title and the body**. It does **not** read tags — a tag is
        a button one row up, and indexing tags would mean the index had to be
        rebuilt on every tag change as well as every note edit. Saying so beats
        letting someone conclude the note does not exist.
      */}
      {query !== '' ? (
        <p className="px-4 pt-2 text-[12px] text-ink-faint" data-testid="vault-search-note">
          正在标题与正文里找「{query}」。
          {searchText.trim() !== query ? '（改完文字要按回车才搜）' : ''}
          标签不参与这次搜索 —— 标签用它上面的按钮筛。
        </p>
      ) : null}

      {notes.error ? (
        <p className="px-4 py-2 text-[13px] text-[color:var(--color-up)]" data-testid="vault-error">
          {notes.error}
        </p>
      ) : null}

      <div className="px-4 py-3">
        {/*
          Both resources reload, not just the list.

          ⭐ Reloading only `notes` was a real bug, and the kind that survives
          review: the note appears in the table while the filter bar above it
          still shows the tags from before it existed. The reader writes
          「宏观、利率」, sees the note listed, looks for a 宏观 filter to narrow
          the vault with, and it is not there — with nothing on screen suggesting
          the two are out of step.
        */}
        <NoteComposer
          onRecorded={() => {
            void notes.reload()
            void tags.reload()
          }}
        />
      </div>

      {view === 'recall' ? (
        <RecallView onDone={() => void notes.reload()} />
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
          {view === 'all' || view === 'cards' ? <CardList /> : null}
        </>
      )}

      {selected ? (
        <NoteDetail note={selected} onChanged={notes.reload} />
      ) : null}
    </div>
  )
}

/* ── writing ────────────────────────────────────────────────────────────── */

function NoteComposer({ onRecorded }: { onRecorded: () => void }) {
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

  return (
    <section className="max-w-[720px]">
      <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">记一条</h2>
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
          rows={5}
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
    // first is true, and the reader cannot tell which they are looking at
    // unless the message says so.
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
            这里还没有笔记。上面写一条 —— 宏观判断、方法、教训、读书笔记，都不用出处。
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
          holds both ends. Rendering is the next round, together with Milkdown.
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
            <Button
              size="sm"
              onClick={() => void enrol()}
              data-testid="note-enrol"
            >
              到时候提醒我再读一遍
            </Button>
          )}
        </div>

        {error ? <p className="mt-1 text-[12px] text-[color:var(--color-up)]">{error}</p> : null}
      </div>
    </section>
  )
}
