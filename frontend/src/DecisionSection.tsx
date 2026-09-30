import { useState } from 'react'
import type { Decision } from './api'
import DecisionForm from './DecisionForm'
import StopLossPrompt from './StopLossPrompt'
import { ACTION_LABEL, formatMoment, formatPredicate } from './format'
import { Button } from './components/ui'

/**
 * The decision layer on an instrument page: what I believed, in what order, and
 * the gate for the next one.
 *
 * Read order is **oldest first**, the same as the watchlist log and for the same
 * reason: "I bought, then I added, then I trimmed" is a story about a person
 * changing their mind, and reversing it leaves three unrelated rows. The
 * timestamp is shown on every row because it is not metadata here — it is the
 * evidence. A decision is only worth something if it can be shown to predate the
 * outcome, and the id *is* that moment.
 */
interface Props {
  market: string
  code: string
  decisions: Decision[]
  onRecorded: (decision: Decision) => void
}

export default function DecisionSection({ market, code, decisions, onRecorded }: Props) {
  const [promptOpen, setPromptOpen] = useState(false)

  // The latest statement of "what would prove me wrong". Not the union of every
  // condition ever written: a criterion from a decision that has since been
  // superseded is a belief the reader has already revised, and reading it back
  // would be quoting them against themselves on a position they no longer hold.
  const latest = decisions.length > 0 ? decisions[decisions.length - 1] : null
  const criteria = latest?.kill_criteria ?? []

  return (
    <section className="mt-4">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta font-normal caps text-ink-faint">
          我对它下过什么判断
        </h2>
        {decisions.length > 0 ? (
          <span className="num type-badge text-ink-faint">{decisions.length} 条决策</span>
        ) : null}
      </div>
      <div className="border-b border-rule" />

      {decisions.length === 0 ? (
        <p className="px-4 pt-2 type-prose text-ink-soft">
          还没有为它做过任何决策。上面那条关注理由是你对它的看法，
          但看法和决策不同 —— 决策要写下「什么能证明我错了」。
        </p>
      ) : (
        <div className="px-4 pt-2">
          <p className="type-prose text-ink-faint">
            按写入顺序排列。每一条的时间戳都是服务端盖的，改不了 ——
            这就是「我是在结果出来之前这么想的」唯一的凭据。
          </p>
          <ol className="mt-1.5">
            {decisions.map((decision) => (
              <DecisionRow key={decision.id} decision={decision} />
            ))}
          </ol>
        </div>
      )}

      {decisions.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 px-4">
          <Button size="sm" onClick={() => setPromptOpen((open) => !open)}>
            {promptOpen ? '收起' : '我正在亏着 —— 算一下要等多久'}
          </Button>
          <span className="type-meta text-ink-faint">
            不是让你卖。是让你知道「再等等」到底要等多久。
          </span>
        </div>
      )}

      {promptOpen && (
        <div className="px-4">
          <StopLossPrompt criteria={criteria} onClose={() => setPromptOpen(false)} />
        </div>
      )}

      <div className="px-4">
        <DecisionForm market={market} code={code} onRecorded={onRecorded} />
      </div>
    </section>
  )
}

function DecisionRow({ decision }: { decision: Decision }) {
  return (
    <li className="mark border-b border-[color:var(--color-rule-soft)] border-l-2 border-l-navy py-1.5">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="type-prose text-ink">
          {ACTION_LABEL[decision.action] ?? decision.action}
        </span>
        {/* ⭐ The moment, once.
            This row used to render `formatMoment(decision.id)` *and* the raw
            `decision.id` on the next span, so every decision showed the same
            instant twice — once readable, once as
            `2026-09-28T06:12:47.514Z`. The raw id is the primary key (that is
            what makes `get_by_id` exact), not something a reader can act on, and
            at 24 characters it was the widest thing in the row. */}
        <span className="num type-meta text-ink-faint">{formatMoment(decision.id)}</span>
      </div>

      <div className="mt-1 grid gap-1 sm:grid-cols-2">
        <div className="mark border-l-2 border-l-navy py-1">
          <p className="type-meta caps text-ink-faint">为什么</p>
          <p className="type-prose text-ink">{decision.rationale}</p>
        </div>
        <div className="mark border-l-2 border-l-brass py-1">
          <p className="type-meta caps text-ink-faint">反面证据</p>
          <p className="type-prose text-ink-soft">{decision.counter_evidence}</p>
        </div>
      </div>

      <div className="mt-1.5">
        <p className="type-meta caps text-ink-faint">失效条件</p>
        <ul className="mt-0.5">
          {decision.kill_criteria.map((criterion, index) => (
            <li
              key={`${criterion.metric}-${criterion.as_of}-${index}`}
              className="num type-meta text-ink-soft"
 >
              {formatPredicate(criterion)}
            </li>
          ))}
        </ul>
      </div>
    </li>
  )
}
