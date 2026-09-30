/**
 * 引用 —— the outgoing links, and the controls that create and drop them.
 *
 * ⭐ **What this product had, measured on 2026-09-30, and why the wording matters.**
 * `note_links` had a repository function, a `POST` endpoint and a test; ⭐ the detail
 * panel printed every outgoing link as `note/note_1700000000000` ⭐ — a row of
 * identifiers that names a record, does not open it, and does not say what it is. ⭐
 * So the honest statement is not 「there was no interface」 ⭐ (there was a bad one) ⭐
 * and not 「nothing pointed anywhere」 ⭐ (points could be created, ⭐ just not from a
 * screen). ⭐ **A raw id is not a link**: a link you cannot follow is a claim you
 * cannot check.
 *
 * ⭐ **And there was no way to take one back at all** ⭐ — no `DELETE` route, ⭐ so a
 * note could be pointed at something for the rest of the product's life. ⭐ For a
 * knowledge base, 「我不再认为 A 和 B 有关」 ⭐ is a statement the reader has to be able
 * to make, ⭐ and it had no way to be said.
 *
 * ⭐ **Outgoing and incoming are two different components and stay that way.** ⭐ This
 * file renders 「它指向」 ⭐ and `BacklinkList` renders 「被引用」 ⭐ — ⭐ because they
 * are not one thing: one is something the reader wrote and can retract, ⭐ the other
 * is a fact about other records, ⭐ which is why the `×` lives here and not there.
 * ⭐ Merging them into one panel looked tidier on paper ⭐ and would have needed a
 * rule for whether a row is retractable, ⭐ which is the 「一个组件里长出 switch」
 * shape this repository has now paid for three times.
 *
 * ⭐ **The target is picked from the list already on screen, not typed.** The vault
 * holds every note the reader can see, ⭐ so a search box over that list is both
 * shorter and more accurate than a free-text field ⭐ — ⭐ and a free-text field
 * would create links to ids that do not exist ⭐ the first time the reader got a
 * title slightly wrong. ⭐ The backend refuses an unknown target ⭐ (spec 026's
 * `link_targets_exist`) ⭐ but a refusal is a worse experience than not offering the
 * mistake.
 */

import { useState } from 'react'

import { ApiError } from '../../api'
import { addNoteLink, removeNoteLink, type Note, type NoteLink } from '../../notes'
import { Button, Input, Rule } from '../ui'

/** ⭐ The five kinds `note_links.to_kind` accepts, in the reader's words. */
const KIND_LABEL: Record<NoteLink['to_kind'], string> = {
  note: '笔记',
  card: '卡片',
  decision: '决策',
  instrument: '标的',
  lesson: '教训',
}

export function NoteLinks({
  note,
  /** ⭐ Every note the reader can currently see. ⭐ The picker's whole source. */
  candidates,
  onChanged,
  onOpen,
}: {
  note: Note
  candidates: readonly Note[]
  onChanged: (note: Note) => void
  onOpen: (noteId: string) => void
}) {
  const [picking, setPicking] = useState(false)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ⭐ **Never offer a note that is already linked, and never this note.** The
  // backend would accept both ⭐ — `INSERT OR IGNORE` makes a duplicate a no-op and
  // `add_link` refuses only a self-link ⭐ — ⭐ so the guarantee belongs here or
  // nowhere, ⭐ and a picker full of rows that do nothing is the worst kind of
  // picker.
  const linkedIds = new Set(note.links.filter((l) => l.to_kind === 'note').map((l) => l.to_id))
  const byId = new Map(candidates.map((candidate) => [candidate.id, candidate]))
  const needle = query.trim().toLowerCase()
  const options = candidates
    .filter((candidate) => candidate.id !== note.id && !linkedIds.has(candidate.id))
    .filter(
      (candidate) =>
        needle === '' || candidate.title.toLowerCase().includes(needle),
    )
    .slice(0, 8)

  async function link(targetId: string) {
    setBusy(true)
    setError(null)
    try {
      onChanged(await addNoteLink(note.id, { to_kind: 'note', to_id: targetId }))
      setPicking(false)
      setQuery('')
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '引用失败。')
    } finally {
      setBusy(false)
    }
  }

  async function unlink(link: NoteLink) {
    setBusy(true)
    setError(null)
    try {
      onChanged(
        await removeNoteLink(note.id, { to_kind: link.to_kind, to_id: link.to_id }),
      )
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '取消引用失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div data-testid="note-links">
      <div className="flex items-baseline gap-2">
        <span className="type-meta caps text-ink-faint">它指向</span>
        <span className="num type-meta text-ink-faint">{note.links.length} 条</span>
      </div>

      {note.links.length === 0 ? (
        // ⭐ **One fact, no illustration, no 「还没有…」 phrasing** ⭐ — rule 8, and
        // the same shape `BacklinkList` uses. ⭐ The sentence names what the section
        // is for ⭐ rather than apologising for being empty, ⭐ because a section that
        // says 「暂无」 is asking the reader to imagine a state the product has not
        // decided on.
        <p className="mt-1 type-prose text-ink-soft">
          它还没有指向别的记录。指向了，它才和别的东西有关系。
        </p>
      ) : (
        <ul className="mt-1">
          {note.links.map((link) => {
            const target = link.to_kind === 'note' ? byId.get(link.to_id) : undefined
            return (
              <li
                key={`${link.to_kind}:${link.to_id}`}
                className="flex items-baseline gap-2 border-b border-l-2 border-l-2 border-[color:var(--color-rule-soft)] border-l-navy py-1.5"
              >
                <span className="type-meta caps shrink-0 text-ink-faint">
                  {KIND_LABEL[link.to_kind]}
                </span>
                {/* ⭐ **A note link is a button, not an `<a>`, and for the same reason
                    `BacklinkList` is one:** the vault selects with component state
                    and the note id is not in the hash, ⭐ so there is no URL. ⭐ For a
                    link to a card, a decision or an instrument there is no title to
                    resolve in this page either, ⭐ so the id is printed — ⭐ honestly,
                    ⭐ and it is the reader's own record so they can recognise it. */}
                {target ? (
                  <button
                    type="button"
                    onClick={() => onOpen(target.id)}
                    className="type-prose block min-w-0 flex-1 truncate text-left text-navy no-underline hover:underline data-[motion=l1]"
                    data-testid="note-link-open"
                  >
                    {target.title}
                  </button>
                ) : (
                  <span
                    className="type-prose min-w-0 flex-1 truncate text-ink"
                    data-testid="note-link-id"
                  >
                    <span className="num">{link.to_id}</span>
                  </span>
                )}
                {/* ⭐ **The unlink control, and it is on every row.** ⭐ A link you
                    cannot take back is a claim you are stuck with, ⭐ and that was the
                    state of this product for its whole life ⭐ — the endpoint did not
                    exist. ⭐ A `×` beside the row ⭐ rather than a row-level menu,
                    ⭐ because a menu is a second thing to discover. */}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void unlink(link)}
                  className="type-badge shrink-0 text-ink-faint hover:text-[color:var(--color-up)] data-[motion=l1]"
                  title="取消引用"
                  data-testid="note-link-remove"
                >
                  ×
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {picking ? (
        <div className="mt-2" data-testid="note-link-picker">
          <Input
            size="sm"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="找一条笔记"
            className="w-[240px]"
            aria-label="找一条笔记来引用"
            data-testid="note-link-search"
          />
          {options.length === 0 ? (
            // ⭐ Rule 8 again: a fact, and what to do. ⭐ And the honest case here is
            // 「没有别的笔记可引用」 ⭐ — ⭐ which is a different statement from
            // 「没有匹配项」 ⭐ and the reader needs to be able to tell them apart,
            // ⭐ because the first means 「记一条再回来」 and the second means
            // 「换个词」。
            <p className="mt-1 type-prose text-ink-soft">
              {candidates.length <= 1
                ? '只有这一条。先记一条别的，再来引用。'
                : '没有匹配项。换个词，或者先记一条。'}
            </p>
          ) : (
            <ul className="mt-1">
              {options.map((candidate) => (
                <li key={candidate.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void link(candidate.id)}
                    className="type-prose block w-full truncate border-b border-l-2 border-l-2 border-l-rule-soft border-[color:var(--color-rule-soft)] py-1 pl-3 text-left text-ink no-underline hover:bg-paper-soft data-[motion=l1]"
                    data-testid="note-link-option"
                  >
                    {candidate.title}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            onClick={() => {
              setPicking(false)
              setQuery('')
            }}
            className="mt-1 type-badge text-ink-faint hover:text-ink-soft"
            data-testid="note-link-picker-close"
          >
            不引用了
          </button>
        </div>
      ) : (
        <div className="mt-1.5">
          <Rule />
          <div className="mt-1.5 flex items-baseline gap-2">
            <Button
              size="sm"
              onClick={() => setPicking(true)}
              data-testid="note-link-open-picker"
            >
              引用另一条
            </Button>
            {/* ⭐ And the sentence that says what it is for, ⭐ because a control
                labelled 「引用」 ⭐ in a knowledge base could mean anything ⭐ and this
                one means 「make this note point at another note」. ⭐ The same reason
                `LessonComposer` carries a sentence about the queue. */}
            <span className="type-meta text-ink-faint">
              指过去之后，那条笔记的「被引用」里就有它。
            </span>
          </div>
        </div>
      )}

      {error ? (
        <p
          className="mt-1.5 border-l-2 border-l-[color:var(--color-up)] py-1 type-prose text-[color:var(--color-up)]"
          data-testid="note-link-error"
        >
          {error}
        </p>
      ) : null}
    </div>
  )
}
