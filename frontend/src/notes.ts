/**
 * The notes client — the other half of the knowledge layer (spec 026).
 *
 * Separate from `api.ts` on purpose rather than appended to it: `api.ts` is
 * already 678 lines and covers instruments, quotes, cards, reviews and
 * decisions, and a sixth concern does not belong in the same file. What matters
 * is that `request` is imported, not reimplemented — one `ApiError` shape, one
 * normalisation of FastAPI's `422` envelope.
 *
 * The types here are the contract `notesContract.test.ts` pins, and the shape
 * that matters most is the one with **everything optional absent**:
 * `source_url` and `source_title` do not exist on `Note`, because a note has no
 * source. If they ever appear as required, the vault has quietly become a
 * second card list.
 */

import { request } from './api'

export type NoteLinkKind = 'note' | 'card' | 'decision' | 'instrument' | 'lesson'

export interface NoteLink {
  to_kind: NoteLinkKind
  to_id: string
}

export interface NoteSymbol {
  market: string
  code: string
}

export interface Note {
  id: string
  title: string
  /** Markdown source, stored and returned byte-for-byte. */
  body: string
  /** Data cutoff, not "when I wrote it". `null` when there is none. */
  as_of: string | null
  created_at: string
  updated_at: string
  tags: string[]
  links: NoteLink[]
  symbols: NoteSymbol[]
}

export interface NoteDraft {
  title: string
  body: string
  as_of?: string | null
  tags?: string[]
  links?: NoteLink[]
  /** Tickers in the usual three spellings; ambiguity is refused server-side. */
  symbols?: string[]
}

/**
 * The list, narrowed.
 *
 * ⭐ **`q` and `tag` compose server-side** and both are optional. An empty or
 * whitespace-only `q` is *not* a search — the API returns the whole vault, so
 * clearing the box is the same as never having typed anything. That is why this
 * omits the parameter rather than sending `q=`: an empty string and an absent
 * parameter are the same request, and only one of them is obvious at a call site.
 *
 * ⭐ **Two characters work.** The backend's `trigram` index has a three-character
 * floor and routes shorter queries to a substring path, so 「利率」 finds the note.
 * A client that had its own minimum would reintroduce the bug the server fixed.
 */
export function listNotes(options: { tag?: string | null; q?: string } = {}): Promise<Note[]> {
  const params = new URLSearchParams()
  if (options.tag) params.set('tag', options.tag)
  const q = options.q?.trim()
  if (q) params.set('q', q)
  const suffix = params.toString()
  return request<Note[]>(`/api/v1/notes${suffix ? `?${suffix}` : ''}`)
}

export function getNote(id: string): Promise<Note> {
  return request<Note>(`/api/v1/notes/${id}`)
}

export function listNoteTags(): Promise<string[]> {
  return request<string[]>('/api/v1/notes/tags')
}

export function createNote(draft: NoteDraft): Promise<Note> {
  return request<Note>('/api/v1/notes', {
    method: 'POST',
    body: JSON.stringify(draft),
  })
}

export function updateNote(
  id: string,
  patch: { title?: string; body?: string },
): Promise<Note> {
  return request<Note>(`/api/v1/notes/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function addNoteTag(id: string, tag: string): Promise<Note> {
  return request<Note>(`/api/v1/notes/${id}/tags`, {
    method: 'POST',
    body: JSON.stringify({ tag }),
  })
}

export function removeNoteTag(id: string, tag: string): Promise<Note> {
  return request<Note>(`/api/v1/notes/${id}/tags/${encodeURIComponent(tag)}`, {
    method: 'DELETE',
  })
}

export function addNoteLink(id: string, link: NoteLink): Promise<Note> {
  return request<Note>(`/api/v1/notes/${id}/links`, {
    method: 'POST',
    body: JSON.stringify(link),
  })
}

/** The full card, so the vault can show a claim and a note under one roof. */
export interface VaultCard {
  id: string
  content: string
  claim_type: 'supporting' | 'challenging' | 'neutral'
  source_url: string
  source_title: string
  status: 'active' | 'converged'
  priority: number
  created_at: string
}
