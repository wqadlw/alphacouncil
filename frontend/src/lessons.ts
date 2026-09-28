/**
 * The lessons client — the 「经验」 half of the knowledge layer (spec 030).
 *
 * Separate from `notes.ts` for the same reason `notes.ts` is separate from
 * `api.ts`: a fourth aggregate in one module is one too many, and what matters is
 * that `request` is imported rather than reimplemented, so there is one `ApiError`
 * shape and one normalisation of FastAPI's `422` envelope.
 *
 * ⭐ **There is no `enrolLesson`.** The server has no such endpoint either, and its
 * absence is red line 7: a lesson's scheduling item is not optional, so a client
 * cannot be handed a way to create one without it. Every other queue in this product
 * has an explicit enrolment call. If a function like that appears here, the
 * guarantee has a hole and this file's comment is the receipt.
 *
 * ⭐ **`LessonScheduleRow` has no `title`.** The server omits it too, and the reason
 * is the product's: a queue whose rows can be scanned is a to-do list, and
 * 「你欠 N 条」 is what the red lines rule out. What the row carries is `content` —
 * the lesson's own sentence, because the reader has to read something.
 */

import { request } from './api'

export interface Lesson {
  lesson_id: string
  review_id: string
  content: string
  created_at: string
}

export interface LessonScheduleRow {
  lesson_id: string
  state: 'learning' | 'review' | 'relearning' | 'deferred'
  due_at: string
  /** The lesson itself, not a label for it. */
  content: string
}

/** What recording returns: the lesson **and** the item the red line forced. */
export interface LessonRecorded {
  lesson: Lesson
  state: LessonScheduleRow['state']
  due_at: string
}

export interface LessonPromotion {
  lesson_id: string
  card_id: string
  promoted_at: string
}

export type LessonRating = 'again' | 'hard' | 'good' | 'easy'

/**
 * Turn a decision's review into a lesson.
 *
 * ⭐ One call, and it is the whole of red line 7 from this side: the server writes
 * the lesson and its scheduling item in one transaction, so there is nothing to
 * pair up and nothing to retry. A client that "records first and schedules after"
 * would be a client that can leave an unscheduled lesson behind — which is why no
 * such two-step shape exists to be written here.
 */
export function recordLesson(
  decisionId: string,
  content: string,
): Promise<LessonRecorded> {
  return request<LessonRecorded>(
    `api/v1/reviews/${encodeURIComponent(decisionId)}/lesson`,
    { method: 'POST', body: JSON.stringify({ content }) },
  )
}

/** Every lesson, newest first. The server returns a bare array — no count. */
export function listLessons(): Promise<Lesson[]> {
  return request<Lesson[]>('api/v1/lessons')
}

/** The lessons that came back on their own. A bare array — no count, no total. */
export function listDueLessons(): Promise<LessonScheduleRow[]> {
  return request<LessonScheduleRow[]>('api/v1/lessons/due')
}

/**
 * Sign a lesson as a card.
 *
 * ⭐ **A source is required, and the signature says so.** There is no overload
 * without one, because 「拿不出出处」 means this is a lesson and not yet a card —
 * and declining costs the reader nothing, because it is already saved and already
 * queued. A convenience overload would invite exactly the call the design refuses.
 */
export function promoteLesson(
  lessonId: string,
  source: { url: string; title: string; claimType?: 'supporting' | 'challenging' | 'neutral' },
): Promise<LessonPromotion> {
  return request<LessonPromotion>(
    `api/v1/lessons/${encodeURIComponent(lessonId)}/promote`,
    {
      method: 'POST',
      body: JSON.stringify({
        source_url: source.url,
        source_title: source.title,
        claim_type: source.claimType ?? 'neutral',
      }),
    },
  )
}

/**
 * Record how a revisit went.
 *
 * ⭐ For a lesson, `again` means 「我不同意我学到的东西了」 rather than 「我忘了」.
 * A lesson is something the reader *concluded*, so the interesting failure is not
 * forgetting it but no longer believing it — and the label is the same decision
 * spec 028 made for a note's `again`, so the two queues do not contradict
 * themselves in front of the same reader.
 */
export function reviewLesson(
  lessonId: string,
  rating: LessonRating,
  durationMs?: number,
): Promise<unknown> {
  return request<unknown>(
    `api/v1/lessons/${encodeURIComponent(lessonId)}/review`,
    {
      method: 'POST',
      body: JSON.stringify({
        rating,
        duration_ms: durationMs ?? null,
      }),
    },
  )
}
