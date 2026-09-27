import { useCallback, useEffect, useState } from 'react'
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
import { ACTION_LABEL, formatPredicate, todayLabel } from './format'
import { POOL_HREF, instrumentHref } from './routing'
import QuoteCell from './QuoteCell'

export default function TodayPage() {
  // Three independent requests, because they have three independent failure
  // modes: attention is local, prices cross the network, and the list is the
  // page's floor. One request for all three would let the flakiest decide
  // what the reader gets to see.
  const [today, setToday] = useState<Today | null>(null)
  const [todayError, setTodayError] = useState<string | null>(null)
  const [entries, setEntries] = useState<WatchlistEntry[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [quotes, setQuotes] = useState<PoolQuote[] | null>(null)
  const [quotesError, setQuotesError] = useState<string | null>(null)

  const refreshToday = useCallback(async () => {
    try {
      setTodayError(null)
      setToday(await getToday())
    } catch (error) {
      setTodayError(error instanceof ApiError ? error.message : '无法读取今日待办。')
    }
  }, [])

  const refreshList = useCallback(async () => {
    try {
      setListError(null)
      setEntries(await listWatchlist())
    } catch (error) {
      setListError(error instanceof ApiError ? error.message : '无法读取关注池。')
    }
  }, [])

  const refreshQuotes = useCallback(async () => {
    try {
      setQuotesError(null)
      setQuotes(await getWatchlistQuotes())
    } catch (error) {
      setQuotesError(error instanceof ApiError ? error.message : '行情未能读取。')
    }
  }, [])

  useEffect(() => {
    void refreshToday()
    void refreshList()
    void refreshQuotes()
  }, [refreshToday, refreshList, refreshQuotes])

  const quoteByKey = new Map(
    (quotes ?? []).map((row) => [`${row.market}:${row.code}`, row.quote]),
  )

  return (
    <div className="mx-auto max-w-[860px] px-8 py-10">
      <header className="border-b border-rule pb-5">
        <h1 className="serif text-[26px] leading-tight">今天 · {todayLabel(new Date())}</h1>
        <p className="mt-1 text-ink-soft">
          打开就能看到的东西：<span className="text-ink">到期的失效条件、你关注的标的、现价</span>。
          <span className="text-ink-faint"> 没有推荐，没有成绩单。</span>
        </p>
      </header>

      <SectionOne
        today={today}
        todayError={todayError}
        onRetry={() => void refreshToday()}
      />

      <SectionTwo
        entries={entries}
        listError={listError}
        quoteByKey={quoteByKey}
        quotesError={quotesError}
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
    </div>
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
