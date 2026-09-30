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
import type { Backlink } from './components/knowledge/BacklinkList'

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

/**
 * Which notes point **at** this one (spec 045 stage C).
 *
 * ⭐ **`encodeURIComponent`, unlike the other note calls in this file.** ⭐ They
 * interpolate the id bare, and they were written before ids could be anything but a
 * `note_<millis>` this file itself generates — so they are safe today and would not be
 * if the id scheme ever changed. ⭐ This one is written correctly because the writer
 * noticed while copying, and the two spellings in one file are the thing worth
 * remembering: ⭐ a rule applied to the third instance instead of all of them is
 * decoration, and the fifth instance will be written from whichever one is nearer.
 */
export function listNoteBacklinks(id: string): Promise<Backlink[]> {
  return request<Backlink[]>(
    `/api/v1/notes/${encodeURIComponent(id)}/backlinks`,
  )
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
  return request<Note>(`/api/v1/notes/${encodeURIComponent(id)}/links`, {
    method: 'POST',
    body: JSON.stringify(link),
  })
}

/**
 * Stop pointing a note at something (spec 045 · 知识库基本功能).
 *
 * ⭐ **`to_kind` and `to_id` in the path, not in a body** ⭐ — a `DELETE` with a body
 * is a thing some HTTP stacks drop, ⭐ and the backend's route is shaped the same way
 * as its tag route ⭐ for the same reason.
 *
 * ⭐ **Both are encoded**, and `encodeURIComponent` is applied to the id here while
 * `addNoteLink` above does the same ⭐ — ⭐ while the rest of this file interpolates
 * bare. ⭐ The note ids this product generates are safe, ⭐ so the difference is not
 * observable today, ⭐ and the reason to write it correctly in the two functions that
 * were added together ⭐ is that the fifth instance of a rule is written from
 * whichever instance is nearest.
 */
export function removeNoteLink(id: string, link: NoteLink): Promise<Note> {
  return request<Note>(
    `/api/v1/notes/${encodeURIComponent(id)}/links/${encodeURIComponent(
      link.to_kind,
    )}/${encodeURIComponent(link.to_id)}`,
    { method: 'DELETE' },
  )
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

/* ── the recall queue (spec 028) ───────────────────────────────────────────
 *
 * ⭐ **The queue carries no length, and this client never asks for one.** The
 * product's rule is 「一句陈述，无推送、无红点、无催促词」, and a count is the one
 * number a reader could start trying to clear. The endpoint returns a bare array,
 * so there is no field to reach for.
 */

/**
 * How well the note still holds up.
 *
 * ⭐ **`again` does not mean 「我忘了」.** For a *card* it does — the claim could
 * not be recalled. For a *note* it means **「我的想法已经变了」**, and that is the
 * most valuable answer this product can get: it says a note has been overtaken by
 * its own author's thinking, which is exactly the moment it should be rewritten,
 * marked, or let converge.
 *
 * The wire format cannot carry that difference — both are `"again"` — so it has to
 * be said in the UI. Dressing it up as a failure would throw away the best
 * feedback the reader gives.
 */
export type ReviewRating = 'again' | 'hard' | 'good' | 'easy'

export interface NoteSchedule {
  note_id: string
  state: 'learning' | 'review' | 'relearning' | 'deferred'
  due_at: string
  enrolled_at: string
  updated_at: string
}

export interface NoteReview {
  id: string
  note_id: string
  outcome: 'reviewed' | 'deferred' | 'reset'
  rating: ReviewRating | null
  reviewed_at: string
  duration_ms: number | null
  from_due_at: string
  to_due_at: string
  from_state: string
  to_state: string
}

/** The queue. A bare list, oldest due first — no count, by design. */
export function listDueNotes(): Promise<NoteSchedule[]> {
  return request<NoteSchedule[]>('/api/v1/notes/due')
}

export function enrollNote(id: string): Promise<NoteSchedule> {
  return request<NoteSchedule>(`/api/v1/notes/${id}/schedule`, { method: 'POST' })
}

export function readNoteSchedule(id: string): Promise<NoteSchedule> {
  return request<NoteSchedule>(`/api/v1/notes/${id}/schedule`)
}

/**
 * The whole history, including the resets.
 *
 * ⭐ This is what answers 「我复习过好几次，为什么今天又来?」 — a rewrite restarts
 * the schedule, and without a row for it the question has no answer.
 */
export function listNoteReviews(id: string): Promise<NoteReview[]> {
  return request<NoteReview[]>(`/api/v1/notes/${id}/reviews`)
}

export function reviewNote(
  id: string,
  rating: ReviewRating,
  durationMs?: number,
): Promise<NoteReview> {
  return request<NoteReview>(`/api/v1/notes/${id}/review`, {
    method: 'POST',
    body: JSON.stringify({ rating, duration_ms: durationMs ?? null }),
  })
}

/** Postpone: 「我的想法还没定」. Touches no memory strength. */
export function deferNote(id: string, days = 7): Promise<NoteReview> {
  return request<NoteReview>(`/api/v1/notes/${id}/defer`, {
    method: 'POST',
    body: JSON.stringify({ days }),
  })
}
