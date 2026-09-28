import { useState } from 'react'
import type { KillCriterion } from './api'
import { formatPredicate } from './format'
import { Button, Input } from './components/ui'
import {
  DEFAULT_ANNUAL_RATE,
  depthsIncluding,
  formatGain,
  formatRate,
  formatYears,
  gainNeeded,
  isOwnDepth,
  yearsToRecover,
} from './recovery'

/**
 * The stop-loss prompt — the moment a position is down and the reader is
 * deciding whether to wait.
 *
 * **Red line 12, and it is checked by rule S-09**
 * (`backend/checks/rules/time_cost_in_stop_loss.py`): a stop-loss prompt that
 * shows only the percentage is the version everyone already ignores. "Down 32%"
 * is a number attached to a position; "about 2.8 years to get back to even" is a
 * number attached to a life. Only the second one changes what a person does, so
 * the recovery figure is not a nice extra here — it is the component.
 *
 * Three things this deliberately does **not** do:
 *
 * 1. **It does not recommend anything.** There is no "sell" button and no
 *    verdict. The product's job is to make the cost legible, not to decide.
 * 2. **It does not hide its assumption.** The annual rate is an input on
 *    screen, because a recovery estimate with a hidden assumption is a number
 *    pretending to be a fact — and a reader who cannot see the rate cannot tell
 *    whether they are being flattered.
 * 3. **It does not ask "should you sell?"** It reads back the conditions the
 *    reader wrote for themselves and asks why they are not being followed. That
 *    is the question the record exists to make askable.
 */
interface Props {
  /** The falsifiable conditions the reader wrote for this instrument. */
  criteria: KillCriterion[]
  onClose: () => void
}

export default function StopLossPrompt({ criteria, onClose }: Props) {
  // Both inputs are held as strings so an empty box stays empty. Parsing to a
  // number is this component's job, and `Number.isFinite` below is what stops
  // an empty box from rendering as a confident answer.
  const [lossText, setLossText] = useState('')
  const [rateText, setRateText] = useState(String(DEFAULT_ANNUAL_RATE * 100))

  const loss = Number(lossText) / 100
  const rate = Number(rateText) / 100
  const usable = lossText.trim() !== '' && loss > 0 && loss < 1
  const rateUsable = rateText.trim() !== '' && rate > 0

  const years = yearsToRecover(loss, rate)
  const gain = gainNeeded(loss)

  return (
    <section className="mt-3 border border-rule border-l-2 border-l-warn bg-paper-soft px-4 py-3">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[11px] font-normal uppercase tracking-[0.06em] text-ink-faint">
          算一下「再等等」要等多久
        </h3>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onClose}>
          收起
        </Button>
      </div>

      <p className="mt-1.5 text-[13px] text-ink-soft">
        亏损的百分比是记不住的。要多少年才能回到成本，是能记住的。
      </p>

      <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">当前亏损</span>
          <span className="flex items-baseline gap-1">
            <Input
              type="number"
              inputMode="decimal"
              min="0"
              max="99"
              step="0.1"
              value={lossText}
              onChange={(event) => setLossText(event.target.value)}
              placeholder="32"
              className="num w-[86px]"
            />
            <span className="text-[12px] text-ink-faint">%</span>
          </span>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
            假定年化 <span className="normal-case">（这是假设，不是事实）</span>
          </span>
          <span className="flex items-baseline gap-1">
            <Input
              type="number"
              inputMode="decimal"
              min="0.1"
              step="0.5"
              value={rateText}
              onChange={(event) => setRateText(event.target.value)}
              placeholder="15"
              className="num w-[86px]"
            />
            <span className="text-[12px] text-ink-faint">%</span>
          </span>
        </label>
      </div>

      {usable && rateUsable ? (
        <>
          <div className="mark mt-3 border-l-2 border-l-up py-1">
            <p className="text-[13px]">
              恢复所需年数：约{' '}
              {/* Serif at 18px, and the largest number in the product. It is a
                  quotation of the reader's own two inputs rather than
                  interface text, so rule 1 applies; 20px read as a headline. */}
              <span className="num serif text-[18px]">{formatYears(years)}</span> 年
              <span className="text-ink-soft">（按年化 {formatRate(rate)} 计）</span>
            </p>
            <p className="num mt-0.5 text-[12px] text-ink-soft">
              需要先涨回 {formatGain(gain)} 才能回到成本 —— 亏损是不对称的。
            </p>
          </div>

          <DepthTable rate={rate} highlight={loss} />
        </>
      ) : (
        <p className="mt-3 text-[13px] text-ink-faint">
          填一个 0 到 99 之间的亏损比例，这里会给出年数。空着就不给 —— 猜一个数字比不给更糟。
        </p>
      )}

      <CriteriaReadback criteria={criteria} />

      <p className="mt-3 text-[12px] text-ink-faint">
        这里没有「要不要卖」。上面的条件是<strong className="text-ink">你自己写的</strong>
        —— 它触发没有，你比我清楚。要改主意，把理由写进下面的表单，它会留下时间戳。
      </p>
    </section>
  )
}

/**
 * The same loss at several depths, so the reader can see where they are standing.
 *
 * Their own row is marked, and inserted if it is not already one of the fixed
 * depths — a reader down 32% needs to see 32% in the column, not interpolate
 * between 30% and 50%. One number in isolation says "this is my situation"; a
 * column says "and here is how much worse it gets", which is the fact that
 * actually bears on the decision.
 */
function DepthTable({ rate, highlight }: { rate: number; highlight: number }) {
  return (
    <table className="mt-3 w-full text-[12px]">
      <thead>
        <tr className="border-b border-rule text-left text-ink-faint">
          {/* Uppercase chrome at 11px, like `DataTable`'s headers, and the two
              numeric columns right-aligned so the figures line up on the
              decimal — otherwise the eye has to re-find each number. */}
          <th className="py-1 text-[11px] font-normal uppercase tracking-[0.06em]">亏损</th>
          <th className="py-1 text-right text-[11px] font-normal uppercase tracking-[0.06em]">
            回到成本需要涨
          </th>
          <th className="py-1 text-right text-[11px] font-normal uppercase tracking-[0.06em]">
            按年化 {formatRate(rate)} 需要
          </th>
        </tr>
      </thead>
      <tbody>
        {depthsIncluding(highlight).map((depth) => {
          const isMine = isOwnDepth(highlight, depth)
          return (
            <tr
              key={depth}
              className={`border-b border-[color:var(--color-rule-soft)] ${isMine ? 'text-ink' : 'text-ink-soft'}`}
            >
              <td className="num py-1">
                {isMine && <span className="text-up">▸ </span>}
                {Math.round(depth * 100)}%
              </td>
              <td className="num py-1 text-right">{formatGain(gainNeeded(depth))}</td>
              <td className="num py-1 text-right">{formatYears(yearsToRecover(depth, rate))} 年</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/**
 * The reader's own kill criteria, read back verbatim.
 *
 * Not a summary and not a paraphrase. These are the exact predicates they
 * committed to, and the confrontation only works if they recognise the words as
 * their own — which means showing the stored form, not a tidier version of it.
 */
function CriteriaReadback({ criteria }: { criteria: KillCriterion[] }) {
  if (criteria.length === 0) {
    return (
      <p className="mt-4 text-[13px] text-ink-soft">
        你还没有为这个标的写下失效条件 —— 所以没有任何东西能在将来提醒你。
      </p>
    )
  }

  return (
    <div className="mt-4">
      <p className="text-[12px] text-ink-faint">
        你当初为它写下的失效条件（{criteria.length} 条）：
      </p>
      <ol className="mt-1">
        {criteria.map((criterion, index) => (
          <li
            key={`${criterion.metric}-${criterion.as_of}-${index}`}
            className="mark border-l-2 border-l-brass py-1 text-[13px]"
          >
            {formatPredicate(criterion)}
          </li>
        ))}
      </ol>
    </div>
  )
}
