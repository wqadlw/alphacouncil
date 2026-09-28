import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  addToWatchlist,
  getInstrument,
  getQuote,
  removeFromWatchlist,
  reviseReason,
  type DataStatus,
  type InstrumentDetail,
  type QuoteResult,
  type WatchlistEvent,
} from './api'
import {
  EVENT_LABEL,
  TONE_CLASS,
  formatAmount,
  formatChange,
  formatMoment,
  formatPrice,
  formatVolume,
} from './format'
import CardSection from './CardSection'
import DecisionSection from './DecisionSection'
import { Button, Skeleton, Textarea } from './components/ui'
import { useResource } from './useResource'

const FOLLOW_LABEL: Record<string, string> = {
  followed: '关注中',
  removed: '已不再关注',
  never: '尚未关注',
}

interface Props {
  market: string
  code: string
}

export default function InstrumentPage({ market, code }: Props) {
  /**
   * The record and the price, fetched separately and on purpose.
   *
   * The record is the floor — it is local and it is what the page is *for*. The
   * price crosses the network and may fail, and when it does the record stays on
   * screen with a sentence about the price. One request for both would let a
   * flaky quote hide a decision record, which is the one thing this page must
   * never do.
   */
  const record = useResource<InstrumentDetail>(
    useCallback(() => getInstrument(market, code), [market, code]),
    [market, code],
    useCallback(
      (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取这个标的。'),
      [],
    ),
  )
  const price = useResource<QuoteResult>(
    useCallback(() => getQuote(market, code), [market, code]),
    [market, code],
    useCallback(
      (cause: unknown) =>
        cause instanceof ApiError ? cause.message : '报价请求失败 —— 记录部分不受影响。',
      [],
    ),
  )

  const detail = record.data
  const loadError = record.error
  const quote = price.data
  const quoteError = price.error

  const [reasonDraft, setReasonDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<{ message: string; fix: string | null } | null>(
    null,
  )

  /**
   * The reason draft is seeded from the record once it arrives.
   *
   * ⭐ **This is the one `set-state-in-effect` warning left in the app, and it is
   * left deliberately** rather than silenced. The draft is a genuine second copy
   * of a value the record owns — the reader edits it, so it cannot simply be
   * derived — and the honest fix is to move the form into its own component keyed
   * on the loaded reason, so it initialises instead of syncing. That is a real
   * refactor of a five-hundred-line page and belongs on its own, not smuggled in
   * here.
   *
   * What would *not* be honest: deleting the warning without doing that, or
   * pretending the remaining cascade does not exist. The other six warnings this
   * file used to raise were genuine and are gone; this one is real and named.
   */
  useEffect(() => {
    if (record.data) setReasonDraft(record.data.follow.reason ?? '')
  }, [record.data])

  const refresh = record.reload

  // The price is fetched once, and never on a timer. A price that refreshes
  // itself turns a record into a terminal, and a terminal is what this product is
  // not: red line 11 forbids anything that nudges the reader to act more often.
  // `price.reload()` is a button, which requires a decision to look.

  const followed = detail?.follow.status === 'followed'
  const reasonMissing = reasonDraft.trim().length === 0

  async function run(action: () => Promise<string>) {
    setBusy(true)
    setNotice(null)
    setActionError(null)
    try {
      setNotice(await action())
      await refresh()
    } catch (error) {
      setActionError(
        error instanceof ApiError
          ? { message: error.message, fix: error.fix }
          : { message: '写入失败。', fix: null },
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (reasonMissing || busy) return
    const text = reasonDraft.trim()
    await run(async () => {
      const recorded = followed
        ? await reviseReason(code, text, market)
        : await addToWatchlist(code, text, market)
      return followed
        ? `已追加一条修改记录（事件 #${recorded.event_id}）—— 上一句理由仍留在日志里。`
        : `已记录（事件 #${recorded.event_id}）—— 理由已写入不可修改的日志。`
    })
  }

  async function handleRemove() {
    await run(async () => {
      const recorded = await removeFromWatchlist(code, market)
      return `已停止关注（事件 #${recorded.event_id}）—— 记录没有被删除，只是追加了一条「不再关注」。`
    })
  }

  return (
    <div className="pb-8">
      {/*
        The shell's header already carries `600519.SH` — it is
        `titleFor('instrument')` — so this page does not repeat it in a 26px
        serif. What the header cannot know is the *name* and whether the reader
        still follows it, so those go on one quiet line beneath it: the same
        information as before, at chrome size rather than headline size.
      */}
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-rule px-4 py-2.5 text-[12px] text-ink-faint">
        {detail ? (
          <>
            <span className="text-[15px] text-ink">{detail.name ?? '—'}</span>
            <span>{detail.asset_type}</span>
            <span className="text-ink-soft">
              · {FOLLOW_LABEL[detail.follow.status] ?? detail.follow.status}
            </span>
          </>
        ) : (
          <span>读取记录…</span>
        )}
      </p>

      <p className="px-4 py-2 text-[12px] text-ink-faint">
        这一页回答五个问题：
        <span className="text-ink-soft">
          {' '}
          现在是什么样 · 我为什么关注它 · 我对它说过什么 · 我对它做过什么 · 我对它下过什么判断
        </span>
      </p>

      {loadError && (
        <div className="mark border-l-2 border-l-[color:var(--color-up)] px-4 py-2">
          <p className="text-[13px] text-[color:var(--color-up)]">{loadError}</p>
          <p className="text-[12px] text-ink-soft">
            后端未启动时会出现这一行 —— 它不会静默显示成「空标的」。
          </p>
        </div>
      )}

      {detail && (
        <>
          <QuoteStrip quote={quote} error={quoteError} onRefresh={price.reload} />

          <Section
            title={followed ? '我为什么关注它' : '我当初为什么关注它'}
            aside={
              detail.follow.since ? (
                <span className="num text-[11px] text-ink-faint">
                  {followed ? '当前理由写于' : '最后一条写于'} {formatMoment(detail.follow.since)}
                </span>
              ) : null
            }
          >
            {detail.follow.reason ? (
              /* Serif at 16px: a quotation of what the reader wrote, so rule 1
                 applies squarely. It is the one block on this page that earns a
                 measure larger than the 13px body floor. */
              <blockquote className="mark border-l-2 border-l-[color:var(--color-brass)] py-1">
                <p className="serif text-[16px] leading-relaxed">{detail.follow.reason}</p>
              </blockquote>
            ) : (
              <p className="text-[13px] text-ink-soft">
                {detail.follow.status === 'never'
                  ? '你还没有关注这个标的，所以还没有理由。下面写一句，它会被记下来。'
                  : '当初离开时你没有留下说明 —— 那是允许的，离开不需要理由。'}
              </p>
            )}
          </Section>

          <Section
            title="我对它做过什么"
            aside={
              detail.history.length > 0 ? (
                <span className="num text-[11px] text-ink-faint">
                  {detail.follow.event_count} 条记录
                </span>
              ) : null
            }
          >
            {detail.history.length === 0 ? (
              <p className="text-[13px] text-ink-soft">
                没有任何记录。这个标的还不在你的关注池里。
              </p>
            ) : (
              <>
                <p className="text-[12px] text-ink-faint">
                  按写入顺序排列 —— 这是不可修改的记录，读下来是「加入 → 改口 → 离开 → 再来」的过程，
                  倒着排就只剩四条互不相干的行。
                </p>
                <ol className="mt-1.5">
                  {detail.history.map((event) => (
                    <TimelineRow key={event.event_id} event={event} />
                  ))}
                </ol>
              </>
            )}
          </Section>

          <section className="mt-4 border-t border-rule pt-4">
            <form onSubmit={handleSubmit}>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
                  {followed ? '改成什么（会追加一条记录，原句不会消失）' : '写下你为什么关注它'}{' '}
                  <span className="text-[color:var(--color-up)]">必填</span>
                </span>
                <Textarea
                  value={reasonDraft}
                  onChange={(event) => setReasonDraft(event.target.value)}
                  rows={2}
                  placeholder="例如：毛利率连续三年高于 90%，品牌定价权强；跟踪批价与渠道库存"
                />
              </label>

              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <Button type="submit" variant="primary" disabled={reasonMissing || busy}>
                  {busy ? '写入中…' : followed ? '追加修改记录' : '加入关注池'}
                </Button>
                {followed && (
                  <Button type="button" onClick={() => void handleRemove()} disabled={busy}>
                    不再关注
                  </Button>
                )}
                <span className="text-[12px] text-ink-faint">
                  {reasonMissing
                    ? '理由为空时按钮不可用 —— 这是唯一不能跳过的一步。'
                    : '理由进入只增不改的日志：无法编辑，只能追加。'}
                </span>
              </div>
            </form>

            {actionError && (
              <div className="mark mt-2.5 border-l-2 border-l-[color:var(--color-up)] py-1">
                <p className="text-[13px] text-[color:var(--color-up)]">{actionError.message}</p>
                {actionError.fix && <p className="text-[12px] text-ink-soft">{actionError.fix}</p>}
              </div>
            )}
            {notice && (
              <div className="mark mt-2.5 border-l-2 border-l-navy py-1">
                <p className="text-[13px] text-navy">{notice}</p>
              </div>
            )}
          </section>

          <CardSection
            market={market}
            code={code}
            cards={detail.cards}
            onRecorded={() => void refresh()}
          />

          <DecisionSection
            market={market}
            code={code}
            decisions={detail.decisions}
            onRecorded={() => void refresh()}
          />

          <NotBuiltYet />
        </>
      )}

      <footer className="mt-6 border-t border-rule px-4 pt-3 text-[12px] text-ink-faint">
        这一页显示的是事实：价格、时间、你自己写下的句子。
        <span className="text-ink-soft">
          {' '}
          它不显示收益率，不算你赚了多少，也不告诉你该不该买。
        </span>
      </footer>
    </div>
  )
}

/**
 * A section header: 11px chrome, a hairline, an optional quiet aside.
 *
 * ⭐ The headings stay **real heading elements**, only smaller. That is not a
 * downgrade — `instrument.spec.ts` finds them with
 * `getByRole('heading', { name: '我对它做过什么' })`, and more to the point a
 * section that is not a heading is invisible to someone navigating by region.
 * Shrinking the type is allowed; dropping the semantics is not.
 */
function Section({
  title,
  aside,
  children,
}: {
  title: string
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="mt-4">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="text-[11px] font-normal uppercase tracking-[0.06em] text-ink-faint">
          {title}
        </h2>
        {aside ? <span className="ml-auto">{aside}</span> : null}
      </div>
      <div className="border-b border-rule" />
      <div className="px-4 pt-2">{children}</div>
    </section>
  )
}

/**
 * The price panel — four states, four different sentences.
 *
 * This is the only part of the page that can fail, and the failure is not
 * hidden behind an em dash: `no_data` ("the source has nothing for this code")
 * and `error` ("every source we tried refused us") mean different things and
 * only one of them is worth retrying, so they get different copy. A `stale`
 * value is shown *with* its warning, never silently as today's.
 */
function QuoteStrip({
  quote,
  error,
  onRefresh,
}: {
  quote: QuoteResult | null
  error: string | null
  onRefresh: () => void
}) {
  return (
    <section className="mt-4">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="text-[11px] font-normal uppercase tracking-[0.06em] text-ink-faint">
          现在是什么样
        </h2>
        <Button size="sm" className="ml-auto" onClick={onRefresh}>
          重新读取
        </Button>
      </div>
      <div className="border-b border-rule" />

      <div className="px-4 pt-2">
        {error && (
          <div className="mark border-l-2 border-l-[color:var(--color-up)] py-1">
            <p className="text-[13px] text-[color:var(--color-up)]">{error}</p>
          </div>
        )}

        {!quote && !error && <Skeleton className="mt-1 w-32" />}

        {quote && <QuoteBody quote={quote} />}

        <p className="mt-1.5 text-[12px] text-ink-faint">
          价格不会自动刷新 —— 需要你按一次。这一页不是行情终端。
        </p>
      </div>
    </section>
  )
}

function QuoteBody({ quote }: { quote: QuoteResult }) {
  if (quote.status === 'ok' && quote.value) {
    const change = formatChange(quote.value.change_pct)
    return (
      <div className="mt-1">
        {/* 24px, not 28px: this is the largest number in the product, and rule 1
            is about *serif*, not about size. A quote in the same sans/mono as
            every other number on screen reads as a figure in a table row rather
            than as a headline, which is the correct register for it. */}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className={`num text-[24px] leading-none ${TONE_CLASS[change.tone]}`}>
            {formatPrice(quote.value.price)}
          </span>
          <span className={`num text-[15px] ${TONE_CLASS[change.tone]}`}>{change.text}</span>
          <span className="num text-[12px] text-ink-faint">
            昨收 {formatPrice(quote.value.prev_close)}
          </span>
        </div>

        <dl className="mt-2 grid grid-cols-2 gap-x-6 text-[13px] sm:grid-cols-4">
          <Field label="今开" value={formatPrice(quote.value.open)} />
          <Field label="最高" value={formatPrice(quote.value.high)} />
          <Field label="最低" value={formatPrice(quote.value.low)} />
          <Field label="成交量" value={formatVolume(quote.value.volume)} />
          <Field label="成交额" value={formatAmount(quote.value.amount)} />
        </dl>

        <p className="num mt-1.5 text-[12px] text-ink-faint">
          来源 {quote.source} · 数据时间 {formatMoment(quote.fetched_at)}
        </p>

        {quote.stale && (
          <div className="mark mt-2 border-l-2 border-l-[color:var(--color-warn)] py-1">
            <p className="text-[13px] text-[color:var(--color-warn)]">
              这个价格是旧的 —— 所有实时来源都没有应答，显示的是最后一次成功取到的值。
            </p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="mark mt-1 border-l-2 border-l-[color:var(--color-warn)] py-1">
      <p className="text-[13px] text-[color:var(--color-warn)]">{QUOTE_FAILURE[quote.status]}</p>
      {quote.reason && <p className="text-[12px] text-ink-soft">{quote.reason}</p>}
      {quote.error_code && (
        <p className="num text-[12px] text-ink-faint">
          {quote.error_code}
          {quote.detail ? ` · ${quote.detail}` : ''}
          {quote.source ? ` · 最后尝试的来源：${quote.source}` : ''}
        </p>
      )}
    </div>
  )
}

const QUOTE_FAILURE: Record<DataStatus, string> = {
  ok: '',
  no_data: '这个代码没有报价 —— 来源查到了这个标的，但它今天没有价格。',
  unavailable: '有报价，但无法核实它的单位口径，所以不显示 —— 显示一个来路不明的数字比不显示更糟。',
  error: '所有报价来源都没有应答。这不是「没有价格」，是「取不到价格」。',
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-[color:var(--color-rule-soft)] py-1">
      <dt className="text-[12px] text-ink-faint">{label}</dt>
      <dd className="num text-[13px]">{value}</dd>
    </div>
  )
}

function TimelineRow({ event }: { event: WatchlistEvent }) {
  const isRemoval = event.kind === 'removed'
  return (
    <li
      className={`mark border-b border-[color:var(--color-rule-soft)] py-1.5 ${
        isRemoval
          ? 'border-l-2 border-l-[color:var(--color-ink-faint)]'
          : 'border-l-2 border-l-navy'
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="text-[13px] text-ink">{EVENT_LABEL[event.kind] ?? event.kind}</span>
        <span className="num text-[12px] text-ink-faint">{formatMoment(event.occurred_at)}</span>
        <span className="num text-[12px] text-ink-faint">事件 #{event.event_id}</span>
        {event.supersedes_id !== null && (
          <span className="num text-[12px] text-ink-faint">取代 #{event.supersedes_id}</span>
        )}
      </div>
      {event.reason ? (
        <p className="mt-0.5 text-[13px] text-ink">{event.reason}</p>
      ) : (
        <p className="mt-0.5 text-[12px] text-ink-faint">（离开时没有留下说明）</p>
      )}
    </li>
  )
}

/**
 * What this page does not have, stated rather than left to look like an error.
 *
 * The product definition puts knowledge cards and the full decision loop on this
 * page, and neither exists in the backend yet. An empty section that looks like
 * a loading failure would be worse than saying so: the reader would assume a bug
 * instead of a gap, and would not know which one to report.
 *
 * This list is a moving target and is meant to be edited as features land — the
 * first version of it said decision recording did not exist, which stopped being
 * true when J1 shipped.
 */
function NotBuiltYet() {
  return (
    <section className="mt-4 border-t border-rule pt-4">
      <h2 className="px-4 pb-1.5 text-[11px] font-normal uppercase tracking-[0.06em] text-ink-faint">
        还没有的部分
      </h2>
      <div className="border-b border-rule" />
      <div className="px-4 pt-2">
        <p className="text-[13px] text-ink-soft">
          这一页最终要同时装下三层：<span className="text-ink">数据</span>、
          <span className="text-ink">知识卡片</span>、<span className="text-ink">决策记录</span>。
          三层里的<strong className="text-ink">记录</strong>都已经有了 ——
          卡片能记能查（K1），决策能记（J1）—— 决策的<strong className="text-ink">对质</strong>还没有。
        </p>
        <ul className="mt-1.5 text-[12px] text-ink-faint">
          <li className="mark border-l-2 border-l-[color:var(--color-rule)] py-1">
            卡片复习与淘汰（K2）—— 卡片只有「记」没有「复习」；「哪张卡可以淘汰」还要靠人眼。
          </li>
          <li className="mark border-l-2 border-l-[color:var(--color-rule)] py-1">
            持仓（D2）—— 没有成本与数量，所以上面那个止损计算器要你自己填亏损比例，
            而不是从持仓里读。
          </li>
          <li className="mark border-l-2 border-l-[color:var(--color-rule)] py-1">
            对质与四象限（J3）—— 决策质量与结果是两件事，把它们分开打分的界面还没有。
          </li>
          <li className="mark border-l-2 border-l-[color:var(--color-rule)] py-1">
            重复检测（J4）—— 「这句话你说过 3 次」还没有实现，因为「怎样算同一句话」还没定义。
          </li>
          <li className="mark border-l-2 border-l-[color:var(--color-rule)] py-1">
            教训转卡（J5）—— 教训还不能变成复习卡片，所以「不再重犯」暂时还不是日程。
          </li>
        </ul>
        <p className="mt-1.5 text-[12px] text-ink-faint">
          写在这里而不是留空白：一个看起来像加载失败的空白区，会让人以为是 bug 而不是缺口。
        </p>
      </div>
    </section>
  )
}
