import { type FormEvent, useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  convergeCard,
  createCard,
  getCardSchedule,
  listCardReviews,
  scheduleCard,
  verifyCard,
  type Card,
  type CardInput,
  type CardReview,
  type ClaimType,
  type Schedule,
} from './api'
import { formatMoment } from './format'
import { CardReviewTimeline, CardTimeline } from './components/data/timelineAdapters'
import { Button, Input, Textarea } from './components/ui'
import { useResource } from './useResource'

/**
 * The knowledge layer on an instrument page (K1): what I have claimed about
 * this company, where each claim came from, and the gate for the next one.
 *
 * Read order is **newest first**, the opposite of the decision journal: the
 * decisions read oldest-first because they are a story about a person changing
 * their mind. Cards are not a story — they are the current body of claims, and
 * an older card still stands; it just answers an older question. Newest first
 * is "what do I currently believe".
 *
 * K2 (spec 013) adds the lifecycle. Active cards are the current claims. A
 * converged card is not deleted or hidden (red line 10 — you must still see
 * what you gave up and why); it retires to a dimmed section. Every origin or
 * state change appends an event, shown on the card, so "why is this card in
 * its present state" always has an answer.
 *
 * The provenance is shown on every card, never hidden behind a tooltip. The
 * timestamps are shown because a claim recorded *after* an outcome it purports
 * to predict is not evidence — it is a diary entry written in hindsight.
 */

interface Props {
  market: string
  code: string
  cards: Card[]
  onRecorded: () => void
}

const CLAIM_LABEL: Record<ClaimType, string> = {
  supporting: '支持',
  challenging: '质疑',
  neutral: '中性',
}

const CLAIM_TONE: Record<ClaimType, string> = {
  supporting: 'border-l-brass',
  challenging: 'border-l-up',
  neutral: 'border-l-navy',
}

export default function CardSection({ market, code, cards, onRecorded }: Props) {
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<{ message: string; fix: string | null } | null>(null)

  const [content, setContent] = useState('')
  const [claimType, setClaimType] = useState<ClaimType>('supporting')
  const [sourceUrl, setSourceUrl] = useState('')
  const [sourceTitle, setSourceTitle] = useState('')
  const [priority, setPriority] = useState('3')
  const [asOf, setAsOf] = useState('')

  const complete =
    content.trim().length > 0 && sourceUrl.trim().length > 0 && sourceTitle.trim().length > 0

  const activeCards = cards.filter((card) => card.status === 'active')
  const convergedCards = cards.filter((card) => card.status === 'converged')

  function reportError(caught: unknown, fallback: string) {
    setError(
      caught instanceof ApiError
        ? { message: caught.message, fix: caught.fix }
        : { message: fallback, fix: null },
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!complete || busy) return

    setBusy(true)
    setNotice(null)
    setError(null)
    try {
      const input: CardInput = {
        content: content.trim(),
        claim_type: claimType,
        source_url: sourceUrl.trim(),
        source_title: sourceTitle.trim(),
        origin: 'user_written',
        priority: Number(priority),
        symbols: [`${market}${code}`],
        ...(asOf.trim() ? { as_of: asOf.trim() } : {}),
      }
      await createCard(input)
      setContent('')
      setSourceUrl('')
      setSourceTitle('')
      setAsOf('')
      setNotice('卡片已写入 —— 来源和主张都留了底，之后可以随时回来对照。')
      onRecorded()
    } catch (caught) {
      reportError(caught, '写入失败。')
    } finally {
      setBusy(false)
    }
  }

  async function handleVerify(cardId: string) {
    setError(null)
    try {
      await verifyCard(cardId)
      setNotice('已核实 —— 这张卡从「AI 生成」转成了「本人核对过」。')
      onRecorded()
    } catch (caught) {
      reportError(caught, '核实失败。')
    }
  }

  async function handleConverge(cardId: string, reason: string) {
    setError(null)
    try {
      await convergeCard(cardId, reason)
      setNotice('已收敛 —— 这张主张退出了当前观点，理由留了底。')
      onRecorded()
    } catch (caught) {
      reportError(caught, '收敛失败。')
    }
  }

  return (
    <section className="mt-4 border-t border-rule pt-4">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta font-normal caps text-ink-faint">
          我对它说过什么
        </h2>
        {cards.length > 0 ? (
          <span className="num type-badge text-ink-faint">{cards.length} 张卡片</span>
        ) : null}
      </div>
      <div className="border-b border-rule" />

      {cards.length === 0 ? (
        <p className="px-4 pt-2 type-prose text-ink-soft">
          还没有为它写过卡片。卡片是<strong className="text-ink">有来源的主张</strong> ——
          不是随手记，是「我这么说过，出处在这里」。
        </p>
      ) : (
        <div className="px-4 pt-2">
          <p className="type-prose text-ink-faint">
            新的在前。来源和主张一起留底，每一张都可以回去核对 ——
            来源打不开的卡片，主张也就失去了重量。
          </p>
          <ol className="mt-1.5">
            {activeCards.map((card) => (
              <CardItem
                key={card.id}
                card={card}
                onVerify={() => void handleVerify(card.id)}
                onConverge={(reason) => void handleConverge(card.id, reason)}
              />
            ))}
          </ol>

          {convergedCards.length > 0 && (
            <div className="mt-4 border-t border-rule pt-3">
              {/* Still a real heading: `instrument.spec.ts` finds this by
                  `getByRole('heading', { name: '已收敛的主张' })`, and a dimmed
                  region is exactly the kind of thing someone navigating by
                  region needs to be able to jump to. */}
              <h3 className="type-meta font-normal caps text-ink-faint">
                已收敛的主张
              </h3>
              <p className="mt-0.5 type-prose text-ink-faint">
                已退出当前观点，保留留痕，方便回看当时为什么放弃。
              </p>
              <ol className="mt-1.5">
                {convergedCards.map((card) => (
                  <CardItem
                    key={card.id}
                    card={card}
                    onVerify={() => void handleVerify(card.id)}
                    onConverge={(reason) => void handleConverge(card.id, reason)}
                  />
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      <form className="mt-4 px-4" onSubmit={handleSubmit}>
        <label className="flex flex-col gap-1">
          <span className="type-meta caps text-ink-faint">
            记一张卡片（主张 + 出处）{' '}
            <span className="text-up">主张、出处标题、出处链接必填</span>
          </span>
          <Textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={2}
            placeholder="例如：渠道库存是白酒的先行指标，通常领先报表 1-2 个季度。"
          />
        </label>

        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="type-meta caps text-ink-faint">出处标题</span>
            <Input
              value={sourceTitle}
              onChange={(event) => setSourceTitle(event.target.value)}
              placeholder="XX证券白酒渠道调研报告"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="type-meta caps text-ink-faint">
              出处链接（http/https）
            </span>
            <Input
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="https://…"
            />
          </label>
        </div>

        {/* ⭐ The two `<select>`s stay native, and that is a decision rather than
            an omission. `前端资源与打磨规格` §4.3 asks for a `Select` with 28px
            rows and a brass rule on the chosen item, and it is **not built** —
            it needs a listbox with focus management and `aria-activedescendant`,
            which is the first thing in this product that genuinely wants
            `cmdk`-style plumbing. A native select gets keyboard behaviour and
            screen-reader semantics for free and looks out of place; a hand-rolled
            one without that plumbing would be worse than out of place. */}
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 type-meta text-ink-soft">
            立场
            <select
              value={claimType}
              onChange={(event) => setClaimType(event.target.value as ClaimType)}
              className="rounded-[2px] border border-rule bg-surface px-1.5 py-1 type-prose outline-none focus:border-navy"
 >
              <option value="supporting">支持</option>
              <option value="challenging">质疑</option>
              <option value="neutral">中性</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 type-meta text-ink-soft">
            权重
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              className="num rounded-[2px] border border-rule bg-surface px-1.5 py-1 type-prose outline-none focus:border-navy"
 >
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={String(value)}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 type-meta text-ink-soft">
            数据截至（可选）
            <input
              type="date"
              value={asOf}
              onChange={(event) => setAsOf(event.target.value)}
              className="num rounded-[2px] border border-rule bg-surface px-1.5 py-1 type-prose outline-none focus:border-navy"
            />
          </label>
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <Button type="submit" variant="primary" disabled={!complete || busy}>
            {busy ? '写入中…' : '记下这张卡片'}
          </Button>
          <span className="type-meta text-ink-faint">
            {complete
              ? '卡片只增不改 —— 改主意是写一张新的，不是擦掉旧的。'
              : '主张、出处标题、出处链接缺一不可：没有出处的断言，过一个月连你自己都不知道它从哪来。'}
          </span>
        </div>

        {error && (
          <div className="mt-2 border-l-2 border-l-up py-1">
            <p className="type-prose text-up">{error.message}</p>
            {error.fix && <p className="type-prose text-ink-soft">{error.fix}</p>}
          </div>
        )}
        {notice && (
          <div className="mt-2 border-l-2 border-l-navy py-1">
            <p className="type-prose text-navy">{notice}</p>
          </div>
        )}
      </form>
    </section>
  )
}

/**
 * ⭐ **「加入复习」这一个控件，和它为什么是三个状态而不是一个布尔。**
 *
 * Spec 048。背景写在 `CardItem` 里那个注释块 —— 这里是实现。
 *
 * ⚠️ **`unknown` 与 `not-enrolled` 分开，是这个组件存在的理由。** 笔记那边
 * （`VaultPage`）用 `.catch(() => false)`：任何失败都读成「未入队」。于是后端
 * 停掉的时候，读者看到的是一个**「加入复习」按钮，点下去必然失败** ——
 * 那是一个看起来能用而实际不能用的控件，比没有更坏。
 *
 * ⚠️ **所以「不知道」这一态显示的是一句话，不是一个按钮。** 它也没有重试按钮 ——
 * **刷新页面就是重试**，而一个只做「再试一次」的按钮会让这一行永远占着位置。
 */
function Enrolment({
  cardId,
  readOnly = false,
}: {
  cardId: string
  /** A converged card gets no button — but it keeps whatever history it earned. */
  readOnly?: boolean
}) {
  // `null` = still asking. `'unknown'` = asked and did not find out.
  const [state, setState] = useState<'asking' | 'unknown' | 'out' | Schedule | 'busy'>('asking')
  const [error, setError] = useState<string | null>(null)

  // ⚠️ **`live` guards the response, not the request.** Without it, switching
  // instruments while a card's schedule is in flight sets state on a component that
  // is no longer on screen — `useResource` in this file's siblings does the same
  // thing and for the same reason.
  const [live, setLive] = useState(true)
  useEffect(() => {
    setLive(true)
    return () => setLive(false)
  }, [cardId])

  useEffect(() => {
    let current = true
    setState('asking')
    getCardSchedule(cardId)
      .then((schedule) => {
        if (current) setState(schedule ?? 'out')
      })
      .catch(() => {
        // ⭐ **Any other failure is 「不知道」, never 「没入队」.** See above.
        if (current) setState('unknown')
      })
    return () => {
      current = false
    }
  }, [cardId])

  async function enrol() {
    setState('busy')
    setError(null)
    try {
      const schedule = await scheduleCard(cardId)
      if (live) setState(schedule)
    } catch (caught) {
      setState('out')
      setError(
        caught instanceof ApiError ? caught.message : '加入复习失败。这张卡片没有变化。',
      )
    }
  }

  if (state === 'asking') return null

  if (state === 'unknown') {
    // ⚠️ A converged card gets **nothing** here, not even the sentence: the sentence
    // explains why there is no 「加入复习」 button, and on a converged card there is no
    // button to explain. ⭐ The history below is equally unavailable — and that is
    // honest, because this state means 「不知道」, not 「没有」.
    if (readOnly) return null
    return (
      <p className="type-meta text-ink-faint" data-testid="card-schedule-unknown">
        复习状态取不到，所以这里不给「加入复习」—— 刷新页面再试。
      </p>
    )
  }

  if (state === 'busy') {
    return (
      <p className="type-meta text-ink-faint" data-testid="card-schedule-busy">
        加入中…
      </p>
    )
  }

  if (typeof state === 'string') {
    // 'out' — known to be off the queue.
    //
    // ⭐⭐ **No history is fetched in this branch, and that is a derived fact rather than an
    // optimisation** (spec 055 §2.5): a review cannot exist without an enrolment, because
    // `scheduling.record_review` reads the schedule first and refuses otherwise
    // (`scheduling.py:284`). ⭐ So 「确定没入队」 settles the history question without
    // asking it — and since most cards are never enrolled, most cards cost **zero**
    // requests here.
    if (readOnly) return null
    return (
      <div className="flex flex-wrap items-baseline gap-2" data-testid="card-schedule-out">
        <Button size="sm" onClick={() => void enrol()}>
          加入复习
        </Button>
        {/* ⚠️ **The button says when it would come back**, because the reader is being
            asked to commit to something and the cost of saying so is one clause.
            `due_at` is the server's, not a guess about the reader's calendar. */}
        <span className="type-meta text-ink-faint">到时会自己回来。</span>
        {error ? <span className="type-meta text-[color:var(--color-up)]">{error}</span> : null}
      </div>
    )
  }

  return (
    <>
      {!readOnly && (
        <p className="type-meta text-ink-faint" data-testid="card-schedule-in">
          已加入复习 · 下次 {formatMoment(state.due_at)}
        </p>
      )}
      {/* ⭐⭐ **The history lives here, in the one branch that knows the card is enrolled.**

        spec 055. Measured on 2026-10-05: `scheduling.list_reviews()` was implemented,
        exported and tested, and **no route called it** — so a card that had been reviewed
        three times showed nothing anywhere. ⭐ This is the branch that answers 「我复习过 5 次，
        为什么今天又来了」, the question spec 028 opened notes for.

        ⚠️ **And it renders for a converged card too.** A card can be enrolled, reviewed,
        and then converged — and hiding its history because the claim changed would
        **delete a record that happened**, ⭐ which is the one thing this product does not
        do. `readOnly` therefore removes the *button* and keeps the *past*.

        ⚠️ **An enrolled card that was never answered renders nothing** (`CardReviewHistory`
        returns `null` on an empty array), also measured: enrolment inserts a schedule row
        and nothing else, so 「已加入复习」 does not imply a history exists.
      */}
      <CardReviewHistory cardId={cardId} />
    </>
  )
}

/**
 * A card's review history, fetched only once the card is known to be enrolled.
 *
 * ⭐ **Three states and three renderings**, and the third is the one that is easy to get
 * wrong: 「读到了，但是空的」 is **not** an error and **not** a sentence. An empty list means
 * the reader enrolled it and has not answered yet, ⭐ and the page already says
 * 「已加入复习 · 下次 …」 — so a second sentence about it would be the same fact twice.
 *
 * ⚠️ **A failure renders one clause and nothing else.** No history is better than a wrong
 * history, and red line 6 is about exactly this: an unripe result shows empty rather than
 * a plausible zero.
 */
function CardReviewHistory({ cardId }: { cardId: string }) {
  const load = useCallback(() => listCardReviews(cardId), [cardId])
  // ⚠️⚠️ **`describe` MUST be stable, and this is not documented where it matters.**
  //
  // `useResource`'s effect deps are `[...deps, describeError]` (`useResource.ts:130`), so
  // an inline arrow re-runs the effect on **every render** — and each run publishes state,
  // which renders again. ⭐ I hit that: A4 and A5 in `card-enrolment.spec.ts` timed out at
  // 30s with my change and passed without it, ⭐ and the JSON reporter said only
  // 「Test timeout of 30000ms exceeded」 with no stack and no line. `F-252`.
  //
  // ⇒ `useCallback` with `[]`, exactly as every other call site does
  // (`ReviewPage.tsx:73`, `VaultPage`). ⭐ The hook now guards against it internally too,
  // but a caller should not have to know.
  const describe = useCallback(() => '复习流水取不到。', [])
  const { data, error } = useResource<CardReview[]>(load, [cardId], describe)

  if (error) {
    return (
      <p className="type-meta text-ink-faint" data-testid="card-review-history-error">
        复习流水取不到。
      </p>
    )
  }
  if (!data || data.length === 0) return null
  return (
    <div data-testid="card-review-history">
      <CardReviewTimeline reviews={data} />
    </div>
  )
}

function CardItem({
  card,
  onVerify,
  onConverge,
}: {
  card: Card
  onVerify: () => void
  onConverge: (reason: string) => void
}) {
  const aiGenerated = card.origin === 'ai_generated'
  const converged = card.status === 'converged'

  const [showForm, setShowForm] = useState(false)
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  function submitConverge(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setFormError('写一句为什么它不再代表你当前的主张。')
      return
    }
    setFormError(null)
    onConverge(reason.trim())
  }

  const tone = converged
    ? 'border-l-rule opacity-60'
    : aiGenerated
      ? 'border-l-warn'
      : CLAIM_TONE[card.claim_type]

  return (
    <li className={`border-b border-[color:var(--color-rule-soft)] border-l-2 py-1.5 pl-3 ${tone}`}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="type-prose text-ink">
          {converged ? '已收敛' : (CLAIM_LABEL[card.claim_type] ?? card.claim_type)}
        </span>
        <span className="num type-meta text-ink-faint">{formatMoment(card.created_at)}</span>
        <span className="num type-meta text-ink-faint">权重 {card.priority}</span>
        {card.as_of && (
          <span className="num type-meta text-ink-faint">数据截至 {card.as_of}</span>
        )}
        {!converged &&
          (aiGenerated ? (
            <span className="type-meta text-warn">AI 生成 · 待核实</span>
          ) : (
            <span className="type-meta text-ink-faint">本人核对过</span>
          ))}
      </div>

      {/* Serif at 15px: a quotation of the reader's own claim (rule 1). It was
          16px; the step down is because a card row now carries a status line, a
          provenance line and up to two event lines, and 16px made a page of cards
          feel like a page of headlines. */}
      {/* ⭐ THE claim. §2.2's 「卡片/主张/象限判语 17–20 / 26，衬线」 row, and it was
          rendered at `text-[15px] leading-relaxed` — three pixels under the low end of
          the range the guide adjudicated, and at 1.625 leading rather than the 26px
          the table gives. A card is a piece of printed argument whose payload is a
          sentence the reader wrote about a company, and at 15px it was reading as
          another row of metadata. */}
      <p className="serif type-claim mt-0.5">{card.content}</p>

      <div className="mt-0.5 type-meta text-ink-soft">
        出处：
        {/* ⭐ L1, and this one has a second reason beyond the underline. A source link
            is the one link in this product that **leaves the product**, and it is the
            link whose absence would quietly turn a claim into an assertion. ⭐ So the
            hover state has to say 「this is a place you can go check」 — and the mark
            for that in this guide is a 2px left rule or a border (规则 5), not colour.
            Underline + fade is the compromise available for an inline source, and the
            fade is what separates it from a printed citation. */}
        <a
          className="text-navy no-underline hover:underline data-[motion=l1]"
          href={card.source_url}
          target="_blank"
          rel="noreferrer"
 >
          {card.source_title}
        </a>
        <span className="num text-ink-faint"> · 采集于 {formatMoment(card.captured_at)}</span>
      </div>

      {/* ⭐ `CardTimeline`, which is `RecordTimeline` plus this domain's vocabulary.
          The previous version was a bare `<ul>` in `type-meta` with no rule, no
          shape and a 「已收敛：」 prefix inside the sentence — ⭐ which read as a
          different product from the watchlist log three components away, even though
          both are append-only records of the reader's own decisions. ⭐ The API
          contract is unchanged (`test_cards_api.py` pins it); only the rendering moved,
          and `RecordTimeline`'s absence sentence means a `verified` row no longer
          shows an empty second line. */}
      {card.events.length > 0 && <CardTimeline events={card.events} />}

      {/*
        ⭐⭐⭐ **加入复习 —— 这个控件是 spec 048 的全部内容，而它能存在只因为后端多了一条
        读路由。**

        2026-10-02 量到的：卡片**只能靠写代码进复习队列**。
        `POST /api/v1/cards/{id}/schedule` 早就存在、而 `scheduleCard` 在 `api.ts`
        有定义**零调用者**；界面既不能知道一张卡在不在队列里，**也不能从
        `/review/due` 推断** —— 那个端点只给**到期**的，排在下周三的卡不在里面。
        ⇒ 「加入复习」如果只能靠点完才知道结果，**它就是一个赌注**，而这个产品不拿
        读者的记录下赌。

        ⭐ **三态，不是一个布尔：**

        | 显示 | 含义 |
        |---|---|
        | （什么都不显示） | 还在问 |
        | 「复习状态取不到。」 | **不知道** —— 后端没起来时**不许**显示「加入复习」，那是一个骗人的按钮 |
        | 「加入复习」 | 确定没入队 |
        | 「已加入复习 · 下次 …」 | 确定在队列里 |

        ⚠️ **笔记那边现在是 `.catch(() => false)`**（`VaultPage`），任何失败都读成
        「未入队」，于是后端一停就出现一个点了会失败的按钮。**本条按 `error.code`
        判断而不是按「抛了没有」**，并且**本 spec 不改笔记那条**（那是 spec 028
        的地盘，已记为欠账）。

        ⚠️ **不给「全部加入」。** 入队是显式的：把读者写过的每样东西都塞进队列，
        攒下的是一份没人清的欠账 —— 这条理由是 `VaultPage` 已经写下的，
        这里沿用它。⚠️ **而教训相反（红线 7 强制入队）**，因为教训是系统自己的产出，
        卡片是读者署名的东西。
      */}
      {/* ⭐ `readOnly` on a converged card: no 「加入复习」 button, but whatever review
          history it earned is still drawn. spec 055 — a card can be enrolled, reviewed and
          then converged, and hiding its history because the claim changed would delete a
          record that happened. */}
      <Enrolment cardId={card.id} readOnly={converged} />

      {!converged && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {aiGenerated && (
            <Button size="sm" onClick={onVerify}>
              我已对照过出处
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setShowForm((value) => !value)
              setFormError(null)
            }}
 >
            收敛这张卡
          </Button>
        </div>
      )}

      {showForm && !converged && (
        <form
          className="mt-1.5 border-l-2 border-l-rule py-1.5 pl-3"
          onSubmit={submitConverge}
 >
          <label className="flex flex-col gap-1">
            <span className="type-meta text-ink-faint">
              为什么它不再代表你当前的主张？
            </span>
            <Textarea
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="例如：公司改直营，渠道库存的先行关系失效了。"
            />
          </label>
          <div className="mt-1.5 flex gap-2">
            <Button size="sm" type="submit" variant="primary">
              确认收敛
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>
              取消
            </Button>
          </div>
          {formError && <p className="mt-1 type-prose text-up">{formError}</p>}
        </form>
      )}
    </li>
  )
}
