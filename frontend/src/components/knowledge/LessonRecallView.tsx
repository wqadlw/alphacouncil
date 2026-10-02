/**
 * The lesson queue — what came back because you were wrong once (spec 030).
 *
 * ⭐ **One 「该复习」 for both kinds, not two.** The vault's recall view was built for
 * notes and said so; now the queue holds notes *and* lessons, and the choice is
 * between one view with both and two views to visit. Two is the fragmentation this
 * product refuses everywhere else — and the reader does not experience a note and a
 * lesson as different *kinds of interruption*. Both are "something you wrote came
 * back". The difference is in why, and that belongs in a small label on the row
 * rather than in a second place to look.
 *
 * ⭐ **They come back for different reasons, and the copy says which.** A note is on
 * this queue because the reader *asked* to be reminded of it. A lesson is on it
 * because red line 7 made the enrolment automatic — it was already wrong once, so it
 * is the one thing here that has earned an immediate revisit. Hiding that behind a
 * single undifferentiated list would make an un-asked-for interruption look like a
 * forgotten errand, which is precisely the 「你欠 N 条」 feeling the red lines reject.
 *
 * ## What is deliberately absent, all of it pinned by tests
 *
 * * **No count.** The endpoint returns a bare array and this renders no total. A
 *   number of things you owe is the one thing this page must not have.
 * * **No title per row.** The row shows the lesson's own sentence, because the reader
 *   has to read something. A title would make the list scannable, and a scannable
 *   list of things you owe is a to-do list.
 * * **No priority, no ordering the reader chose.** Oldest due first, ties on id.
 *   Ranking the reader's own backlog is what red line 11 is about.
 * * **No 「入队」 button anywhere.** There is nothing to enrol — see `lessons.ts`.
 */

import { useCallback, useState } from 'react'

import { ApiError } from '../../api'
import { listDueLessons, reviewLesson, type LessonRating } from '../../lessons'
import { LESSON_RATINGS } from './ratings'
import { formatAgo } from './formatAgo'
import { Badge, Button, Rule } from '../ui'
import { useResource } from '../../useResource'
import { Markdown } from './Markdown'

/**
 * ⭐ The four buttons, and the first one is not 「忘了」.
 *
 * For a **note** (spec 028) `again` means 「我的想法变了」. For a **lesson** the same
 * grade means something adjacent and different: 「我不同意我学到的东西了」. Same verb,
 * two queues, and the reader meets both — so the wording says which. 「我忘了」 would
 * be wrong for both, and calling the most valuable answer this queue collects a
 * lapse is the failure the whole scheduling mechanism is for.
 */
/** ⭐ **From `./ratings`, which owns it** — see that file for why the two
 *  queues deliberately disagree on the wording of the same four wire values. */
const RATINGS = LESSON_RATINGS

export default function LessonRecallView({ onDone }: { onDone?: () => void }) {
  const describe = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取教训队列。'),
    [],
  )
  const rows = useResource<Awaited<ReturnType<typeof listDueLessons>>>(listDueLessons, [], describe)

  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function rate(lessonId: string, rating: LessonRating) {
    setBusy(lessonId)
    setError(null)
    try {
      await reviewLesson(lessonId, rating)
      onDone?.()
      await rows.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '记录失败。')
    } finally {
      setBusy(null)
    }
  }

  if (rows.error) {
    return (
      <p className="px-4 py-3 type-prose text-[color:var(--color-up)]" data-testid="lesson-queue-error">
        {rows.error}
      </p>
    )
  }

  const items = rows.data ?? []

  if (items.length === 0) {
    return (
      <div data-testid="lesson-queue-empty">
        <Rule />
        <p className="px-4 py-3 type-prose text-ink-soft" data-testid="lesson-queue-empty-text">
          教训这边没有到期的。
        </p>
        <p className="px-4 pb-3 type-prose text-ink-faint">
          记一条教训就会自己进来 —— 不用点「入队」，那是红线 7 要求的。
        </p>
      </div>
    )
  }

  return (
    <section className="mt-3" data-testid="lesson-queue">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">教训</h2>
        {/*
          ⭐ No count next to the heading. A tally of how many are waiting is the
          number this product refuses, and putting it here would be the easiest
          possible place to add one.
        */}
      </div>
      <Rule />
      <ul>
        {items.map((row) => (
          <li
            key={row.lesson_id}
            className="border-b border-rule-soft px-4 py-3 last:border-b-0"
            data-testid="lesson-queue-item"
 >
            <div className="flex items-baseline gap-2">
              <Badge>从一次复盘来的</Badge>
              <span className="num shrink-0 type-meta text-ink-faint">
                {formatAgo(row.due_at)}
              </span>
            </div>
            {/* ⭐ Rendered, ⭐ and a lesson's content is the whole point of reviewing it —
                  ⭐ a `whitespace-pre-wrap` paragraph shows `##` to the reader who is being
                asked to recall what it says. ⭐ And no `max-w` here: ⭐ `Markdown` carries
            {/* its own measure, ⭐ and a second one on the wrapper is one more place the two
                can disagree. */}
            <div className="mt-1.5">
              <Markdown source={row.content} />
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {RATINGS.map((rating) => (
                <Button
                  key={rating.value}
                  size="sm"
                  disabled={busy === row.lesson_id}
                  onClick={() => void rate(row.lesson_id, rating.value)}
                  title={rating.hint}
                  data-testid={`lesson-rate-${rating.value}`}
 >
                  {rating.label}
                </Button>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {error ? (
        <p className="px-4 py-2 type-prose text-[color:var(--color-up)]">{error}</p>
      ) : null}
    </section>
  )
}
