import { type FormEvent, useCallback, useEffect, useState } from 'react'
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
  displayCode,
  formatAmount,
  formatChange,
  formatMoment,
  formatPrice,
  formatVolume,
} from './format'
import { POOL_HREF } from './routing'
import CardSection from './CardSection'
import DecisionSection from './DecisionSection'

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
  const [detail, setDetail] = useState<InstrumentDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [quote, setQuote] = useState<QuoteResult | null>(null)
  const [quoteError, setQuoteError] = useState<string | null>(null)

  const [reasonDraft, setReasonDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<{ message: string; fix: string | null } | null>(
    null,
  )

  const refresh = useCallback(async () => {
    try {
      setLoadError(null)
      const loaded = await getInstrument(market, code)
      setDetail(loaded)
      setReasonDraft(loaded.follow.reason ?? '')
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : '无法读取这个标的。')
    }
  }, [market, code])

  const refreshQuote = useCallback(async () => {
    try {
      setQuoteError(null)
      setQuote(await getQuote(market, code))
    } catch (error) {
      setQuote(null)
      setQuoteError(
        error instanceof ApiError ? error.message : '报价请求失败 —— 记录部分不受影响。',
      )
    }
  }, [market, code])

  // Trips React's `set-state-in-effect` rule — same deliberate warning as on the
  // pool page, where the full reasoning is written down. Left visible for the
  // same reason: it is the signal that the data layer is due to move to
  // TanStack Query, not a bug to be silenced.
  useEffect(() => {
    void refresh()
  }, [refresh])

  // Fetched once, and never on a timer. A price that refreshes itself turns a
  // record into a terminal, and a terminal is what this product is not: red
  // line 11 forbids anything that nudges the reader to act more often. There is
  // a button instead, which requires a decision to look.
  useEffect(() => {
    void refreshQuote()
  }, [refreshQuote])

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

  const heading = displayCode(market, code)

  return (
    <div className="mx-auto max-w-[860px] px-8 py-10">
      <nav className="text-[12px]">
        <a href={POOL_HREF} className="text-navy no-underline hover:underline">
          ← 关注池
        </a>
      </nav>

      <header className="mt-4 border-b border-rule pb-5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="serif num text-[26px] leading-tight">{heading}</h1>
          {detail?.name && <span className="text-[17px] text-ink">{detail.name}</span>}
          {detail && <span className="text-[12px] text-ink-faint">{detail.asset_type}</span>}
          {detail && (
            <span className="text-[12px] text-ink-soft">
              · {FOLLOW_LABEL[detail.follow.status] ?? detail.follow.status}
            </span>
          )}
        </div>
        <p className="mt-1 text-ink-soft">
          这一页只回答五个问题：<span className="text-ink">现在是什么样</span>、
          <span className="text-ink">我为什么关注它</span>、
          <span className="text-ink">我对它说过什么</span>、
          <span className="text-ink">我对它做过什么</span>、
          <span className="text-ink">我对它下过什么判断</span>。
        </p>
      </header>

      {loadError && (
        <div className="mark mt-6 border-l-2 border-l-up py-1">
          <p className="text-up">{loadError}</p>
          <p className="text-[12px] text-ink-soft">
            后端未启动时会出现这一行 —— 它不会静默显示成「空标的」。
          </p>
        </div>
      )}

      {detail && (
        <>
          <QuoteStrip quote={quote} error={quoteError} onRefresh={() => void refreshQuote()} />

          <section className="mt-8">
            <div className="flex items-baseline justify-between border-b border-rule pb-2">
              <h2 className="serif text-[17px]">
                {followed ? '我为什么关注它' : '我当初为什么关注它'}
              </h2>
              {detail.follow.since && (
                <span className="num text-[12px] text-ink-faint">
                  {followed ? '当前理由写于' : '最后一条写于'} {formatMoment(detail.follow.since)}
                </span>
              )}
            </div>

            {detail.follow.reason ? (
              <blockquote className="mark mt-3 border-l-2 border-l-brass py-1">
                <p className="serif text-[16px] leading-relaxed">{detail.follow.reason}</p>
              </blockquote>
            ) : (
              <p className="mt-3 text-ink-soft">
                {detail.follow.status === 'never'
                  ? '你还没有关注这个标的，所以还没有理由。下面写一句，它会被记下来。'
                  : '当初离开时你没有留下说明 —— 那是允许的，离开不需要理由。'}
              </p>
            )}
          </section>

          <section className="mt-8">
            <div className="flex items-baseline justify-between border-b border-rule pb-2">
              <h2 className="serif text-[17px]">我对它做过什么</h2>
              <span className="num text-[12px] text-ink-faint">
                {detail.follow.event_count} 条记录
              </span>
            </div>

            {detail.history.length === 0 ? (
              <p className="mt-3 text-ink-soft">
                没有任何记录。这个标的还不在你的关注池里。
              </p>
            ) : (
              <>
                <p className="mt-3 text-[12px] text-ink-faint">
                  按写入顺序排列 —— 这是不可修改的记录，读下来是「加入 → 改口 → 离开 → 再来」的过程，
                  倒着排就只剩四条互不相干的行。
                </p>
                <ol className="mt-3">
                  {detail.history.map((event) => (
                    <TimelineRow key={event.event_id} event={event} />
                  ))}
                </ol>
              </>
            )}
          </section>

          <section className="mt-8 border-t border-rule pt-5">
            <form onSubmit={handleSubmit}>
              <label className="flex flex-col gap-1">
                <span className="text-[12px] text-ink-faint">
                  {followed ? '改成什么（会追加一条记录，原句不会消失）' : '写下你为什么关注它'}{' '}
                  <span className="text-up">必填</span>
                </span>
                <textarea
                  value={reasonDraft}
                  onChange={(event) => setReasonDraft(event.target.value)}
                  rows={2}
                  placeholder="例如：毛利率连续三年高于 90%，品牌定价权强；跟踪批价与渠道库存"
                />
              </label>

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button type="submit" disabled={reasonMissing || busy}>
                  {busy ? '写入中…' : followed ? '追加修改记录' : '加入关注池'}
                </button>
                {followed && (
                  <button type="button" onClick={() => void handleRemove()} disabled={busy}>
                    不再关注
                  </button>
                )}
                <span className="text-[12px] text-ink-faint">
                  {reasonMissing
                    ? '理由为空时按钮不可用 —— 这是唯一不能跳过的一步。'
                    : '理由进入只增不改的日志：无法编辑，只能追加。'}
                </span>
              </div>
            </form>

            {actionError && (
              <div className="mark mt-3 border-l-2 border-l-up py-1">
                <p className="text-up">{actionError.message}</p>
                {actionError.fix && <p className="text-[12px] text-ink-soft">{actionError.fix}</p>}
              </div>
            )}
            {notice && (
              <div className="mark mt-3 border-l-2 border-l-navy py-1">
                <p className="text-navy">{notice}</p>
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

      <footer className="mt-10 border-t border-rule pt-4 text-[12px] text-ink-faint">
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
    <section className="mt-6">
      <div className="flex items-baseline justify-between border-b border-rule pb-2">
        <h2 className="serif text-[17px]">现在是什么样</h2>
        <button type="button" onClick={onRefresh} className="text-[12px]">
          重新读取
        </button>
      </div>

      {error && (
        <div className="mark mt-3 border-l-2 border-l-up py-1">
          <p className="text-up">{error}</p>
        </div>
      )}

      {!quote && !error && <p className="mt-3 text-ink-faint">读取中…</p>}

      {quote && <QuoteBody quote={quote} />}

      <p className="mt-2 text-[12px] text-ink-faint">
        价格不会自动刷新 —— 需要你按一次。这一页不是行情终端。
      </p>
    </section>
  )
}

function QuoteBody({ quote }: { quote: QuoteResult }) {
  if (quote.status === 'ok' && quote.value) {
    const change = formatChange(quote.value.change_pct)
    return (
      <div className="mt-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className={`num text-[28px] leading-none ${TONE_CLASS[change.tone]}`}>
            {formatPrice(quote.value.price)}
          </span>
          <span className={`num text-[17px] ${TONE_CLASS[change.tone]}`}>{change.text}</span>
          <span className="num text-[12px] text-ink-faint">
            昨收 {formatPrice(quote.value.prev_close)}
          </span>
        </div>

        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] sm:grid-cols-4">
          <Field label="今开" value={formatPrice(quote.value.open)} />
          <Field label="最高" value={formatPrice(quote.value.high)} />
          <Field label="最低" value={formatPrice(quote.value.low)} />
          <Field label="成交量" value={formatVolume(quote.value.volume)} />
          <Field label="成交额" value={formatAmount(quote.value.amount)} />
        </dl>

        <p className="num mt-3 text-[12px] text-ink-faint">
          来源 {quote.source} · 数据时间 {formatMoment(quote.fetched_at)}
        </p>

        {quote.stale && (
          <div className="mark mt-3 border-l-2 border-l-warn py-1">
            <p className="text-warn">
              这个价格是旧的 —— 所有实时来源都没有应答，显示的是最后一次成功取到的值。
            </p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="mark mt-3 border-l-2 border-l-warn py-1">
      <p className="text-warn">{QUOTE_FAILURE[quote.status]}</p>
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
    <div className="flex justify-between gap-2 border-b border-b-rule py-1">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="num">{value}</dd>
    </div>
  )
}

function TimelineRow({ event }: { event: WatchlistEvent }) {
  const isRemoval = event.kind === 'removed'
  return (
    <li
      className={`mark border-t border-t-rule py-3 ${
        isRemoval ? 'border-l-2 border-l-ink-faint' : 'border-l-2 border-l-navy'
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
        <p className="mt-1 text-ink">{event.reason}</p>
      ) : (
        <p className="mt-1 text-[13px] text-ink-faint">（离开时没有留下说明）</p>
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
    <section className="mt-8 border-t border-rule pt-5">
      <h2 className="serif text-[17px]">还没有的部分</h2>
      <p className="mt-2 text-ink-soft">
        这一页最终要同时装下三层：<span className="text-ink">数据</span>、
        <span className="text-ink">知识卡片</span>、<span className="text-ink">决策记录</span>。
        三层里的<strong className="text-ink">记录</strong>都已经有了 ——
        卡片能记能查（K1），决策能记（J1）—— 决策的<strong className="text-ink">对质</strong>还没有。
      </p>
      <ul className="mt-2 text-[13px] text-ink-faint">
        <li className="mark border-l-2 border-l-rule py-1">
          卡片复习与淘汰（K2）—— 卡片只有「记」没有「复习」；「哪张卡可以淘汰」还要靠人眼。
        </li>
        <li className="mark border-l-2 border-l-rule py-1">
          持仓（D2）—— 没有成本与数量，所以上面那个止损计算器要你自己填亏损比例，
          而不是从持仓里读。
        </li>
        <li className="mark border-l-2 border-l-rule py-1">
          对质与四象限（J3）—— 决策质量与结果是两件事，把它们分开打分的界面还没有。
        </li>
        <li className="mark border-l-2 border-l-rule py-1">
          重复检测（J4）—— 「这句话你说过 3 次」还没有实现，因为「怎样算同一句话」还没定义。
        </li>
        <li className="mark border-l-2 border-l-rule py-1">
          教训转卡（J5）—— 教训还不能变成复习卡片，所以「不再重犯」暂时还不是日程。
        </li>
      </ul>
      <p className="mt-2 text-[12px] text-ink-faint">
        写在这里而不是留空白：一个看起来像加载失败的空白区，会让人以为是 bug 而不是缺口。
      </p>
    </section>
  )
}
