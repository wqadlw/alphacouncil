/**
 * The pool page — the reader's own list, and the first page migrated to the
 * application idiom (spec 025 §八 item 1).
 *
 * **What changed, and why it is the same page.** The content is untouched: the
 * same four states per row, the same mandatory reason, the same append-only
 * receipts, the same footer sentence. What changed is the *shape*:
 *
 * - **no page-level 26px heading and no "← 今日" link.** The frame already names
 *   the page and already offers four ways out. Both were answering questions the
 *   shell answers better, and the back link was a single point of failure — a
 *   reader on `#/retrospective` had exactly one way to leave.
 * - **the list is a `DataTable`, not a stack of 72px `<li>` rows.** Twenty
 *   instruments fit on one screen now; four did.
 * - **the form uses the shared `Input`/`Button`**, so focus rings, disabled
 *   colours and the 2px radii are the same objects everywhere rather than
 *   approximations of each other.
 * - **the explanation stays.** 「理由不是备注，是半年后你被追问时要面对的那句话。」
 *   is the page's reason to exist and it is not chrome — it is what stops the
 *   reason field from feeling optional. Density must not eat the argument.
 *
 * The app-idiom rules this file follows are in `docs/FRONTEND_STYLE_GUIDE.md`,
 * and `styleguide.test.ts` is what stops it drifting back.
 */

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
import { instrumentHref } from './routing'
import QuoteCell from './QuoteCell'
import { DataTable, type Column } from './components/data/DataTable'
import { Button, Input } from './components/ui'
import { useResource } from './useResource'

interface PoolRow {
  entry: WatchlistEntry
  quote: PoolQuote['quote'] | undefined
}

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

  const rows: PoolRow[] = entries.map((entry) => ({
    entry,
    quote: quoteByKey.get(`${entry.market}:${entry.code}`),
  }))

  /**
   * `navigable: false` on every column, and the row link is the ticker.
   *
   * `DataTable` makes the whole row clickable when `onRowClick` is given, which
   * here would be wrong twice over: the row contains a *destructive* button, so
   * a row-wide click target would put "不再关注" one mis-click from every price.
   * The ticker stays the only link, and it is where the record actually is.
   */
  const columns: Column<PoolRow>[] = [
    {
      key: 'code',
      header: '标的',
      width: '150px',
      sortValue: (row) => row.entry.code,
      render: (row) => (
        <a
          href={instrumentHref(row.entry.market, row.entry.code)}
          className="num text-ink no-underline hover:text-navy hover:underline"
        >
          {displayCode(row.entry.market, row.entry.code)}
        </a>
      ),
    },
    {
      key: 'name',
      header: '名称',
      width: '110px',
      sortValue: (row) => row.entry.name ?? '',
      render: (row) => <span className="text-ink">{row.entry.name}</span>,
    },
    {
      key: 'reason',
      header: '为什么关注',
      // No sort key: this is the reader's own prose, and ordering it by its
      // characters would produce an order that means nothing to them.
      render: (row) => <span className="text-ink-soft">{row.entry.reason}</span>,
    },
    {
      key: 'since',
      header: '加入',
      numeric: true,
      sortValue: (row) => row.entry.since,
      render: (row) => (
        <span className="text-[12px] text-ink-faint">
          {formatMoment(row.entry.since)}
          <span className="ml-1">#{row.entry.last_event_id}</span>
        </span>
      ),
    },
    {
      key: 'price',
      header: '现价',
      numeric: true,
      sortValue: (row) => {
        // Sorting by the displayed string would order `291.99` before `8.40`,
        // because the column is text. The underlying value is what the reader
        // means by "sort by price", so that is the key.
        const price = (row.quote as { value?: { price?: number } } | undefined)?.value?.price
        return price ?? -1
      },
      render: (row) => <QuoteCell result={row.quote} />,
    },
    {
      key: 'actions',
      header: '',
      width: '96px',
      render: (row) => {
        const code = displayCode(row.entry.market, row.entry.code)
        const busy = removing === code
        return (
          <Button
            size="sm"
            disabled={busy}
            onClick={() => void handleRemove(row.entry)}
          >
            {busy ? '处理中…' : '不再关注'}
          </Button>
        )
      },
    },
  ]

  return (
    <div className="pb-8">
      {/* The frame header says 关注池. This line is the page's argument, which
          the header cannot carry: a reader who has not yet written a reason
          needs to know why this field is not optional. */}
      <p className="border-b border-rule px-4 py-2.5 text-[13px] text-ink-soft">
        你关注什么，以及<span className="text-ink">你为什么关注它</span>。
        <span className="text-ink-faint">
          {' '}
          理由不是备注，是半年后你被追问时要面对的那句话。
        </span>
      </p>

      <form onSubmit={handleSubmit} className="border-b border-rule px-4 py-3">
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex w-[200px] flex-col gap-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
              标的代码
            </span>
            <Input
              value={ticker}
              onChange={(event) => setTicker(event.target.value)}
              placeholder="600519 / sh600519 / 600519.SH"
              className="num"
              autoComplete="off"
            />
          </label>

          <label className="flex min-w-[260px] flex-1 flex-col gap-1">
            <span className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
              关注理由 <span className="text-[color:var(--color-up)]">必填</span>
            </span>
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="例如：毛利率连续三年高于 90%，品牌定价权强"
            />
          </label>

          <Button type="submit" variant="primary" disabled={tickerMissing || reasonMissing || submitting}>
            {submitting ? '写入中…' : '加入关注池'}
          </Button>
        </div>

        <p className="mt-1.5 text-[12px] text-ink-faint">
          {reasonMissing
            ? '理由为空时按钮不可用 —— 这是唯一不能跳过的一步。'
            : '提交后理由会进入只增不改的事件日志：无法编辑，只能追加一条修改记录。'}
        </p>

        {formError ? (
          <div className="mark mt-2 border-l-2 border-l-[color:var(--color-up)] py-1">
            <p className="text-[color:var(--color-up)]">{formError.message}</p>
            {formError.fix ? <p className="text-[12px] text-ink-soft">{formError.fix}</p> : null}
          </div>
        ) : null}
        {notice ? (
          <div className="mark mt-2 border-l-2 border-l-navy py-1">
            <p className="text-navy">{notice}</p>
          </div>
        ) : null}
      </form>

      <section className="mt-4">
        <div className="flex items-baseline gap-2 px-4 pb-1.5">
          <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">关注中</h2>
          {/* A count of what is on screen, not a target to climb (red line 11). */}
          {entries.length > 0 ? (
            <span className="num text-[11px] text-ink-faint">{entries.length}</span>
          ) : null}
          <Button
            size="sm"
            className="ml-auto"
            onClick={() => void refreshQuotes()}
            disabled={refreshingQuotes || entries.length === 0}
          >
            {refreshingQuotes ? '读取中…' : '刷新行情'}
          </Button>
        </div>
        <div className="border-b border-rule" />

        {loading ? (
          <div className="px-4 py-3" data-testid="pool-loading">
            <p className="text-[13px] text-ink-faint">读取中…</p>
          </div>
        ) : null}

        {loadError ? (
          <div className="mark border-l-2 border-l-[color:var(--color-up)] px-4 py-2">
            <p className="text-[13px] text-[color:var(--color-up)]">{loadError}</p>
            <p className="text-[12px] text-ink-soft">
              后端未启动时会出现这一行 —— 它不会静默显示成「空」。
            </p>
          </div>
        ) : null}

        {quotesError ? (
          <div className="mark border-l-2 border-l-[color:var(--color-up)] px-4 py-2">
            <p className="text-[13px] text-[color:var(--color-up)]">{quotesError}</p>
            <p className="text-[12px] text-ink-soft">
              行情没能读取，但关注池本身不受影响 —— 记录与报价是两个请求。
            </p>
          </div>
        ) : null}

        {!loading && !loadError && entries.length === 0 ? (
          <p className="px-4 py-3 text-[13px] text-ink-soft">
            关注池是空的。你还没有关注任何标的 —— 上面加一个，并写下你为什么关注它。
          </p>
        ) : null}

        <DataTable<PoolRow>
          columns={columns}
          rows={rows}
          rowKey={(row) => `${row.entry.market}:${row.entry.code}`}
        />

        {!loading && entries.length > 0 ? (
          <p className="px-4 pt-2 text-[12px] text-ink-faint">
            点代码进标的页 —— 那里有你写下过的每一句话。
          </p>
        ) : null}
      </section>

      <footer className="mt-6 border-t border-rule px-4 pt-3 text-[12px] text-ink-faint">
        这一页只显示事实：你关注了什么、为什么、什么时候、现在什么价。
        <span className="text-ink-soft"> 它不显示收益率，也不给你推荐。</span>
        <br />
        行情是打开页面或点「刷新行情」时的一次快照，不自动刷新 —— 会自己跳动
        的价格把记录页变成盯盘终端。
      </footer>
    </div>
  )
}
