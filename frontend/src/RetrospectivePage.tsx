import { useCallback, useState } from 'react'
import {
  ApiError,
  getDecisionReview,
  getDueDecisionReviews,
  recordDecisionReview,
  type Decision,
  type DecisionOutcome,
  type DecisionReview,
  type ReviewState,
} from './api'
import { instrumentHref, TODAY_HREF } from './routing'
import { EmptyState, ErrorNote, Page, PageSkeleton } from './ui'
import { useResource } from './useResource'

/**
 * The retrospective queue (J3) — where red line 10 actually happens.
 *
 * **This page shows the decision as it was written, next to what you think of it
 * now.** That pairing is the mechanism, not a layout choice: `项目总纲` P0-3 asks
 * for 到期决策 + 你当初写的话 + 现在的事实, and the words being graded are still on
 * the page because `decisions` is append-only. So what gets reviewed is **not a
 * memory, it is a passage of text** — which is the only thing in this product
 * that resists hindsight, and no amount of UI would have substituted for it.
 *
 * **Three things this page deliberately does not do.**
 *
 * 1. **No result choice before the review is due.** Not disabled — *not rendered*.
 *    A greyed-out control is still on screen, still reachable by keyboard, and
 *    still an invitation; clicking it means scoring the outcome early, and
 *    scoring early *is* hindsight, because the answer is already known and it
 *    colours the judgement of the process. The database refuses it too
 *    (`reviews_not_scored_early_check`, spec 020), so this is the second line
 *    rather than the only one.
 *
 * 2. **No profit figure, anywhere, ever.** Red line 10. There is nothing to
 *    render: `outcome` is a category (`good` / `bad` / `failed`) and no magnitude
 *    was ever stored. In the dangerous quadrant — a bad decision that happened to
 *    pay — the page shows the warning sentence and that is all. A number here
 *    would be the defect, not the feature, and the E2E spec asserts the rendered
 *    text contains no digits in that case.
 *
 * 3. **No praise, no progress bar.** `你复盘了 3 / 8` turns draining the backlog
 *    into a number the user can feel (red lines 11 and 13). The count of what is
 *    waiting is a plain sentence, and it is **not** on the nav bar either.
 *
 * **The quadrant sentence is rendered, not written here.** It arrives from the
 * domain through the API, so the wording is reviewed in the same diff as the rule
 * that requires it. A warning composed in this file is one refactor away from
 * "干得漂亮".
 */
export default function RetrospectivePage() {
  const describeQueue = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取复盘队列。'),
    [],
  )
  const { data: rows, error: loadError, loading, reload } = useResource<ReviewState[]>(
    getDueDecisionReviews,
    [],
    describeQueue,
  )

  const [index, setIndex] = useState(0)
  /** The score picked but not yet submitted — the outcome choice completes it. */
  const [picked, setPicked] = useState<number | null>(null)
  /** The one thing shown after a submission: the verdict, in the domain's words. */
  const [verdict, setVerdict] = useState<DecisionReview | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const queue = rows ?? []
  const current = queue[index] ?? null
  const currentId = current?.decision_id ?? null

  /**
   * The decision's own words, fetched per queue position.
   *
   * The server sends the decision **with** its review state on purpose: a page
   * that could render a review without the text would be grading from memory,
   * which is the hindsight this feature exists to prevent (spec 021 §五).
   */
  const describeOne = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取这条决策。'),
    [],
  )
  const loadOne = useCallback(
    () =>
      currentId === null
        ? Promise.resolve<{ decision: Decision; latest: DecisionReview | null } | null>(null)
        : getDecisionReview(currentId),
    [currentId],
  )
  const { data: detail } = useResource(loadOne, [currentId], describeOne)
  const decision = detail?.decision ?? null
  const previous = detail?.latest ?? null

  const submit = useCallback(
    async (body: { process_score: number; outcome?: DecisionOutcome }) => {
      if (!current) return
      setSubmitting(true)
      setSubmitError(null)
      try {
        setVerdict(await recordDecisionReview({ decision_id: current.decision_id, ...body }))
      } catch (cause) {
        setSubmitError(cause instanceof ApiError ? cause.message : '无法记录这次复盘。')
      } finally {
        setSubmitting(false)
      }
    },
    [current],
  )

  const refresh = useCallback(() => {
    setIndex(0)
    setPicked(null)
    setVerdict(null)
    setSubmitError(null)
    reload()
  }, [reload])

  const next = useCallback(() => {
    if (index + 1 >= queue.length) {
      refresh()
      return
    }
    setIndex(index + 1)
    setPicked(null)
    setVerdict(null)
  }, [index, queue.length, refresh])

  if (loading) {
    return <PageSkeleton label="读取复盘队列" />
  }

  if (loadError && queue.length === 0) {
    return (
      <Page>
        <ErrorNote message={loadError} />
      </Page>
    )
  }

  if (queue.length === 0) {
    return (
      <Page>
        <EmptyState
          title="现在没有到期的复盘"
          body="记决策的时候写下「什么时候回来看看」，到期了它会自己出现在这里。没写就不来。"
          action={{ href: TODAY_HREF, label: '回到今天' }}
        />
      </Page>
    )
  }

  if (verdict) {
    return (
      <Page>
        <div
          data-testid="retro-verdict"
          data-quadrant={verdict.quadrant}
          data-active="false"
        >
          {/*
            The verdict, in the domain's words. Rendered, never composed here. In
            the dangerous quadrant this is the *only* line: there is no figure to
            show, because none was ever recorded. That is red line 10 resting on
            the data model rather than on this component's restraint.
          */}
          <p className="serif text-[18px] leading-relaxed" data-testid="retro-guidance">
            {verdict.guidance}
          </p>
          <button
            type="button"
            className="mt-4 text-navy"
            onClick={next}
            data-testid="retro-next"
          >
            {index + 1 >= queue.length ? '看看还有没有' : '下一条'}
          </button>
        </div>
      </Page>
    )
  }

  const pickScore = (value: number) => () => {
    if (!current) return
    setPicked(value)
    if (!current.is_due) {
      // Not due, so the outcome does not exist yet — and the process score needs
      // no second step. Submitting it here is the whole interaction: the gate
      // is that there is nothing left afterwards to fill in.
      void submit({ process_score: value })
    }
    // Due: wait for the outcome choice, which submits both together. Picking a
    // score on its own would leave a half-review sitting in the UI looking
    // unfinished, and "unfinished" is exactly the state that invites a guess.
  }

  return (
    <Page>
      {/* A count in a sentence, not a progress bar (red line 11). */}
      <h1 className="text-[13px] tracking-wide text-ink-faint">
        到期要看的 {queue.length} 条决策
      </h1>

      {decision ? (
        <article className="mt-6" data-testid="retro-decision">
          <div className="border-l-2 border-navy pl-4">
            <p className="serif text-[18px] leading-relaxed" data-testid="retro-rationale">
              {decision.rationale}
            </p>
          </div>
          <div className="mt-4 space-y-2 text-[13px] text-ink-soft">
            <p data-testid="retro-counter">反面：{decision.counter_evidence}</p>
            {decision.kill_criteria.map((criterion, i) => (
              <p key={i} data-testid="retro-kill">
                作废条件：{criterion.metric} {criterion.operator} {criterion.threshold}（
                {criterion.as_of}）
              </p>
            ))}
          </div>
          <a
            href={instrumentHref(decision.market, decision.code)}
            className="mt-3 inline-block text-[12px] text-navy"
          >
            {decision.display} →
          </a>
        </article>
      ) : (
        <p className="mt-6 text-ink-faint">读取这条决策…</p>
      )}

      <div className="mt-8" data-testid="retro-scores">
        <p className="text-[12px] text-ink-faint">过程分：当时这个推理有多站得住？</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              disabled={submitting}
              onClick={pickScore(value)}
              className="border border-rule px-3 py-2 text-[13px]"
              data-testid={`retro-score-${value}`}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {current?.is_due ? (
        picked === null ? (
          <p className="mt-6 text-[12px] text-ink-faint" data-testid="retro-pick-first">
            先给过程分，再看结果。
          </p>
        ) : (
          <div className="mt-6" data-testid="retro-outcome">
            <p className="text-[12px] text-ink-faint">然后：结果如何？</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(['good', 'bad', 'failed'] as const).map((outcome) => (
                <button
                  key={outcome}
                  type="button"
                  disabled={submitting}
                  onClick={() => void submit({ process_score: picked, outcome })}
                  className="border border-rule px-3 py-2 text-[13px]"
                  data-testid={`retro-outcome-${outcome}`}
                >
                  {outcome === 'good' ? '结果好' : outcome === 'bad' ? '结果不好' : '失败了'}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[12px] text-ink-faint">
              只有「好 / 不好 / 失败」三档。系统不记金额，也不算收益率。
            </p>
          </div>
        )
      ) : (
        /*
         * Not rendered at all, and that is the gate (red line 4, `项目总纲` P0-3).
         * The process score above already submitted itself; there is nothing left
         * to fill in, so there is nothing to invite.
         */
        <p className="mt-6 text-[12px] text-ink-faint" data-testid="retro-not-due">
          没到期，所以结果那一栏不存在 —— 提前打分会用结果污染过程分。
        </p>
      )}

      {previous ? (
        <p className="mt-4 text-[12px] text-ink-faint" data-testid="retro-previous">
          你在 {previous.reviewed_at.slice(0, 10)} 写过一条。
        </p>
      ) : null}

      {submitError ? (
        <p className="mt-4 text-[12px] text-ink-soft" data-testid="retro-error">
          {submitError}
        </p>
      ) : null}
    </Page>
  )
}
