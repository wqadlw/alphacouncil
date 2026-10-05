import { useEffect, useState } from 'react'
import {
  ApiError,
  getMetrics,
  recordDecision,
  type ComparisonOperator,
  type Decision,
  type DecisionAction,
  type MetricCatalogue,
} from './api'
import { ACTION_LABEL, OPERATOR_LABEL } from './format'
import { Button, Input, Textarea } from './components/ui'
import { METRIC_DATALIST_ID, uncomputable } from './metricVocabulary'

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
 * The frontend checks **completeness**, never **shape**. Whether `revenue_yoy`
 * is a well-formed metric token is the domain's question, and a second copy of
 * that rule here would be a second chance to disagree with it — so an
 * ill-shaped token goes to the server and comes back with the domain's own
 * sentence, which is displayed as-is.
 *
 * ⭐⭐ **Membership is a third thing, and this round is about it** (spec 058).
 *
 * ⭐ **Shape** is the domain's to refuse. ⭐ **Membership** is the domain's to *know* —
 * `metrics.read_metric` has answered `UNKNOWN_METRIC` since before this file existed — ⭐
 * and ⭐ **nobody was asking.** Measured, before the vocabulary endpoint existed:
 *
 * ```
 *   this input's placeholder      gross_margin
 *   gross_margin in either catalogue   no  ⭐ the real one is gp_margin「销售毛利率」
 *   domain check                  [a-z][a-z0-9_]* — shape only
 *   POST /api/v1/decisions        201, stored verbatim
 *   anything said at write time   nothing
 * ```
 *
 * ⇒ A reader who followed **the product's own example** got a kill criterion that could
 * never be evaluated, and the only place that would have said so runs months later, when
 * the criterion comes due — where the sentence blames the data, and the data is fine.
 *
 * ⭐ **So the field now offers the vocabulary and says so when you leave it.** ⭐⭐ And it
 * is **not** a `<select>`, because `criterion_sentence` has a whole sentence state for
 * 「不在我们能算的指标里」 — ⭐⭐ replacing free text with a select would make that state
 * **unreachable from the interface**, which is deleting a capability rather than fixing a
 * defect. ⭐ An uncomputable metric is a **fact about the reader** (they care about gross
 * margin); that this build lacks it is a fact about the product. ⭐ Neither is a reason to
 * refuse the write, so the write is not refused.
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

/**
 * ⭐ The vocabulary for this market, or `null` while unknown.
 *
 * ⭐ **`null` means 「没问出来」 and renders nothing.** Not an error sentence: 「我无法列出
 * 我能算的指标」 is not something a reader should have to read because a request failed, ⭐
 * and the guarantee this screen offers is a prompt, not a refusal — ⭐ the write is
 * allowed either way, so there is nothing to warn about. ⭐ Same rule as `DemoBanner`.
 */
function useMetricCatalogue(market: string): MetricCatalogue | null {
  const [catalogue, setCatalogue] = useState<MetricCatalogue | null>(null)

  useEffect(() => {
    let live = true
    getMetrics(market)
      .then((answer) => {
        if (live) setCatalogue(answer)
      })
      .catch(() => {
        // See the docstring: silence is the honest rendering of 「did not find out」.
      })
    return () => {
      live = false
    }
  }, [market])

  return catalogue
}

/**
 * ⭐⭐ The sentence. One fact, no reassurance, no promise.
 *
 * ⭐ **It says 「我算不了」 and not 「你写错了」** ⭐ — because the reader did not get it
 * wrong; ⭐ this build simply does not have that metric, ⭐ and for gross margin it *does*
 * have one, under a different token. ⭐ Blaming the reader for the product's gap is the
 * tone red line 13 rules out.
 *
 * ⭐⭐ **And it promises nothing.** The first draft of this said 「它会一直在这儿等，等到
 * 我能算为止」 ⭐ — ⭐ **which is false**: ⭐ a token in neither catalogue is not something
 * this build is scheduled to acquire, ⭐ so 「等到我能算为止」 names an event with no date.
 * ⭐ That is reassurance (红线 13) *and* a promise the product cannot keep, ⭐ and it is the
 * same species as the bug this screen was fixed for: ⭐ **saying something kind instead of
 * something true.** ⇒ It states what *does* happen — the criterion is recorded, and the
 * existing `criterion_sentence` will name the reason when it comes due.
 *
 * ⭐ **It does not block the write.** Not a validation error, not a warning banner — ⭐ one
 * line under the field, and the button stays enabled.
 */
function UncomputableNotice({ token }: { token: string }) {
  return (
    <p
      className="mt-1 type-meta text-ink-soft"
      data-testid="metric-uncomputable"
      // ⭐ `role="status"` not `role="alert"`: this appears as the reader types and settles,
      // ⭐ and an alert announces itself on every keystroke that keeps it on screen.
      role="status"
    >
      <code className="type-prose">{token}</code> 我算不了。
      <span className="text-ink-faint">
        {' '}
        判据照样记下来；到期时它会照实说「不在我们能算的指标里」。
      </span>
    </p>
  )
}

/**
 * ⭐ What this market *can* compute — the one disclosure, shared by every row.
 *
 * ⭐ **Not inline per row.** A 32-item list under each of up to N criteria turns a form into
 * a wall, ⭐ and the reader only needs it once. ⭐ **Sorted by token server-side** ⭐ so no
 * ordering here can imply that one metric is more worth watching than another — ⭐ red line
 * 8, and the same reason `DecisionForm` gives its five actions identical weight.
 */
function ComputableList({ catalogue }: { catalogue: MetricCatalogue }) {
  if (catalogue.metrics.length === 0) {
    // ⭐ A `.BJ` instrument lands here, and it is the sentence that reader most needs:
    // ⭐ **nothing at all can be watched**, which is a fact about the data layer and not
    // ⭐ about anything they wrote. ⭐ Measured: `financial` and `daily` are both `pending`
    // ⭐ for `bj` — no provider declares them for that venue.
    return (
      <p className="mt-1 type-meta text-ink-soft" data-testid="metrics-empty">
        这个市场我还没有数据源，所以一个指标都算不了。
      </p>
    )
  }
  return (
    <details className="mt-1.5">
      <summary className="type-meta caps text-ink-faint">
        我能算的（{catalogue.metrics.length}）
      </summary>
      <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {catalogue.metrics.map((metric) => (
          <li key={metric.token} className="type-meta text-ink-soft">
            <span className="text-ink-faint">{metric.label}</span>{' '}
            <code className="type-prose">{metric.token}</code>
          </li>
        ))}
      </ul>
    </details>
  )
}

export default function DecisionForm({ market, code, onRecorded }: Props) {
  const [action, setAction] = useState<DecisionAction>('buy')
  const [rationale, setRationale] = useState('')
  const [counterEvidence, setCounterEvidence] = useState('')
  const [rows, setRows] = useState<CriterionRow[]>(() => [blankRow()])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ message: string; fix: string | null } | null>(null)

  const catalogue = useMetricCatalogue(market)
  const computable = new Set(catalogue?.metrics.map((metric) => metric.token) ?? [])

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
      <h3 className="type-meta font-normal caps text-ink-faint">
        记录一个决策
      </h3>
      <p className="mt-1 type-prose text-ink-faint">
        写下来之后不能改、不能删 —— 「改变想法」是再写一条。这三项都是必填，
        因为一条缺了反面证据的决策，事后会被记忆补全成它从来不是的样子。
      </p>

      <fieldset className="mt-2.5">
        <legend className="type-meta caps text-ink-faint">做了什么</legend>
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
        <span className="type-meta caps text-ink-faint">
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
        <span className="type-meta caps text-ink-faint">
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
          <span className="type-meta caps text-ink-faint">
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
              computable={computable}
              vocabularyKnown={catalogue !== null}
            />
          ))}
        </ol>

        {/* ⭐ One `<datalist>` for every criterion row. ⭐ `list` is a *reference*, so N rows
            share one list — ⭐ and a native `<datalist>` keeps free text writable, which a
            `<select>` would not (spec 058 §2.1). */}
        {catalogue !== null && (
          <datalist id={METRIC_DATALIST_ID}>
            {catalogue.metrics.map((metric) => (
              <option key={metric.token} value={metric.token}>
                {metric.label}
              </option>
            ))}
          </datalist>
        )}

        <p className="mt-1 type-prose text-ink-faint">
          写成四段而不是一句话，是为了让数据将来能<strong className="text-ink">自己来</strong>
          告诉你条件触发了。一句话没人能计算，也就永远不会来找你。
        </p>

        {/* ⭐ **One** disclosure for the whole form, not one per criterion — 32 labels inline
            under every row would turn a form into a wall. ⭐ And it appears only once the
            reader has actually written something this build cannot compute, ⭐ because a
            list nobody asked for is noise, ⭐ and this screen's whole problem was giving
            information in the wrong place at the wrong time. */}
        {catalogue !== null &&
          rows.some((row) => uncomputable(row.metric, computable, true)) && (
            <ComputableList catalogue={catalogue} />
          )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" disabled={blocked || busy}>
          {busy ? '写入中…' : '记下来'}
        </Button>
        <span className="type-meta text-ink-faint">
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
        <div className="mt-2 border-l-2 border-l-up py-1">
          <p className="type-prose text-up">{error.message}</p>
          {error.fix && <p className="type-prose text-ink-soft">{error.fix}</p>}
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
  computable,
  vocabularyKnown,
}: {
  row: CriterionRow
  index: number
  removable: boolean
  onChange: (patch: Partial<CriterionRow>) => void
  onRemove: () => void
  /** Tokens this market can compute. ⭐ Empty while the catalogue is unknown. */
  computable: Set<string>
  /** ⭐ `false` while the catalogue has not arrived — ⭐ and then nothing is accused. */
  vocabularyKnown: boolean
}) {
  const showNotice = uncomputable(row.metric, computable, vocabularyKnown)
  return (
    <li className="mt-1.5 border-l-2 border-l-rule py-1.5">
      <div className="flex flex-wrap items-end gap-x-2 gap-y-1.5">
        <label className="flex flex-col gap-1">
          <span className="type-meta caps text-ink-faint">
            指标 #{index + 1}
          </span>
          <Input
            value={row.metric}
            onChange={(event) => onChange({ metric: event.target.value })}
            // ⭐⭐ **`gp_margin`, not `gross_margin`.** ⭐ The first placeholder was
            // `gross_margin`, ⭐ which is in **neither** catalogue — ⭐ so the product's own
            // example produced a kill criterion this build can never evaluate, stored
            // verbatim by a domain that checks shape only, ⭐ with nothing said at write
            // time and a sentence months later that blames the data (spec 058).
            // ⭐ **Gross margin *is* computable. Its token is `gp_margin`.**
            placeholder="gp_margin"
            // ⭐ **A `<datalist>`, not a `<select>`.** Free text stays writable on purpose —
            // ⭐ `criterion_sentence` has a sentence state for a metric this build lacks,
            // ⭐ and a select would make it unreachable from the interface (spec 058 §2.1).
            list={METRIC_DATALIST_ID}
            className="num w-[132px]"
            spellCheck={false}
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="type-meta caps text-ink-faint">关系</span>
          {/* Native, for the same reason as the pool page's selects: a real
              listbox needs `aria-activedescendant` and focus management, and
              hand-rolling that badly is worse than looking slightly plain. */}
          <select
            value={row.operator}
            onChange={(event) => onChange({ operator: event.target.value as ComparisonOperator })}
            className="h-8 rounded-[2px] border border-rule bg-surface px-2 type-prose outline-none focus:border-navy"
 >
            {OPERATORS.map((operator) => (
              <option key={operator} value={operator}>
                {OPERATOR_LABEL[operator]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="type-meta caps text-ink-faint">阈值</span>
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
          <span className="type-meta caps text-ink-faint">
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

      {showNotice && <UncomputableNotice token={row.metric.trim()} />}

      {isComplete(row) && (
        <p className="mt-0.5 type-prose text-ink-soft">
          读作：截至 {row.asOf}，{row.metric.trim()} {OPERATOR_LABEL[row.operator]} {row.threshold}
        </p>
      )}
    </li>
  )
}
