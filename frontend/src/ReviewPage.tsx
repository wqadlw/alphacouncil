import { useCallback, useEffect, useState } from 'react'
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
 * - after rating `again`, **one line**: when it returns. No reassurance, no red
 *   badge, no "you have forgotten this 3 times". The product records the
 *   interaction and does not comment on it (red line 13)
 *
 * **"现在不是时候" is a first-class button, not buried.** SuperMemo S-05: it is a
 * feature, not procrastination. And spec 018 guarantees it does not damage the
 * card's memory — so choosing it honestly is free, which is the only reason a
 * user would choose it over lying "记得" (red line 14: do not build a punishment
 * tool).
 */
export default function ReviewPage() {
  const [queue, setQueue] = useState<Schedule[]>([])
  const [index, setIndex] = useState(0)
  const [claim, setClaim] = useState<Card | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  /**
   * The one piece of feedback this page gives. A date — a fact about time, not a
   * verdict about the person reading it. `null` before the first answer.
   */
  const [returnedAt, setReturnedAt] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoadError(null)
      setQueue(await getDueCards())
      setIndex(0)
      setReturnedAt(null)
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : '无法读取复习队列。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const current = queue[index] ?? null
  const currentId = current?.card_id ?? null

  useEffect(() => {
    if (currentId === null) return
    let cancelled = false
    void getCard(currentId)
      .then((card: Card) => {
        if (!cancelled) setClaim(card)
      })
      .catch(() => {
        if (!cancelled) setClaim(null)
      })
    return () => {
      cancelled = true
    }
  }, [currentId])

  const answer = useCallback(
    async (body: Parameters<typeof recordReview>[1]) => {
      if (!current) return
      setSubmitting(true)
      try {
        const receipt = await recordReview(current.card_id, body)
        // The entire response. No score, no count, no praise — a date.
        setReturnedAt(receipt.next_due_at)
        setClaim(null)
      } catch (error) {
        setLoadError(error instanceof ApiError ? error.message : '无法记录这次复习。')
      } finally {
        setSubmitting(false)
      }
    },
    [current],
  )

  const next = useCallback(() => {
    if (index + 1 >= queue.length) {
      void refresh()
      return
    }
    setIndex(index + 1)
    setReturnedAt(null)
  }, [index, queue.length, refresh])

  if (loading) {
    return (
      <div className="mx-auto max-w-[720px] px-8 py-10">
        {/* Skeleton, not a spinner: financial software does not animate. */}
        <div className="h-6 w-40 bg-rule" />
      </div>
    )
  }

  if (loadError && queue.length === 0) {
    return (
      <div className="mx-auto max-w-[720px] px-8 py-10">
        <p className="text-ink-soft">{loadError}</p>
      </div>
    )
  }

  if (queue.length === 0) {
    return (
      <div className="mx-auto max-w-[720px] px-8 py-10">
        <h1 className="serif text-[26px] leading-tight">今天没有到期的卡片</h1>
        <p className="mt-2 text-ink-soft">
          还没加入复习的卡片不会出现在这里。到期的会自己回来。
        </p>
        <p className="mt-4">
          <a href={TODAY_HREF} className="text-navy">
            ← 回到今天
          </a>
        </p>
      </div>
    )
  }

  if (returnedAt) {
    return (
      <div className="mx-auto max-w-[720px] px-8 py-10" data-testid="review-receipt">
        {/* The whole confirmation. A date and a button. Nothing about the user. */}
        <p className="text-ink-soft">记下了。下次 {returnedAt.slice(0, 10)} 再来。</p>
        <button
          type="button"
          className="mt-4 text-navy"
          onClick={next}
          data-testid="review-next"
        >
          {index + 1 >= queue.length ? '看看还有没有' : '下一张'}
        </button>
      </div>
    )
  }

  const rating = (value: ReviewRating) => () => {
    void answer({ outcome: 'reviewed', rating: value })
  }

  return (
    <div className="mx-auto max-w-[720px] px-8 py-10">
      {/* A count, not a progress bar. Red line 11: there is no "3 / 8". */}
      <h1 className="text-[13px] tracking-wide text-ink-faint">
        今天要过一遍的 {queue.length} 张
      </h1>

      {claim ? (
        <article className="mt-6" data-testid="review-claim">
          <div className="border-l-2 border-navy pl-4">
            <p className="serif text-[20px] leading-relaxed">{claim.content}</p>
          </div>

          {/* Always visible. Not folded, not hover-only (provenance rule). */}
          <div className="mt-4 flex items-baseline gap-3 text-[12px] text-ink-soft">
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
        <p className="mt-6 text-ink-faint">读取这条主张…</p>
      )}

      {/*
        Five buttons, equally prominent, one row. "现在不是时候" is not behind a
        menu: if answering honestly costs the user nothing (spec 018: a
        postponement does not touch the card's memory), hiding it only pushes
        them toward lying "记得" instead.
      */}
      <div className="mt-8 flex flex-wrap gap-2" data-testid="review-actions">
        <button
          type="button"
          disabled={submitting}
          onClick={rating('again')}
          className="border border-rule px-3 py-2 text-[13px]"
          data-testid="rate-again"
        >
          忘了
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={rating('hard')}
          className="border border-rule px-3 py-2 text-[13px]"
          data-testid="rate-hard"
        >
          有点难
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={rating('good')}
          className="border border-rule px-3 py-2 text-[13px]"
          data-testid="rate-good"
        >
          记得
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={rating('easy')}
          className="border border-rule px-3 py-2 text-[13px]"
          data-testid="rate-easy"
        >
          太简单
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => void answer({ outcome: 'deferred' })}
          className="border border-rule px-3 py-2 text-[13px]"
          data-testid="rate-defer"
        >
          现在不是时候
        </button>
      </div>
    </div>
  )
}
