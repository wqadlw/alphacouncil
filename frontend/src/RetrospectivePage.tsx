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
 *
 * ## ⭐ Why the shell is a *constraint* here and not just a frame
 *
 * Red line 10 is enforced in its strongest form: in the dangerous quadrant the
 * **entire page body** must contain no digit — `retrospective.spec.ts:120`
 * asserts it against `document.body`, not against this component. So every
 * element the shell adds is also inside the blast radius, and this page is the
 * reason the shell was built digit-free in the first place.
 *
 * Two consequences worth keeping in mind when the shell changes again:
 *
 * - **The `⌘K` hint in the top bar is load-bearing.** It is the one piece of
 *   chrome that most wants to render a number, and it renders a letter.
 * - **The verdict state renders the guidance and one button. Nothing else.** A
 *   queue count here would satisfy "a fact about the reader" and still break the
 *   assertion, because the queue is still `N` items long while the verdict is on
 *   screen. Which is also why the verdict state does not get the count sentence
 *   the other two states have — and, like the review page, it deliberately does
 *   not render a list of what is left (red line 11; see `ReviewPage`'s header).
 */

/**
 * A reading measure for the prose. Same reasoning as `ReviewPage`: one column of
 * serif stretched across a wide pane loses the line on the return sweep.
 */
const READING_COLUMN = 'max-w-[660px]'

import { useCallback, useMemo, useState } from 'react'
import {
  ApiError,
  getDecisionReview,
  getRecentDecisionReviews,
  getDueDecisionReviews,
  recordDecisionReview,
  type Decision,
  type DecisionOutcome,
  type DecisionReview,
  type ReviewState,
} from './api'
import { instrumentHref, TODAY_HREF } from './routing'
import { Button, EmptyState, ErrorNote, Skeleton } from './components/ui'
import LessonComposer from './components/knowledge/LessonComposer'
import { useResource } from './useResource'

export default function RetrospectivePage() {
  const describeQueue = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取复盘队列。'),
    [],
  )
  const describeRecent = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取复盘记录。'),
    [],
  )
  const { data: recent } = useResource<ReviewState[]>(
    getRecentDecisionReviews,
    [],
    describeRecent,
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

  /**
   * ⭐ **Due first, then reviewed**, deduped by id.
   *
   * The page's only list used to be the *due* one, and a decision leaves it the
   * moment its review is written — so a review you had already done was invisible
   * here, and the lesson composer was unreachable: correctly hidden before the
   * review, gone from the only list afterwards. Found by opening the app.
   *
   * Due leads because those are waiting on an answer. Reviewed follow because they
   * are there to be read and to yield a lesson, not to be worked through. A
   * decision that is both due *and* already graded appears in both lists, and
   * listing it twice would let the reader grade it twice from one page.
   */
  const queue = useMemo(() => {
    const seen = new Set<string>()
    const out: ReviewState[] = []
    for (const row of [...(rows ?? []), ...(recent ?? [])]) {
      if (seen.has(row.decision_id)) continue
      seen.add(row.decision_id)
      out.push(row)
    }
    return out
  }, [rows, recent])
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

  /**
   * ⭐ **Has this decision already been graded?** A separate question from
   * is_due, and the page needs both: is_due decides whether to offer the outcome
   * choice, this decides whether to offer a score at all. They coincide only for a
   * decision that is due *and* ungraded — the one case this page was built for, and
   * the only one where the two answers being equal is not a coincidence.
   *
   * Declared **here** rather than next to current, because previous comes from
   * the second resource below and TS2448 says so. ⭐ A cast or an ny would
   * have silenced both errors and left the ordering bug in place — and a flag
   * whose definition depends on declaration order is not obviously anything.
   */
  const graded = Boolean(previous ?? verdict)

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
    // ⚠️ Static blocks, and deliberately **digit-free**: the skeleton is part of
    // the page body too, so a `w-6` or a `h-5` written as an arbitrary pixel
    // value in a class is fine, but anything that renders text is not.
    return (
      <div className={`px-4 py-4 ${READING_COLUMN}`}>
        <Skeleton width="120px" />
        <Skeleton size="title" className="mt-6 w-full" />
        <Skeleton size="title" className="mt-2 w-2/3" />
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
        title="现在没有到期的复盘"
        body="记决策的时候写下「什么时候回来看看」，到期了它会自己出现在这里。没写就不来。"
        action={{ href: TODAY_HREF, label: '回到今天' }}
      />
    )
  }

  if (verdict) {
    return (
      <div className={`px-4 py-6 ${READING_COLUMN}`}>
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

            ⭐ No queue count, no position, no "第 N 条" — see this file's header.
            The count is a fact about the reader and would still be a digit in a
            quadrant where the whole body must contain none.
          */}
          <p className="serif text-[18px] leading-relaxed" data-testid="retro-guidance">
            {verdict.guidance}
          </p>
          <Button className="mt-4" onClick={next} data-testid="retro-next">
            {index + 1 >= queue.length ? '看看还有没有' : '下一条'}
          </Button>
        </div>
      </div>
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
    <div className={`px-4 py-4 ${READING_COLUMN}`}>
      {/* A count in a sentence, not a progress bar (red line 11). This state is
          allowed digits: the assertion only covers the dangerous-quadrant
          verdict, where there is nothing to count. */}
      <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
        到期要看的 <span className="num">{queue.length}</span> 条决策
      </h2>

      {decision ? (
        <article className="mt-5" data-testid="retro-decision">
          {/* The reader's own words, in serif (rule 1). The graded text is the
              point of this page, so it is the largest thing in it. */}
          <div className="border-l-2 border-l-navy pl-4">
            <p className="serif text-[18px] leading-relaxed" data-testid="retro-rationale">
              {decision.rationale}
            </p>
          </div>
          <div className="mt-4 space-y-1.5 text-[13px] text-ink-soft">
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
            className="mt-3 inline-block text-[12px] text-navy no-underline hover:underline"
          >
            {decision.display} →
          </a>
        </article>
      ) : (
        <p className="mt-5 text-[13px] text-ink-faint">读取这条决策…</p>
      )}

      {/*
        ⭐ **Gated on 「has this been graded?」, not on `is_due`.** Those are two
        different questions and the page needs the second one: `is_due` decides
        whether to offer the *outcome* choice, while a reviewed decision still owes
        the reader their own score.

        The score block used to sit outside the `is_due` conditional, on the
        assumption that 「not due」 meant 「not yet graded」 — true while this page
        listed only due decisions, and false once spec 030's follow-up added the
        reviewed ones. ⭐ The browser showed the page contradicting itself in
        consecutive lines: 「都不会再变」 directly above five buttons that change it.

        ⭐ And when it *has* been graded, the score is **shown** rather than hidden.
        The reader came here to look at their own reasoning; a page that omits the
        number it is about does not answer the question. It is their number — this
        system never assigns one, and the quadrant verdict above already refuses to
        render a grade.
      */}
      {graded ? (
        <div className="mt-7" data-testid="retro-score-given">
          <p className="text-[12px] text-ink-faint">你当时给的过程分</p>
          <p className="serif mt-1 text-[20px] text-ink num" data-testid="retro-score-value">
            {(previous ?? verdict)?.process_score}
          </p>
        </div>
      ) : (
        <div className="mt-7" data-testid="retro-scores">
          <p className="text-[12px] text-ink-faint">过程分：当时这个推理有多站得住？</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5].map((value) => (
              <Button
                key={value}
                disabled={submitting}
                onClick={pickScore(value)}
                data-testid={`retro-score-${value}`}
                className="num w-11"
              >
                {value}
              </Button>
            ))}
          </div>
        </div>
      )}

      {current?.is_due ? (
        picked === null ? (
          <p className="mt-5 text-[12px] text-ink-faint" data-testid="retro-pick-first">
            先给过程分，再看结果。
          </p>
        ) : (
          <div className="mt-5" data-testid="retro-outcome">
            <p className="text-[12px] text-ink-faint">然后：结果如何？</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(['good', 'bad', 'failed'] as const).map((outcome) => (
                <Button
                  key={outcome}
                  disabled={submitting}
                  onClick={() => void submit({ process_score: picked, outcome })}
                  data-testid={`retro-outcome-${outcome}`}
                >
                  {outcome === 'good' ? '结果好' : outcome === 'bad' ? '结果不好' : '失败了'}
                </Button>
              ))}
            </div>
            <p className="mt-2 text-[12px] text-ink-faint">
              只有「好 / 不好 / 失败」三档。系统不记金额，也不算收益率。
            </p>
          </div>
        )
      ) : previous || verdict ? (
        /*
         * ⭐ **The third branch, and it exists because the second one's copy became
         * false.** Once reviewed decisions could appear here, a decision you had
         * already graded arrived with `is_due: false` and fell into 「没到期」 — which
         * is untrue for it. What it should say is 「你已经复盘过了」.
         *
         * A simple sentence that is false on a page is worse than no sentence, and
         * the lesson composer lives in exactly this branch — so without it the
         * reader lands on a claim the page has just contradicted, and *then* finds a
         * form for writing a lesson.
         */
        <p className="mt-5 text-[12px] text-ink-faint" data-testid="retro-already-done">
          你已经复盘过了。过程分和结果都不会再变 —— 复盘是只追加的。
        </p>
      ) : (
        /*
         * Not rendered at all, and that is the gate (red line 4, `项目总纲` P0-3).
         * The process score above already submitted itself; there is nothing left
         * to fill in, so there is nothing to invite.
         */
        <p className="mt-5 text-[12px] text-ink-faint" data-testid="retro-not-due">
          没到期，所以结果那一栏不存在 —— 提前打分会用结果污染过程分。
        </p>
      )}

      {previous ? (
        <p className="mt-4 text-[12px] text-ink-faint" data-testid="retro-previous">
          你在 {previous.reviewed_at.slice(0, 10)} 写过一条。
        </p>
      ) : null}

      {/*
        ⭐ 「记一条教训」 appears only once a review exists for this decision, and
        that is the **server's** rule rather than a UI preference: a lesson is a
        statement about what a review taught you, so it has nothing to attach to
        before the review is written (`LESSON_REVIEW_MISSING` is a 409).

        And this is the answer to where 「经验」 gets recorded — **here**, on the
        screen where the review is, rather than on a page of its own that the reader
        has to go and find. A lesson is derived from a review, and a page you must
        go looking for is a page most people never visit. Same reasoning as spec
        029's 「记一条」 on the vault: not hidden behind a control.

        `previous || verdict` is a **derivation**, and unlike spec 029's `formOpen`
        this one cannot be wrong — neither term is a quantity the reader's own action
        changes after the fact.
      */}
      {current && (previous || verdict) ? (
        <LessonComposer decisionId={current.decision_id} />
      ) : null}

      {submitError ? (
        <p className="mt-4 text-[12px] text-ink-soft" data-testid="retro-error">
          {submitError}
        </p>
      ) : null}
    </div>
  )
}
