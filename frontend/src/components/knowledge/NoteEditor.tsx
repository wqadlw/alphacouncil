/**
 * 改这条 —— the only way a note changes after it is written.
 *
 * ⭐ **Why this exists at all.** Measured on 2026-09-30: the backend has had
 * `PATCH /notes/{id}` since spec 026, `notes.ts` has had `updateNote` since the same
 * day, and **no page has ever called it.** ⭐ So the product could record a thought
 * and never correct one — ⭐ and for a knowledge base, where a wrong note is worse
 * than no note, ⭐ 「记错了改不了」 is not a missing convenience, ⭐ it is the feature
 * that makes recording worth trusting. ⭐ This is the third time a fully
 * implemented, fully tested backend capability has had no interface ⭐ (the first two
 * were `backlinks_for` and `add_link`), ⭐ and the pattern is worth naming: ⭐ **an
 * endpoint with a test and no caller looks exactly like a feature that is done.**
 *
 * ⭐ **Only the title and the body, and that is the backend's shape, not a choice.**
 * `PATCH /notes/{id}` accepts `{title?, body?}` ⭐ and tags have their own endpoints
 * ⭐ which the detail panel already uses ⭐ (`addNoteTag` / `removeNoteTag`, ⭐ both
 * with interface affordances). ⭐ Putting tags in this form too would mean two ways
 * to change a tag, ⭐ and the one that works when you did not mean to change anything
 * is the one that is not there.
 *
 * ⭐ **It is a form, not a dialog.** ⭐ A modal that hides the note you are
 * correcting is a modal you cannot check your correction against, ⭐ and the note is
 * right there on the same screen. ⭐ That is also why the editor replaces the reading
 * view in place ⭐ — the same decision the vault's 「记一条」 made in spec 029.
 */

import { useState } from 'react'

import { ApiError } from '../../api'
import { updateNote, type Note } from '../../notes'
import { Button, Input, Rule, Textarea } from '../ui'
import { Markdown } from './Markdown'

export function NoteEditor({
  note,
  onSaved,
  onCancel,
}: {
  note: Note
  onSaved: (note: Note) => void
  onCancel: () => void
}) {
  // ⭐ **Seeded from the note, once.** `useState(note.body)` ⭐ and not an effect
  // that re-seeds ⭐ — an effect that writes state on every render of a changed
  // `note` would discard what the reader has typed ⭐ the moment the list reloads
  // underneath them, ⭐ which is exactly what happens after a save.
  const [title, setTitle] = useState(note.title)
  const [body, setBody] = useState(note.body)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const titleMissing = title.trim() === ''
  const bodyMissing = body.trim() === ''
  const unchanged = title === note.title && body === note.body

  async function save() {
    if (titleMissing || bodyMissing || busy) return
    setBusy(true)
    setError(null)
    try {
      // ⭐ **Only the fields that changed.** ⭐ Sending `title` unchanged is a write
      // the reader did not ask for, ⭐ and on a table with an `updated_at` column ⭐
      // it makes the note look edited when it was not. ⭐ It also means a reader who
      // fixed one typo does not silently restate the rest of their note.
      const patch: { title?: string; body?: string } = {}
      if (title !== note.title) patch.title = title.trim()
      if (body !== note.body) patch.body = body
      const saved = await updateNote(note.id, patch)
      onSaved(saved)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '保存失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section data-testid="note-editor">
      <div className="flex items-baseline gap-2 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">改这条</h2>
        <button
          type="button"
          onClick={onCancel}
          className="type-badge text-ink-faint hover:text-ink-soft data-[motion=l1]"
          data-testid="note-edit-cancel"
        >
          取消
        </button>
      </div>
      <Rule />
      <div className="mt-1.5 flex flex-col gap-1.5">
        <Input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          aria-label="笔记标题"
          data-testid="note-edit-title"
        />
        <Textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          // ⭐ **Taller than the composer's four rows, and deliberately.** ⭐ Editing a
          // Markdown note means seeing the structure while you fix it, ⭐ and four
          // rows is a single sentence ⭐ — ⭐ which is the right size for recording a
          // thought and the wrong size for correcting one.
          rows={12}
          className="font-sans"
          aria-label="笔记正文"
          data-testid="note-edit-body"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={titleMissing || bodyMissing || busy || unchanged}
            onClick={() => void save()}
            data-testid="note-edit-save"
          >
            {busy ? '保存中…' : '保存'}
          </Button>
          {/* ⭐ **The button is disabled while nothing has changed, and this line says
              so.** ⭐ A disabled 「保存」 with no explanation is the shape a reader
              reads as 「something is broken」, ⭐ and the sentence costs one row. ⭐ The
              alternative — leaving it enabled and making it a no-op ⭐ — is worse,
              because it invites a click that does nothing. */}
          <span className="type-meta text-ink-faint">
            {unchanged ? '改点什么再保存。' : '标签在上面单独加减 —— 改标题和正文不会动它。'}
          </span>
        </div>
      </div>

      {error ? (
        <p
          className="mark mt-1.5 border-l-2 border-l-[color:var(--color-up)] py-1 type-prose text-[color:var(--color-up)]"
          data-testid="note-edit-error"
        >
          {error}
        </p>
      ) : null}

      {/* ⭐ **A live preview, and it is below the fields rather than beside them.**
          ⭐ Side by side would be a two-pane editor, ⭐ which is a layout decision
          this panel has no width for ⭐ and one the guide's density rule does not ask
          for. ⭐ Below is enough: ⭐ the reader writes, ⭐ scrolls, ⭐ and sees what
          the note will look like. ⭐ And it is the same `Markdown` the reading view
          uses, ⭐ so 「预览和实际不一样」 is not a state this product can be in. */}
      <div className="mt-3">
        <span className="type-meta caps text-ink-faint">改完是这样</span>
        <div className="mt-1">
          <Markdown source={body} />
        </div>
      </div>
    </section>
  )
}
