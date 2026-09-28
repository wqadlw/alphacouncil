import { useCallback } from 'react'
import {
  ApiError,
  getToday,
  getWatchlistQuotes,
  listWatchlist,
  type AttentionItem,
  type PoolQuote,
  type QuoteResult,
  type Today,
  type WatchlistEntry,
} from './api'
import { ACTION_LABEL, formatDay, formatPredicate, todayLabel } from './format'
import {
  POOL_HREF,
  instrumentHref,
  queueHref,
  type QueueName,
} from './routing'
import QuoteCell from './QuoteCell'
import { WidePage } from './ui'
import { useResource } from './useResource'

export default function TodayPage() {
  /**
   * Three independent requests, because they have three independent failure
   * modes: attention is local, prices cross the network, and the list is the
   * page's floor. One request for all three would let the flakiest decide what
   * the reader gets to see.
   *
   * Each is its own `useResource`, so one failing does not blank the other two —
   * and the reader sees a sentence about the part that failed while the rest of
   * the page stays true.
   */
  const today = useResource<Today>(
    getToday,
    [],
    useCallback((cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取今日待办。'), []),
  )
  const list = useResource<WatchlistEntry[]>(
    listWatchlist,
    [],
    useCallback((cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取关注池。'), []),
  )
  const prices = useResource<PoolQuote[]>(
    getWatchlistQuotes,
    [],
    useCallback((cause: unknown) => (cause instanceof ApiError ? cause.message : '行情未能读取。'), []),
  )

  const quotes = prices.data
  const entries = list.data ?? []
  const quoteByKey = new Map(
    (quotes ?? []).map((row) => [`${row.market}:${row.code}`, row.quote]),
  )

  return (
    <WidePage>
      <header className="border-b border-rule pb-5">
        <h1 className="serif text-[26px] leading-tight">今天 · {todayLabel(new Date())}</h1>
        {today.data?.market_status.verdict === 'non_trading_day' && (
          <p className="mark mt-2 border-l-2 border-l-navy py-1 text-[13px] text-navy">
            休市 · 最后交易日 {formatDay(today.data.market_status.last_trading_date)}
            <span className="text-ink-faint">
              {' '}
              —— 下列价格不会变化，这不是故障，也不是过期的数据。
            </span>
          </p>
        )}
        <p className="mt-2 text-ink-soft">
          打开就能看到的东西：<span className="text-ink">到期的失效条件、你关注的标的、现价</span>。
          <span className="text-ink-faint"> 没有推荐，没有成绩单。</span>
        </p>
      </header>

      <DueLine due={today.data?.due} />

      <SectionOne
        today={today.data}
        todayError={today.error}
        onRetry={today.reload}
      />

      <SectionTwo
        entries={entries}
        listError={list.error}
        quoteByKey={quoteByKey}
        quotesError={prices.error}
      />

      <section className="mt-8">
        <h2 className="serif text-[17px]">今天的数据变化</h2>
        <p className="mt-2 text-[13px] text-ink-soft">
          还没有的部分：公告与财务数据源尚未接入（D4 / D5）——
          所以今天的行情变化就在上面「我关注的」里，其余还没有东西可报。
        </p>
      </section>

      <section className="mt-8">
        <h2 className="serif text-[17px]">你在重复自己</h2>
        <p className="mt-2 text-[13px] text-ink-soft">
          还没有的部分：重复检测的判定算法尚未定义（J4）——
          这里以后会指出你对同一只票写下的同一句话。
        </p>
      </section>

      <footer className="mt-10 border-t border-rule pt-4 text-[12px] text-ink-faint">
        这一页只陈列事实，不陈列成绩：没有收益率、没有排行、没有打卡。
        <span className="text-ink-soft"> 它安静，是因为催促会让你动作变多。</span>
      </footer>
    </WidePage>
  )
}

/**
 * ⭐ The line that makes the product come and find the reader.
 *
 * `项目总纲` §2.1 says the 4th and 5th moments are ones the user will **not** come
 * for, so the product has to go to them — and this is that, in one sentence.
 *
 * The boundary it must not cross is narrow, and everything about the shape follows
 * from it: **a statement about something the reader already committed to**,
 * never **a suggestion about something they might want**. "2 条决策 · 3 张卡片" has
 * the reader as its subject and is a fact about their own calendar. "今天有 3 个
 * 机会" has the *product* as its subject and is a judgement about the market,
 * which is what red line 8 forbids.
 *
 * So, concretely, what is **not** here:
 *
 * - no badge, no red dot, no "new" tag, no count on the nav (red line 11 — the nav
 *   is already pinned digit-free by `nav.spec.ts`, and that is not an accident)
 * - no ordering, no "most overdue", no per-item list (a ranking the reader can
 *   feel; the detail belongs to the queue page, which is one click away)
 * - no "out of N", no completion fraction (ADR-0028 lists that as a thing the
 *   card page deliberately refuses)
 * - no escalation at a threshold — "11" must not become "很多" (a nudge wearing
 *   a number's clothes; `项目总纲` §2.1⑤ says 一句陈述, no 催促词)
 * - **nothing at all when both are zero** — "0 条决策到期" is still a sentence
 *   about the reader, and being told you owe yourself nothing is not worth a line
 * - ⭐ **no "three days overdue" threshold.** `项目总纲` ⑤ mentions three days,
 *   but nothing defines what would be said differently on day four, or how much
 *   louder. Inventing it is the same mistake as inventing a 90-day review
 *   interval (spec 020), and the failure mode is worse: "louder the longer you
 *   ignore it" *is* nagging, which is red line 11.
 */
function DueLine({ due }: { due: Today['due'] | undefined }) {
  if (!due) return null
  const parts: { queue: QueueName; count: number; label: string }[] = []
  if (due.reviews.count > 0) {
    parts.push({ queue: 'reviews', count: due.reviews.count, label: '条决策' })
  }
  if (due.cards.count > 0) {
    parts.push({ queue: 'cards', count: due.cards.count, label: '张卡片' })
  }
  if (parts.length === 0) return null

  return (
    <p className="mt-4 text-[13px] text-ink-soft" data-testid="today-due">
      到期要看的：
      {parts.map((part, index) => (
        <span key={part.queue}>
          {index > 0 ? ' · ' : ''}
          <a href={queueHref(part.queue)} className="text-navy" data-testid={`today-due-${part.queue}`}>
            {part.count} {part.label}
          </a>
        </span>
      ))}
    </p>
  )
}

interface SectionOneProps {
  today: Today | null
  todayError: string | null
  onRetry: () => void
}

function SectionOne({ today, todayError, onRetry }: SectionOneProps) {
  return (
    <section className="mt-6">
      <div className="flex items-baseline justify-between">
        <h2 className="serif text-[17px]">
          需要你处理的
          {today && today.attention.length > 0 && (
            <span className="num ml-2 text-[12px] text-ink-faint">
              {today.attention.length}
            </span>
          )}
        </h2>
        {todayError && (
          <button type="button" onClick={onRetry}>
            重试
          </button>
        )}
      </div>

      {todayError && (
        <div className="mark mt-3 border-l-2 border-l-up py-1">
          <p className="text-up">{todayError}</p>
          <p className="text-[12px] text-ink-soft">其余区块不受影响。</p>
        </div>
      )}

      {today && today.attention.length === 0 && (
        <p className="mt-2 text-[13px] text-ink-soft">
          今天没有到期的失效条件。你写下的每个条件都会在它该被看的那天出现在这里。
        </p>
      )}

      {today && today.attention.length > 0 && (
        <ul className="mt-3">
          {today.attention.map((entry) => (
            <AttentionRow key={`${entry.item.decision_id}-${entry.item.criterion.metric}`} entry={entry} />
          ))}
        </ul>
      )}
    </section>
  )
}

function AttentionRow({ entry }: { entry: AttentionItem }) {
  const { item } = entry
  const href = instrumentHref(item.market, item.code)
  return (
    <li className="mark border-t border-t-rule py-3 first:border-t-0">
      <p className="text-[13px]">
        <a href={href} className="num text-navy no-underline hover:underline">
          {item.display}
        </a>
        <span className="ml-2 text-ink">{ACTION_LABEL[item.action] ?? item.action}</span>
        <span className="ml-2 text-ink-faint">· 决策 #{item.decision_id.slice(0, 10)}</span>
      </p>
      <p className="mt-1 text-ink">
        你写的失效条件「{formatPredicate(item.criterion)}」观察期已到 —— 去核实数据。
      </p>
      <p className="mt-1 text-[12px] text-ink-faint">
        到期不等于触发：系统还没有指标数据源，能不能成立要你自己看一眼。
      </p>
    </li>
  )
}

interface SectionTwoProps {
  entries: WatchlistEntry[]
  listError: string | null
  quoteByKey: Map<string, QuoteResult>
  quotesError: string | null
}

function SectionTwo({ entries, listError, quoteByKey, quotesError }: SectionTwoProps) {
  return (
    <section className="mt-8">
      <div className="flex items-baseline justify-between">
        <h2 className="serif text-[17px]">我关注的</h2>
        <div className="flex items-baseline gap-3">
          <span className="num text-[12px] text-ink-faint">{entries.length} 个标的</span>
          <a href={POOL_HREF} className="text-[12px] text-navy no-underline hover:underline">
            管理关注池 →
          </a>
        </div>
      </div>

      {listError && (
        <div className="mark mt-3 border-l-2 border-l-up py-1">
          <p className="text-up">{listError}</p>
        </div>
      )}

      {!listError && entries.length === 0 && (
        <p className="mt-2 text-[13px] text-ink-soft">
          关注池是空的 —— 到
          <a href={POOL_HREF} className="text-navy">
            关注池
          </a>
          加一个，并写下你为什么关注它。
        </p>
      )}

      {quotesError && (
        <p className="mt-2 text-[12px] text-warn">
          行情没能读取（{quotesError}）—— 名单和理由不受影响。
        </p>
      )}

      <ul className="mt-3">
        {entries.map((entry) => {
          const key = `${entry.market}:${entry.code}`
          return (
            <li
              key={key}
              className="flex items-start justify-between gap-4 border-t border-t-rule py-3 first:border-t-0"
            >
              <div className="min-w-0">
                <p>
                  <a
                    href={instrumentHref(entry.market, entry.code)}
                    className="num text-[15px] text-navy no-underline hover:underline"
                  >
                    {entry.code}
                  </a>
                  {entry.name && <span className="ml-2 text-ink">{entry.name}</span>}
                </p>
                <p className="mt-1 text-[13px] text-ink-soft">{entry.reason}</p>
              </div>
              <QuoteCell result={quoteByKey.get(key)} />
            </li>
          )
        })}
      </ul>
    </section>
  )
}
