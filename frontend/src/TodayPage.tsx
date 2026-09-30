/**
 * The today page — the front door, and the densest screen in the product.
 *
 * **The idiom changed in spec 025, and the reason is worth stating.** This page
 * used to be a 26px serif heading over a stack of large cards with 32px padding:
 * the layout of a *document*. A knowledge program is not a document — it is
 * "see many, pick one, read it" — so the content now obeys the same rules as the
 * frame around it:
 *
 * - **no page-sized heading.** The frame's header already says where you are; a
 *   second 26px title restating it is decoration (rule 7).
 * - **rows, not cards.** The due criteria are 40px rows with a 2px left rule, so
 *   twenty of them fit on one screen. As cards, four did.
 * - **13px body, 11px for chrome** (guide §2.2). The old page ran 12px for
 *   everything, which is table-chrome size used for prose.
 * - **serif only for the reader's own words** (rule 1) — the rationale and the
 *   counter-evidence, because those are quotations of what they wrote, not
 *   interface text.
 *
 * The three sections that say "this is not built yet" stay. They are the honest
 * answer to "what does this page do", and deleting them to look finished would be
 * the exact failure this product's own red lines exist to prevent.
 */

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
import {
  ACTION_LABEL,
  displayCode,
  formatDay,
  formatMoment,
  formatPredicate,
} from './format'
import { POOL_HREF, instrumentHref, queueHref, type QueueName } from './routing'
import { criterionPresentation } from './criterionVerdict'
import QuoteCell from './QuoteCell'
import { Badge, Rule } from './components/ui'
import { DataTable, type Column } from './components/data/DataTable'
import { useResource } from './useResource'

export default function TodayPage() {
  /**
   * Three independent requests, because they have three independent failure
   * modes: attention is local, prices cross the network, and the list is the
   * page's floor. One request for all three would let the flakiest decide what
   * the reader gets to see.
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

  const entries = list.data ?? []
  const quoteByKey = new Map(
    (prices.data ?? []).map((row) => [`${row.market}:${row.code}`, row.quote]),
  )

  return (
    <div className="pb-8">
      {/* The frame's header carries the date and title. This line only carries
          what the frame cannot know: whether the market is open, and why the
          prices below will therefore not move. */}
      {today.data?.market_status.verdict === 'non_trading_day' ? (
        <p className="border-b border-rule bg-paper-soft px-4 py-2 type-prose text-ink-soft">
          休市 · 最后交易日 {formatDay(today.data.market_status.last_trading_date)}
          <span className="text-ink-faint"> —— 下列价格不会变化，这不是故障，也不是过期的数据。</span>
        </p>
      ) : null}

      <DueLine due={today.data?.due} />

      <Section
        title="需要你处理的"
        count={today.data?.attention.length ?? 0}
        note="观察期已到不代表判据成立；成立不成立、以及我们能不能算，看下面每一行自己怎么说。"
 >
        {/*
          Rule 8: an empty state is a statement of fact plus what it means, and
          this one keeps the promise the reader is owed. 「今天没有到期的失效条件」
          says what is true; 「你写下的每个条件都会在它该被看的那天出现在这里」
          says why the page being empty is not the same as your conditions having
          been deleted. The second half is the part worth writing down — without
          it an empty page reads as data loss.

          ⭐ **The section note used to lie.** It read 「到期不等于触发：系统还没有指标
          数据源」 — and that stopped being true when spec 034 gave the endpoint an HTTP
          exit, spec 037 computed the indicators and spec 038 drew them. ⭐ A false
          sentence about our own debt is worse than no sentence: it told the reader the
          gap was a missing dependency rather than a missing function, and it was ours.
          The replacement says the true thing — the date arriving is not the comparison,
          and the row below is which one you are looking at.
        */}
        {today.data && today.data.attention.length === 0 ? (
          <p className="px-4 py-2 type-prose text-ink-soft">
            今天没有到期的失效条件。你写下的每个条件都会在它该被看的那天出现在这里。
          </p>
        ) : null}
        {(today.data?.attention ?? []).map((item, index) => (
          <AttentionRow key={`${item.item.decision_id}-${item.item.criterion.metric}-${index}`} item={item} />
        ))}
      </Section>

      <Section
        title="我关注的"
        count={entries.length}
        action={{ href: POOL_HREF, label: '管理关注池' }}
 >
        <DataTable<PoolRow>
          dense
          columns={poolColumns()}
          rows={entries.map((entry) => ({ entry, quote: quoteByKey.get(`${entry.market}:${entry.code}`) ?? null }))}
          rowKey={(row) => `${row.entry.market}:${row.entry.code}`}
          empty={
            <p className="px-4 py-3 type-prose text-ink-soft">
              关注池是空的 —— 到关注池加一个，并写下你为什么关注它。
            </p>
          }
        />
      </Section>

      <Section title="今天的数据变化">
        <p className="px-4 py-2 type-prose text-ink-soft">
          公告与财务数据源尚未接入（D4 / D5）—— 所以今天的价格变化就在上面「我关注的」里。
        </p>
      </Section>

      <Section title="你在重复自己">
        <p className="px-4 py-2 type-prose text-ink-soft">
          重复检测的判定算法尚未定义（J4）—— 这里以后会指出你对同一只票写下的同一句话。
        </p>
      </Section>

      <footer className="mt-6 border-t border-rule px-4 pt-3 type-meta text-ink-faint">
        这一页只陈列事实，不陈列成绩：没有收益率、没有排行、没有打卡。
        <span className="text-ink-soft"> 它安静，是因为催促会让你动作变多。</span>
      </footer>
    </div>
  )
}

/**
 * A section header with a hairline under it.
 *
 * `count` is rendered in `ink-faint` and only when non-zero. ⭐ It is a **fact
 * about what is on screen**, not a nag: the reader is already looking at the rows
 * that produced it, so it saves counting rather than pushing them to act
 * (red line 11). No badge, no red dot — and specifically nothing on the nav.
 */
function Section({
  title,
  count,
  note,
  action,
  children,
}: {
  title: string
  count?: number
  note?: string
  action?: { href: string; label: string }
  children: React.ReactNode
}) {
  return (
    <section className="mt-4">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">{title}</h2>
        {count !== undefined && count > 0 ? (
          <span className="num type-badge text-ink-faint">{count}</span>
        ) : null}
        {action ? (
          // ⭐ `data-[motion=l1]` — see the A5 note in `globals.css`:
          // `text-decoration-color` is what makes an underline fade, and this is
          // the shape this product uses for every link it can afford a border on.
          //
          // ⭐ A **JS** comment, not a JSX one, for the reason that has now bitten
          // twice in this migration: the `(` after `?` puts the parser in an
          // expression position, where a brace opens an object literal — so a
          // brace-comment becomes an empty `{}` followed by a JSX element, which is
          // a syntax error. The other one was a comment that quoted its own closing
          // delimiter and ended itself mid-sentence.
          <a href={action.href} className="ml-auto type-badge text-navy hover:underline data-[motion=l1]">
            {action.label} →
          </a>
        ) : null}
      </div>
      <Rule />
      {note ? <p className="px-4 pt-2 type-prose text-ink-faint">{note}</p> : null}
      {children}
    </section>
  )
}

/** One due criterion, as a row rather than a card. */
function AttentionRow({ item }: { item: AttentionItem }) {
  const { decision_id: decisionId, display, action, criterion } = item.item
  const sentence = criterionPresentation(item)
  return (
    <a
      href={instrumentHref(item.item.market, item.item.code)}
      className="block border-b border-[color:var(--color-rule-soft)] border-l-2 border-l-transparent px-4 py-2 no-underline data-[motion=l1] hover:border-l-[color:var(--color-brass)] hover:bg-paper-soft"
      data-testid="attention-row"
      data-crossed={sentence.crossed ? 'true' : 'false'}
      data-adjudicable={sentence.adjudicable ? 'true' : 'false'}
 >
      <div className="flex items-baseline gap-2">
        <span className="num type-meta text-ink">{display}</span>
        <Badge tone="neutral">{ACTION_LABEL[action]}</Badge>
        <span className="type-meta text-ink-faint">· 决策 {formatMoment(decisionId)}</span>
      </div>
      {/* ⭐ One sentence, five states, and the state is carried by the clause.

          Still one clause and still one element: the first draft split it into a
          criterion fragment and a right-aligned link, which read tidier and broke two
          things. `today.spec.ts` asserted both parts on the same sentence, and
          Playwright's strict mode rejects a `getByText` resolving to two elements, so
          the split made a passing assertion fail on its own success.

          ⭐ But the reason for the split mattered more than the split. As fragments it
          read as a status plus a link — a weaker claim than the sentence makes, and the
          weaker claim is the one that would let a reader think the criterion had already
          been adjudicated. ⭐ Since spec 040 it **has** been adjudicated, so the
          assertion that forbade 「已触发」 went away with the fact that forbade it.

          ⭐ The accent marks only `crossed`, and it is `--color-warn` — ⭐ **not
          `--color-up`**, which the first draft used. That token means 「涨」 on every
          chart in this product, and a crossed kill criterion is the opposite news. ⭐
          Reusing it would make 「your own criterion failed」 render in the colour the
          reader has been trained to read as 「up」, and the two would fight on the same
          screen. The three 「we don't know」 states keep the neutral treatment, because a
          louder rendering of 「we could not check」 would be the page presenting its own
          gap as news about the reader's decision. */}
      {/* The largest sentence in the product, and it was .type-prose until the
          A6 pass. It is the whole point of spec 040 - the one line the reader
          wrote themselves and then has to adjudicate against - and the
          guide's card / claim / quadrant-verdict row is 17-20 serif. At 13px
          sans it rendered as another field of a table row.

          serif is deliberate, and it took two readings. The clause carrying the
          state is the product's finding, not the reader's words, and the guide
          puts serif on titles and claims. But the sentence IS the reader's claim
          about their own position: the criterion in the quotes is theirs, and
          what follows is the answer to it. The ruling: the sentence takes the
          claim's size, and serif is what marks a claim in this product - the
          same treatment CardSection's own sentence gets, because that is the
          same kind of thing.

          And the accent colour now applies to a whole claim, which is new:
          the sentence goes --color-warn when crossed, not just the clause. That
          is a change in what the reader sees and it is intentional - a crossed
          kill criterion is the loudest thing this product can say about a
          position, and half-emphasising it would say it quietly. --color-warn,
          never --color-up: that token means up on every chart here, and reusing
          it would render your-own-criterion-failed in the colour the reader
          reads as up. */}
      <div
        className={`serif type-claim mt-0.5 ${sentence.crossed ? 'text-[color:var(--color-warn)]' : 'text-ink'}`}
 >
        你写的失效条件「{formatPredicate(criterion)}」{sentence.verdict}
      </div>
    </a>
  )
}

/**
 * The one line that makes the product come and find the reader.
 *
 * `项目总纲` §2.1 says the 4th and 5th moments are ones the user will **not** come
 * for, so the product has to go to them — and this is that, in one sentence.
 *
 * The boundary it must not cross is narrow, and everything about the shape
 * follows: **a statement about something the reader already committed to**, never
 * **a suggestion about something they might want**. "2 条决策 · 3 张卡片" has the
 * reader as its subject; "今天有 3 个机会" has the *product* as its subject and is
 * a judgement about the market, which is what red line 8 forbids.
 *
 * So there is no badge, no red dot, no ordering, no "most overdue", no
 * "out of N", and **no escalation at a threshold** — eleven and one render through
 * the same sentence, because "louder the longer you ignore it" is nagging
 * (red line 11).
 *
 * ⭐ And **no three-day overdue threshold.** `项目总纲` §2.1⑤ mentions three days,
 * but nothing defines what would be said differently on day four. Inventing it is
 * the same mistake as inventing a 90-day review interval (spec 020), and the
 * failure mode is worse — that policy *is* the nagging.
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
    <p className="border-b border-rule px-4 py-2 type-prose text-ink-soft" data-testid="today-due">
      到期要看的：
      {parts.map((part, index) => (
        <span key={part.queue}>
          {index > 0 ? ' · ' : ''}
          {/* ⭐ `data-[motion=l1]`, and this is the A5 pass: eleven of the
              fourteen `hover:` sites in this product are a `hover:underline` on a
              text link. ⭐ **A colour-only transition cannot help there** — the
              underline appears instantly, so the text either jumps to underlined or
              the underline fades in while the colour eases, and the two read as two
              different things. Putting these on L1 means the underline is the thing
              that moves, which is the whole of §7.1's 「hover 底色 / focus 环 / 按下」
              applied to the shape this product actually uses for its links. */}
          <a
            href={queueHref(part.queue)}
            className="text-navy hover:underline data-[motion=l1]"
            data-testid={`today-due-${part.queue}`}
          >
            {part.count} {part.label}
          </a>
        </span>
      ))}
    </p>
  )
}

interface PoolRow {
  entry: WatchlistEntry
  quote: QuoteResult | null
}

function poolColumns(): Column<PoolRow>[] {
  return [
    {
      key: 'display',
      header: '标的',
      width: '32%',
      sortValue: (row) => row.entry.code,
      // ⭐ No `data-[motion=l1]` on this link, and that is deliberate. The `<tr>`
      // already carries it and the cell **inherits** the transition — and a
      // transition is inherited, so `text-decoration-color` is covered either way.
      // ⭐ Marking every link would be one class written eleven times for a single
      // effect: the row is the thing being hovered, so the row owns the motion.
      render: (row) => (
        <a
          href={instrumentHref(row.entry.market, row.entry.code)}
          className="text-ink no-underline hover:text-navy hover:underline"
 >
          {/* ⭐ `displayCode`, not the bare code, and this is a consistency fix
              rather than a prettiness one: the attention rows above already show
              `600519.SH` because the server hands them a `display` field, so a
              table reading `300750` beside rows reading `600519.SH` had the same
              instrument written two ways on one screen. `parse_ticker` refuses an
              ambiguous code rather than guessing the market, so the market suffix
              is not decoration — it is what makes the code unambiguous.

              `name` is the exchange's name and may be null; the code never is, so
              the code leads and the name is a quiet suffix. */}
          <span className="num">{displayCode(row.entry.market, row.entry.code)}</span>
          {row.entry.name ? (
            <span className="ml-1.5 text-ink-soft">{row.entry.name}</span>
          ) : null}
        </a>
      ),
    },
    {
      key: 'reason',
      header: '为什么关注',
      // The one column with no sort key: it is prose, and sorting prose by its
      // characters would produce an order that means nothing to a reader.
      render: (row) => <span className="text-ink-soft">{row.entry.reason}</span>,
    },
    {
      key: 'price',
      header: '现价',
      numeric: true,
      render: (row) => <QuoteCell result={row.quote ?? undefined} />,
    },
  ]
}
