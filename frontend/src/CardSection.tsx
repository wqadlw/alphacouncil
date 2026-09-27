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
    <section className="mt-8 border-t border-rule pt-5">
      <div className="flex items-baseline justify-between border-b border-rule pb-2">
        <h2 className="serif text-[17px]">我对它说过什么</h2>
        <span className="num text-[12px] text-ink-faint">{cards.length} 张卡片</span>
      </div>

      {cards.length === 0 ? (
        <p className="mt-3 text-ink-soft">
          还没有为它写过卡片。卡片是<strong className="text-ink">有来源的主张</strong> ——
          不是随手记，是「我这么说过，出处在这里」。
        </p>
      ) : (
        <>
          <p className="mt-3 text-[12px] text-ink-faint">
            新的在前。来源和主张一起留底，每一张都可以回去核对 ——
            来源打不开的卡片，主张也就失去了重量。
          </p>
          <ol className="mt-3">
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
            <div className="mt-5 border-t border-rule pt-3">
              <h3 className="text-[13px] text-ink-soft">已收敛的主张</h3>
              <p className="mt-0.5 text-[12px] text-ink-faint">
                已退出当前观点，保留留痕，方便回看当时为什么放弃。
              </p>
              <ol className="mt-2">
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
        </>
      )}

      <form className="mt-6" onSubmit={handleSubmit}>
        <label className="flex flex-col gap-1">
          <span className="text-[12px] text-ink-faint">
            记一张卡片（主张 + 出处） <span className="text-up">主张、出处标题、出处链接必填</span>
          </span>
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={2}
            placeholder="例如：渠道库存是白酒的先行指标，通常领先报表 1-2 个季度。"
          />
        </label>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-ink-faint">出处标题</span>
            <input
              value={sourceTitle}
              onChange={(event) => setSourceTitle(event.target.value)}
              placeholder="XX证券白酒渠道调研报告"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-ink-faint">出处链接（http/https）</span>
            <input
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="https://…"
            />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-[13px] text-ink-soft">
            立场
            <select value={claimType} onChange={(event) => setClaimType(event.target.value as ClaimType)}>
              <option value="supporting">支持</option>
              <option value="challenging">质疑</option>
              <option value="neutral">中性</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-[13px] text-ink-soft">
            权重
            <select value={priority} onChange={(event) => setPriority(event.target.value)}>
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={String(value)}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-[13px] text-ink-soft">
            数据截至（可选）
            <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button type="submit" disabled={!complete || busy}>
            {busy ? '写入中…' : '记下这张卡片'}
          </button>
          <span className="text-[12px] text-ink-faint">
            {complete
              ? '卡片只增不改 —— 改主意是写一张新的，不是擦掉旧的。'
              : '主张、出处标题、出处链接缺一不可：没有出处的断言，过一个月连你自己都不知道它从哪来。'}
          </span>
        </div>

        {error && (
          <div className="mark mt-3 border-l-2 border-l-up py-1">
            <p className="text-up">{error.message}</p>
            {error.fix && <p className="text-[12px] text-ink-soft">{error.fix}</p>}
          </div>
        )}
        {notice && (
          <div className="mark mt-3 border-l-2 border-l-navy py-1">
            <p className="text-navy">{notice}</p>
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
    <li className={`mark border-t border-t-rule border-l-2 py-3 ${tone}`}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="text-[13px] text-ink">
          {converged ? '已收敛' : (CLAIM_LABEL[card.claim_type] ?? card.claim_type)}
        </span>
        <span className="num text-[12px] text-ink-faint">{formatMoment(card.created_at)}</span>
        <span className="num text-[12px] text-ink-faint">权重 {card.priority}</span>
        {card.as_of && (
          <span className="num text-[12px] text-ink-faint">数据截至 {card.as_of}</span>
        )}
        {!converged &&
          (aiGenerated ? (
            <span className="text-[12px] text-warn">AI 生成 · 待核实</span>
          ) : (
            <span className="text-[12px] text-ink-faint">本人核对过</span>
          ))}
      </div>

      <p className="serif mt-1 text-[16px] leading-relaxed">{card.content}</p>

      <div className="mt-1 text-[12px] text-ink-soft">
        出处：
        <a className="text-navy no-underline hover:underline" href={card.source_url} target="_blank" rel="noreferrer">
          {card.source_title}
        </a>
        <span className="num text-ink-faint"> · 采集于 {formatMoment(card.captured_at)}</span>
      </div>

      {card.events.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[12px] text-ink-faint">
          {card.events.map((event) => (
            <li key={event.id} className="num">
              {event.event_type === 'verified' ? (
                <>已对照出处 · {formatMoment(event.created_at)}</>
              ) : (
                <>
                  已收敛：{event.reason} · {formatMoment(event.created_at)}
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {!converged && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          {aiGenerated && (
            <button type="button" onClick={onVerify}>
              我已对照过出处
            </button>
          )}
          <button
            type="button"
            className="text-ink-faint"
            onClick={() => {
              setShowForm((value) => !value)
              setFormError(null)
            }}
          >
            收敛这张卡
          </button>
        </div>
      )}

      {showForm && !converged && (
        <form className="mark mt-2 border-l-2 border-l-rule py-2 pl-3" onSubmit={submitConverge}>
          <label className="flex flex-col gap-1">
            <span className="text-[12px] text-ink-faint">
              为什么它不再代表你当前的主张？
            </span>
            <textarea
              rows={2}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="例如：公司改直营，渠道库存的先行关系失效了。"
            />
          </label>
          <div className="mt-2 flex gap-3">
            <button type="submit">确认收敛</button>
            <button type="button" className="text-ink-faint" onClick={() => setShowForm(false)}>
              取消
            </button>
          </div>
          {formError && <p className="mt-1 text-[12px] text-up">{formError}</p>}
        </form>
      )}
    </li>
  )
}
