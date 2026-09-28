import { useState } from 'react'
import { ApiError, recordDecision, type ComparisonOperator, type Decision, type DecisionAction } from './api'
import { ACTION_LABEL, OPERATOR_LABEL } from './format'
import { Button, Input, Textarea } from './components/ui'

/**
 * Recording a decision — the gate, and the only screen in the product that
 * writes something the future cannot revise.
 *
 * Three fields are required and the submit button stays disabled until all
 * three are filled. That is not form validation; it is the product. A decision
 * whose `counter_evidence` is blank is a decision taken with only one side
 * considered, and the whole reason this table exists is that the other side has
 * to be written down **before** the outcome is known — afterwards, memory
 * supplies it retroactively and the record becomes worthless.
 *
 * **The kill criteria are a structured editor, not a textarea** (ADR-0017 #5).
 * "营收同比转负就重评" as prose cannot be evaluated, so nothing can watch it,
 * so it can never come and find you — and "the data comes to you" is the
 * product's third highlight. Four fields per condition is more work than one
 * sentence. That cost is the feature.
 *
 * The frontend checks **completeness**, never **validity**. Whether
 * `gross_margin` is a well-formed metric token is the domain's question, and a
 * second copy of that rule here would be a second chance to disagree with it —
 * so an ill-shaped token goes to the server and comes back with the domain's own
 * sentence, which is displayed as-is.
 */
interface Props {
  market: string
  code: string
  onRecorded: (decision: Decision) => void
}

const ACTIONS: readonly DecisionAction[] = ['buy', 'add', 'hold', 'trim', 'exit']
const OPERATORS: readonly ComparisonOperator[] = ['<', '<=', '>', '>=', '==', '!=']

interface CriterionRow {
  id: number
  metric: string
  operator: ComparisonOperator
  threshold: string
  asOf: string
}

//: Keys for React's reconciliation only — never sent anywhere. A module counter
//: is enough because the requirement is uniqueness within one session, not
//: stability across reloads.
let rowSeq = 0

function blankRow(): CriterionRow {
  rowSeq += 1
  return { id: rowSeq, metric: '', operator: '<', threshold: '', asOf: '' }
}

/** Filled in, as opposed to well-formed. See the note in the docstring. */
function isComplete(row: CriterionRow): boolean {
  return (
    row.metric.trim() !== '' &&
    row.threshold.trim() !== '' &&
    Number.isFinite(Number(row.threshold)) &&
    row.asOf.trim() !== ''
  )
}

export default function DecisionForm({ market, code, onRecorded }: Props) {
  const [action, setAction] = useState<DecisionAction>('buy')
  const [rationale, setRationale] = useState('')
  const [counterEvidence, setCounterEvidence] = useState('')
  const [rows, setRows] = useState<CriterionRow[]>(() => [blankRow()])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; fix: string | null } | null>(null)

  const rationaleMissing = rationale.trim() === ''
  const counterMissing = counterEvidence.trim() === ''
  const incomplete = rows.filter((row) => !isComplete(row))
  const blocked = rationaleMissing || counterMissing || incomplete.length > 0

  function updateRow(id: number, patch: Partial<CriterionRow>) {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  function removeRow(id: number) {
    // The last row cannot be removed: a decision with no falsifiable condition
    // is not a decision, and letting the editor reach that state would mean
    // offering a shape the domain refuses.
    setRows((current) => (current.length === 1 ? current : current.filter((row) => row.id !== id)))
  }

  function reset() {
    setRationale('')
    setCounterEvidence('')
    setRows([blankRow()])
    setAction('buy')
  }

  async function handleSubmit() {
    if (blocked || busy) return
    setBusy(true)
    setError(null)
    try {
      const recorded = await recordDecision({
        ticker: code,
        market,
        action,
        rationale: rationale.trim(),
        counter_evidence: counterEvidence.trim(),
        kill_criteria: rows.map((row) => ({
          metric: row.metric.trim(),
          operator: row.operator,
          threshold: Number(row.threshold),
          as_of: row.asOf,
        })),
      })
      onRecorded(recorded)
      reset()
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? { message: caught.message, fix: caught.fix }
          : { message: '写入失败。', fix: null },
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="mt-4 border-t border-rule pt-3"
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <h3 className="text-[11px] font-normal uppercase tracking-[0.06em] text-ink-faint">
        记录一个决策
      </h3>
      <p className="mt-1 text-[12px] text-ink-faint">
        写下来之后不能改、不能删 —— 「改变想法」是再写一条。这三项都是必填，
        因为一条缺了反面证据的决策，事后会被记忆补全成它从来不是的样子。
      </p>

      <fieldset className="mt-2.5">
        <legend className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">做了什么</legend>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {ACTIONS.map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              aria-pressed={action === value}
              // ⭐ Filled navy marks the *current selection*, not the recommended
              // one. 买入 / 加仓 / 持有 / 减仓 / 清仓 is a five-way choice the reader
              // has already made; giving any of them a "primary" look as if the
              // product had an opinion is the same mistake the review page avoids
              // by giving all five ratings identical weight.
              variant={action === value ? 'primary' : 'default'}
              onClick={() => setAction(value)}
            >
              {ACTION_LABEL[value]}
            </Button>
          ))}
        </div>
      </fieldset>

      <label className="mt-3 flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
          为什么 <span className="text-up">必填</span>
          <span className="normal-case text-ink-faint"> —— 你以后会被这句话审问</span>
        </span>
        <Textarea
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          rows={2}
          placeholder="例如：市场把渠道库存的回补当成了终端需求，实际动销没有跟上"
        />
      </label>

      <label className="mt-2.5 flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
          反面证据 <span className="text-up">必填</span>
          <span className="normal-case text-ink-faint">
            {' '}
            —— 反对你自己的那一面。这是唯一能对抗确认偏差的字段
          </span>
        </span>
        <Textarea
          value={counterEvidence}
          onChange={(event) => setCounterEvidence(event.target.value)}
          rows={2}
          placeholder="例如：批价仍在下跌，说明渠道还在去库存；上一轮同样的判断错了 9 个月"
        />
      </label>

      <div className="mt-3">
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
            失效条件 <span className="text-up">至少一条</span>
            <span className="normal-case text-ink-faint"> —— 什么能证明我错了</span>
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => setRows((c) => [...c, blankRow()])}
          >
            + 再加一条
          </Button>
        </div>

        <ol className="mt-1.5">
          {rows.map((row, index) => (
            <CriterionEditor
              key={row.id}
              row={row}
              index={index}
              removable={rows.length > 1}
              onChange={(patch) => updateRow(row.id, patch)}
              onRemove={() => removeRow(row.id)}
            />
          ))}
        </ol>

        <p className="mt-1 text-[12px] text-ink-faint">
          写成四段而不是一句话，是为了让数据将来能<strong className="text-ink">自己来</strong>
          告诉你条件触发了。一句话没人能计算，也就永远不会来找你。
        </p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" disabled={blocked || busy}>
          {busy ? '写入中…' : '记下来'}
        </Button>
        <span className="text-[12px] text-ink-faint">
          {blocked
            ? `还差：${[
                rationaleMissing ? '为什么' : null,
                counterMissing ? '反面证据' : null,
                incomplete.length > 0 ? `${incomplete.length} 条没填完的失效条件` : null,
              ]
                .filter(Boolean)
                .join('、')}`
            : '写入后会带一个服务端时间戳，它证明这句话是在结果出来之前写的。'}
        </span>
      </div>

      {error && (
        <div className="mark mt-2 border-l-2 border-l-up py-1">
          <p className="text-[13px] text-up">{error.message}</p>
          {error.fix && <p className="text-[12px] text-ink-soft">{error.fix}</p>}
        </div>
      )}
    </form>
  )
}

/**
 * One predicate: `{metric, operator, threshold, as_of}`.
 *
 * `as_of` is labelled as a cutoff rather than a deadline because it is one. It
 * answers "which figures may be read", not "when should I check" — reading a
 * figure announced after the question was asked is how a review quietly turns
 * into hindsight (constitution rule 20).
 */
function CriterionEditor({
  row,
  index,
  removable,
  onChange,
  onRemove,
}: {
  row: CriterionRow
  index: number
  removable: boolean
  onChange: (patch: Partial<CriterionRow>) => void
  onRemove: () => void
}) {
  return (
    <li className="mark mt-1.5 border-l-2 border-l-rule py-1.5">
      <div className="flex flex-wrap items-end gap-x-2 gap-y-1.5">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
            指标 #{index + 1}
          </span>
          <Input
            value={row.metric}
            onChange={(event) => onChange({ metric: event.target.value })}
            placeholder="gross_margin"
            className="num w-[132px]"
            spellCheck={false}
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">关系</span>
          {/* Native, for the same reason as the pool page's selects: a real
              listbox needs `aria-activedescendant` and focus management, and
              hand-rolling that badly is worse than looking slightly plain. */}
          <select
            value={row.operator}
            onChange={(event) => onChange({ operator: event.target.value as ComparisonOperator })}
            className="h-8 rounded-[2px] border border-rule bg-surface px-2 text-[13px] outline-none focus:border-navy"
          >
            {OPERATORS.map((operator) => (
              <option key={operator} value={operator}>
                {OPERATOR_LABEL[operator]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">阈值</span>
          <Input
            type="number"
            inputMode="decimal"
            step="any"
            value={row.threshold}
            onChange={(event) => onChange({ threshold: event.target.value })}
            placeholder="0.55"
            className="num w-[92px]"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
            按截至哪天公布的数据
          </span>
          <Input
            type="date"
            value={row.asOf}
            onChange={(event) => onChange({ asOf: event.target.value })}
            className="num"
          />
        </label>

        {removable && (
          <Button size="sm" variant="ghost" onClick={onRemove}>
            删掉
          </Button>
        )}
      </div>

      {isComplete(row) && (
        <p className="mt-0.5 text-[12px] text-ink-soft">
          读作：截至 {row.asOf}，{row.metric.trim()} {OPERATOR_LABEL[row.operator]} {row.threshold}
        </p>
      )}
    </li>
  )
}
