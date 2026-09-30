import { type FormEvent, useState } from 'react'
import {
  ApiError,
  convergeCard,
  createCard,
  verifyCard,
  type Card,
  type CardInput,
  type ClaimType,
} from './api'
import { formatMoment } from './format'
import { CardTimeline } from './components/data/timelineAdapters'
import { Button, Input, Textarea } from './components/ui'

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
