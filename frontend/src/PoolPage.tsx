import { type FormEvent, useCallback, useState } from 'react'
import {
  ApiError,
  addToWatchlist,
  getWatchlistQuotes,
  listWatchlist,
  removeFromWatchlist,
  type PoolQuote,
  type WatchlistEntry,
} from './api'
import { displayCode, formatMoment } from './format'
import { TODAY_HREF, instrumentHref } from './routing'
import QuoteCell from './QuoteCell'
import { useResource } from './useResource'

export default function PoolPage() {
  /**
   * Two requests, kept apart on purpose: the list is the page's floor and is
   * local, the prices cross the network. A failure to price must not blank the
   * list — that split is the whole reason a reader can still act during an
   * outage.
   */
  const list = useResource<WatchlistEntry[]>(
    listWatchlist,
    [],
    useCallback(
      (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取关注池。'),
      [],
    ),
  )
  const prices = useResource<PoolQuote[]>(
    getWatchlistQuotes,
    [],
    useCallback(
      (cause: unknown) => (cause instanceof ApiError ? cause.message : '行情未能读取。'),
      [],
    ),
  )

  const entries = list.data ?? []
  const loading = list.loading
  const loadError = list.error
  // `null` means "not here yet" — the list renders without it, because the
  // record never waits on the network.
  const quotes = prices.data
  const quotesError = prices.error
  const refreshingQuotes = prices.loading

  const [ticker, setTicker] = useState('')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<{ message: string; fix: string | null } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)

  const refresh = list.reload
  const refreshQuotes = prices.reload

  const tickerMissing = ticker.trim().length === 0
  const reasonMissing = reason.trim().length === 0

  // Keyed by the composite (market, code) — a bare code is not an instrument.
  const quoteByKey = new Map(
    (quotes ?? []).map((row) => [`${row.market}:${row.code}`, row.quote]),
  )

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (tickerMissing || reasonMissing || submitting) return

    setSubmitting(true)
    setFormError(null)
    setNotice(null)
    try {
      const recorded = await addToWatchlist(ticker.trim(), reason.trim())
      setNotice(`已记录（事件 #${recorded.event_id}）—— 理由已写入不可修改的日志。`)
      setTicker('')
      setReason('')
      await refresh()
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? { message: error.message, fix: error.fix }
          : { message: '写入失败。', fix: null },
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(entry: WatchlistEntry) {
    const code = displayCode(entry.market, entry.code)
    setRemoving(code)
    setFormError(null)
    setNotice(null)
    try {
      await removeFromWatchlist(entry.code, entry.market)
      setNotice(`已停止关注 ${code}。记录没有被删除 —— 只是追加了一条「不再关注」。`)
      await refresh()
    } catch (error) {
      setFormError({
        message: error instanceof ApiError ? error.message : '移除失败。',
        fix: error instanceof ApiError ? error.fix : null,
      })
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="mx-auto max-w-[860px] px-8 py-10">
      <header className="border-b border-rule pb-5">
        <p className="text-[12px] text-ink-faint">
          <a href={TODAY_HREF} className="text-navy no-underline hover:underline">
            ← 今日
          </a>
        </p>
        <h1 className="serif mt-2 text-[26px] leading-tight">关注池</h1>
        <p className="mt-1 text-ink-soft">
          你关注什么，以及<span className="text-ink">你为什么关注它</span>。
          <span className="text-ink-faint"> 理由不是备注，是半年后你被追问时要面对的那句话。</span>
        </p>
      </header>

      <form onSubmit={handleSubmit} className="mt-6 border-b border-rule pb-6">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-ink-faint">标的代码</span>
            <input
              value={ticker}
              onChange={(event) => setTicker(event.target.value)}
              placeholder="600519 / sh600519 / 600519.SH"
              className="num w-[220px]"
              autoComplete="off"
            />
          </label>

          <label className="flex min-w-[260px] flex-1 flex-col gap-1">
            <span className="text-[12px] text-ink-faint">
              关注理由 <span className="text-up">必填</span>
            </span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="例如：毛利率连续三年高于 90%，品牌定价权强"
            />
          </label>

          <button type="submit" disabled={tickerMissing || reasonMissing || submitting}>
            {submitting ? '写入中…' : '加入关注池'}
          </button>
        </div>

        <p className="mt-2 text-[12px] text-ink-faint">
          {reasonMissing
            ? '理由为空时按钮不可用 —— 这是唯一不能跳过的一步。'
            : '提交后理由会进入只增不改的事件日志：无法编辑，只能追加一条修改记录。'}
        </p>

        {formError && (
          <div className="mark mt-3 border-l-2 border-l-up py-1">
            <p className="text-up">{formError.message}</p>
            {formError.fix && <p className="text-[12px] text-ink-soft">{formError.fix}</p>}
          </div>
        )}
        {notice && (
          <div className="mark mt-3 border-l-2 border-l-navy py-1">
            <p className="text-navy">{notice}</p>
          </div>
        )}
      </form>

      <section className="mt-6">
        <div className="flex items-baseline justify-between">
          <h2 className="serif text-[17px]">关注中</h2>
          <div className="flex items-baseline gap-3">
            <span className="num text-[12px] text-ink-faint">{entries.length} 个标的</span>
            <button
              type="button"
              onClick={() => void refreshQuotes()}
              disabled={refreshingQuotes || entries.length === 0}
            >
              {refreshingQuotes ? '读取中…' : '刷新行情'}
            </button>
          </div>
        </div>

        {loading && <p className="mt-4 text-ink-faint">读取中…</p>}

        {loadError && (
          <div className="mark mt-4 border-l-2 border-l-up py-1">
            <p className="text-up">{loadError}</p>
            <p className="text-[12px] text-ink-soft">
              后端未启动时会出现这一行 —— 它不会静默显示成「空」。
            </p>
          </div>
        )}

        {quotesError && (
          <div className="mark mt-4 border-l-2 border-l-up py-1">
            <p className="text-up">{quotesError}</p>
            <p className="text-[12px] text-ink-soft">
              行情没能读取，但关注池本身不受影响 —— 记录与报价是两个请求。
            </p>
          </div>
        )}

        {!loading && !loadError && entries.length === 0 && (
          <p className="mt-4 text-ink-soft">
            关注池是空的。你还没有关注任何标的 —— 上面加一个，并写下你为什么关注它。
          </p>
        )}

        <ul className="mt-3">
          {entries.map((entry) => {
            const code = displayCode(entry.market, entry.code)
            return (
              <li
                key={code}
                className="mark flex items-start justify-between gap-4 border-t border-t-rule py-3"
              >
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <a
                      href={instrumentHref(entry.market, entry.code)}
                      className="num text-[15px] text-navy no-underline hover:underline"
                    >
                      {code}
                    </a>
                    {entry.name && <span className="text-ink">{entry.name}</span>}
                    <span className="text-[12px] text-ink-faint">{entry.asset_type}</span>
                  </div>
                  <p className="mt-1 text-ink">{entry.reason}</p>
                  <p className="num mt-1 text-[12px] text-ink-faint">
                    {formatMoment(entry.since)} 加入 · 最新事件 #{entry.last_event_id}
                  </p>
                </div>
                <QuoteCell result={quoteByKey.get(`${entry.market}:${entry.code}`)} />
                <button
                  type="button"
                  onClick={() => void handleRemove(entry)}
                  disabled={removing === code}
                >
                  {removing === code ? '处理中…' : '不再关注'}
                </button>
              </li>
            )
          })}
        </ul>

        {!loading && entries.length > 0 && (
          <p className="mt-3 text-[12px] text-ink-faint">
            点代码进标的页 —— 那里有你写下过的每一句话。
          </p>
        )}
      </section>

      <footer className="mt-10 border-t border-rule pt-4 text-[12px] text-ink-faint">
        这一页只显示事实：你关注了什么、为什么、什么时候、现在什么价。
        <span className="text-ink-soft"> 它不显示收益率，也不给你推荐。</span>
        <br />
        行情是打开页面或点「刷新行情」时的一次快照，不自动刷新 —— 会自己跳动
        的价格把记录页变成盯盘终端。
      </footer>
    </div>
  )
}
