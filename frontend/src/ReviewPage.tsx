/**
 * The review queue (K3).
 *
 * **What this page is allowed to say, and why that list is so short.**
 *
 * It shows three things: the claim being reviewed, its source (always visible,
 * never behind a hover — the provenance rule paying out in the UI), and when the
 * card comes back. It never says how well the user is doing.
 *
 * That is red line 9 (不展示「成绩」，可以展示「事实」) and red line 13
 * (不讨好用户 — 不在用户做错事时发糖) implemented as an **absence rather than a
 * feature**, which is the hard part and the whole reason this file's docstring is
 * longer than its logic:
 *
 * - no "你记住了 87%" — retrievability is never even fetched (red line 9)
 * - no "连续复习 5 天", no streak, no check-in (red line 11)
 * - no "已复习 3 / 8" progress bar — turning "drain the backlog" into a gameable
 *   number is the same objection one layer down (red line 11)
 * - no count on the nav bar either — see `app/AppShellFrame`; the queue's length
 *   is a fact you learn by opening this page, not a number advertised in advance
 * - after rating `again`, **one line**: when it returns. No reassurance, no red
 *   badge, no "you have forgotten this 3 times". The product records the
 *   interaction and does not comment on it (red line 13)
 *
 * **"现在不是时候" is a first-class button, not buried.** SuperMemo S-05: it is a
 * feature, not procrastination. And spec 018 guarantees it does not damage the
 * card's memory — so choosing it honestly is free, which is the only reason a
 * user would choose it over lying "记得" (red line 14: do not build a punishment
 * tool).
 *
 * ## ⭐ Why the third pane stays empty here, when the shell has one
 *
 * `AppShellFrame` offers a `detail` slot, and this page is the obvious candidate:
 * the due queue on the left, the card on the right. **It was deliberately not
 * done**, because rendering the remaining cards is a progress bar that happens to
 * use pictures instead of digits.
 *
 * A list of what is left is countable at a glance and it visibly shrinks after
 * every answer, which is exactly the "keep the number and try to climb" shape red
 * line 11 objects to. The current design shows **a count, once, and no
 * position** — `今天要过一遍的 1 张`, never `1 / 8`. So the queue stays a sentence.
 *
 * This is the one place where "make it an application" and "respect the red lines"
 * pull in opposite directions, and the red lines win. Recorded here because the
 * next reader will see an empty third pane and assume it is unfinished.
 */

import { useCallback, useState } from 'react'
import {
  ApiError,
  getCard,
  getDueCards,
  recordReview,
  type Card,
  type ReviewRating,
  type Schedule,
} from './api'
import { TODAY_HREF } from './routing'
import { Button, EmptyState, ErrorNote, Skeleton } from './components/ui'
import { useResource } from './useResource'

/**
 * A reading measure for the card's text.
 *
 * The pane is as wide as the window, and a single column of 20px serif stretched
 * to 1200px is unreadable — the eye loses the line on the return sweep. This is
 * the one place a max-width belongs, and it belongs on the *prose*, not on the
 * page: the frame still owns the chrome, and the buttons stay put either way.
 */
const READING_COLUMN = 'max-w-[660px]'

export default function ReviewPage() {
  const describeQueue = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取复习队列。'),
    [],
  )
  const { data: rows, error: loadError, loading, reload } = useResource<Schedule[]>(
    getDueCards,
    [],
    describeQueue,
  )

  const [index, setIndex] = useState(0)
  /**
   * The one piece of feedback this page gives. A date — a fact about time, not a
   * verdict about the person reading it. `null` before the first answer.
   */
  const [returnedAt, setReturnedAt] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [answerError, setAnswerError] = useState<string | null>(null)

  const queue = rows ?? []
  const current = queue[index] ?? null
  const currentId = current?.card_id ?? null

  /**
   * The claim is a second resource rather than part of the queue's.
   *
   * A failure to read one card must not blank the queue — the reader came for the
   * list, and the list is still true. Folding them together made one bad card
   * indistinguishable from a broken page.
   */
  const describeCard = useCallback(() => '无法读取这张卡片。', [])
  const loadClaim = useCallback(
    () => (currentId === null ? Promise.resolve(null) : getCard(currentId)),
    [currentId],
  )
  const { data: claim } = useResource<Card | null>(loadClaim, [currentId], describeCard)

  const refresh = useCallback(() => {
    setIndex(0)
    setReturnedAt(null)
    setAnswerError(null)
    reload()
  }, [reload])

  const answer = useCallback(
    async (body: Parameters<typeof recordReview>[1]) => {
      if (!current) return
      setSubmitting(true)
      setAnswerError(null)
      try {
        const receipt = await recordReview(current.card_id, body)
        // The entire response. No score, no count, no praise — a date.
        setReturnedAt(receipt.next_due_at)
      } catch (cause) {
        setAnswerError(cause instanceof ApiError ? cause.message : '无法记录这次复习。')
      } finally {
        setSubmitting(false)
      }
    },
    [current],
  )

  const next = useCallback(() => {
    if (index + 1 >= queue.length) {
      refresh()
      return
    }
    setIndex(index + 1)
    setReturnedAt(null)
  }, [index, queue.length, refresh])

  if (loading) {
    // Static grey blocks whose heights match what replaces them, so the card does
    // not jump when it lands. No spinner, no shimmer (guide §7.3).
    return (
      <div className={`px-4 py-4 ${READING_COLUMN}`}>
        <Skeleton width="120px" />
        <Skeleton size="title" className="mt-6 w-full" />
        <Skeleton size="title" className="mt-2 w-3/4" />
        <Skeleton className="mt-4 w-40" />
      </div>
    )
  }

  if (loadError && queue.length === 0) {
    return (
      <div className={`px-4 py-4 ${READING_COLUMN}`}>
        <ErrorNote message={loadError} />
      </div>
    )
  }

  if (queue.length === 0) {
    return (
      <EmptyState
        title="今天没有到期的卡片"
        body="还没加入复习的卡片不会出现在这里。到期的会自己回来。"
        action={{ href: TODAY_HREF, label: '回到今天' }}
      />
    )
  }

  if (returnedAt) {
    return (
      <div className={`px-4 py-6 ${READING_COLUMN}`}>
        {/* The whole confirmation. A date and a button. Nothing about the user. */}
        <div data-testid="review-receipt">
          <p className="type-prose text-ink-soft">记下了。下次 {returnedAt.slice(0, 10)} 再来。</p>
          <Button className="mt-4" onClick={next} data-testid="review-next">
            {index + 1 >= queue.length ? '看看还有没有' : '下一张'}
          </Button>
        </div>
      </div>
    )
  }

  const rating = (value: ReviewRating) => () => {
    void answer({ outcome: 'reviewed', rating: value })
  }

  return (
    <div className={`px-4 py-4 ${READING_COLUMN}`}>
      {/* A count, not a progress bar. Red line 11: there is no "1 / 8", and
          deliberately no list of what is left — see the file's header. */}
      <h2 className="type-meta caps text-ink-faint">
        今天要过一遍的 <span className="num">{queue.length}</span> 张
      </h2>

      {claim ? (
        <article className="mt-5" data-testid="review-claim">
          {/* The reader's own words, in serif at 20px (rule 1). This is the one
              place in the product where large serif is unambiguously right: it
              is a quotation, not interface text. */}
          <div className="border-l-2 border-l-navy pl-4">
            {/* ⭐ 象限判语 — the quadrant's own sentence, which §2.2 puts at the top of the
          「卡片/主张/象限判语」 row (17–20 serif). It was already serif and already
          larger than the page, at 20px, so this is the one claim site the migration
          confirms rather than corrects. */}
      <p className="serif type-claim-lg">{claim.content}</p>
          </div>

          {/* Always visible. Not folded, not hover-only (provenance rule). */}
          <div className="mt-4 flex items-baseline gap-3 type-meta text-ink-soft">
            <span>来源 {claim.source_title}</span>
            <a
              href={claim.source_url}
              className="text-navy"
              target="_blank"
              rel="noreferrer"
              data-testid="review-source"
 >
              [打开]
            </a>
          </div>
        </article>
      ) : (
        <p className="mt-5 type-prose text-ink-faint">读取这条主张…</p>
      )}

      {/*
        Five buttons, equally prominent, one row. "现在不是时候" is not behind a
        menu: if answering honestly costs the user nothing (spec 018: a
        postponement does not touch the card's memory), hiding it only pushes
        them toward lying "记得" instead.

        `variant="default"` for all five, deliberately — not one primary and four
        ghosts. The product has no opinion about which answer is correct, so it
        has no opinion about which button is the good one.
      */}
      <div className="mt-7 flex flex-wrap gap-2" data-testid="review-actions">
        <Button disabled={submitting} onClick={rating('again')} data-testid="rate-again">
          忘了
        </Button>
        <Button disabled={submitting} onClick={rating('hard')} data-testid="rate-hard">
          有点难
        </Button>
        <Button disabled={submitting} onClick={rating('good')} data-testid="rate-good">
          记得
        </Button>
        <Button disabled={submitting} onClick={rating('easy')} data-testid="rate-easy">
          太简单
        </Button>
        <Button disabled={submitting} onClick={() => void answer({ outcome: 'deferred' })} data-testid="rate-defer">
          现在不是时候
        </Button>
      </div>

      {answerError ? (
        <p className="mt-4 type-prose text-ink-soft" data-testid="answer-error">
          {answerError}
        </p>
      ) : null}
    </div>
  )
}
