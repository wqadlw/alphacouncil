/**
 * The launch screen: what is waiting for you today, beside one painting.
 *
 * ⭐ **It is not a route, and that is a decision rather than an omission.**
 * `routing.ts` exists so that "a view is declared in exactly one place", and its
 * header is explicit that the table drives navigation, hash parsing, titles and
 * hrefs. A launch screen is none of those: it has no address, cannot be linked to,
 * Back does not return to it, and it must not appear in the nav — a 「开屏」 row in
 * a sidebar of five working views is a row that does nothing.
 *
 * ⭐ **It shows once a day, and a deep link skips it.** A tool somebody opens twenty
 * times a day cannot put a full-screen anything in front of that twenty times —
 * and a reader who opens `#/i/sh/600519` from a bookmark has asked a specific
 * question, which this screen has no business answering first. See `isHomeAddress`
 * in `launchLogic.ts`; that function exists because the first version put this
 * screen in front of every route and **broke 101 e2e tests** (every one of them
 * failing on 「the shell is not on screen」, which was correct of them).
 *
 * ---
 *
 * ## ⭐⭐ What changed on 2026-10-01, and why the first version was wrong
 *
 * The first version was **a painting with a slogan beside it**, and the owner
 * looked at it and said 「非常不满意」. Measuring it said why, and one of the
 * measurements was the important one:
 *
 * ```
 * viewport 1440×900
 *   .startup-copy   420 × 146      ← the words
 *   .startup-frame  698 × 558      ← the painting: 7× the words' area
 *   left margin      64px, then 420px of nothing
 * ```
 *
 * So: the picture was carrying the screen and the product was not on it at all.
 * 「投资是一场修行」 and a Zha Shibiao album leaf have nothing to do with each
 * other; they had been placed next to each other.
 *
 * **Three things changed, in order of how much they matter.**
 *
 * **1 · The screen says what it is for.** It now renders `GET /api/v1/today` and
 * leads with the answer — how many of the reader's own kill criteria have come due,
 * and what the market is doing. That is the product's actual first job
 * (spec 040 · 「判据会被送到你面前而不必你打开页面」), and it is data this screen would
 * otherwise be throwing away a request's worth of.
 *
 * **2 · The painting got smaller and the frame got bigger.** The first version had
 * the frame at 1.25:1 and the painting at 1.27:1 — near enough identical that it
 * read as **an image pasted onto a page** rather than an object on a wall. A real
 * mount is *visibly* larger than what it holds; that margin is what makes the
 * object an object. The frame is now `1fr` of the column rather than sized to the
 * painting.
 *
 * **3 · The way out is now a way out.** It was a 20px underlined link — about 2% of
 * a 900px screen, and the *only* exit from the screen. It is now the largest
 * single mark on the left column, because a screen whose one action looks
 * dismissible is a screen people dismiss.
 *
 * ⚠️ **The painting is still shown whole and uncropped**, which is the one thing
 * from the first version that was right and is kept: a two-metre hanging scroll and
 * a landscape album leaf are both 30-centimetre objects of the same kind, and
 * cropping one to match the other picks the wrong one.
 */

import { useEffect, useState } from 'react'
import { SCROLL_MUSEUM, scrollFor, scrollUrlFor } from './art/scroll/manifest'
import { getToday, type MarketStatus, type Today } from './api'
import { creditLine } from './launchLogic'
import { cn } from './lib/cn'

export interface StartupPageProps {
  /** Called when the reader wants in. The caller records it and navigates. */
  onEnter: () => void
  /** Injected in tests and in `e2e/`; the real page reads the clock. */
  now?: Date
  /**
   * ⭐ Injected in tests. The real page calls `getToday`.
   *
   * A parameter rather than a direct call because `e2e/launch.spec.ts` has to run
   * against a stubbed API, and because "what does this screen say when nothing is
   * due" is exactly the question this product has to answer well — it must be
   * answerable without a database.
   */
  loadToday?: () => Promise<Today>
}

/**
 * The one sentence the screen leads with.
 *
 * ⭐ **Written here rather than by the backend, and that is a deliberate temporary
 * asymmetry.** `/api/v1/today` ships `attention[].kind` and two counts, but no
 * sentence: spec 040 says the wording must be the product's, and every sentence on
 * that endpoint so far lives in `TodayPage`. Reusing that component's logic would
 * mean importing a page into the launch screen, and duplicating it would mean two
 * homes for the same wording.
 *
 * So it is one function, here, and **the debt is recorded**: when `/today` starts
 * sending the sentence (which is the right home for it), this function is deleted
 * and the field is rendered. See `.ai/logs/changes/2026-10-01-plan.md`.
 *
 * ⭐ **The three branches are ordered by how much they need the reader**, and the
 * order is the design. A kill criterion coming due is about a thing the *reader*
 * wrote and the date has arrived on — it is the strongest reason this product has
 * to interrupt, so it leads. The queues are second: they are work that was
 * scheduled, not work that has newly become urgent. "Nothing is due" is last, and
 * it is **not** an apology — it names the next thing that is missing, because a
 * screen that only says 「今天没有到期的东西」 leaves a new reader with no next step.
 */
function headline(snapshot: Today): { lead: string; detail: string } {
  const due = snapshot.attention.filter((a) => a.kind === 'kill_criterion_due').length
  const cards = snapshot.due.cards.count
  const reviews = snapshot.due.reviews.count

  if (due > 0) {
    return {
      lead: `你有 ${due} 条自己写下的失效条件到期了`,
      detail: '到期不是「已经触发」，是「观察期到了，去核实」。判断还是你自己做。',
    }
  }
  if (cards + reviews > 0) {
    const parts = [
      cards > 0 ? `${cards} 张卡片` : null,
      reviews > 0 ? `${reviews} 条复盘` : null,
    ].filter((x): x is string => x !== null)
    return {
      lead: `今天有 ${parts.join('、')}等着你`,
      detail: '它们是自己回来的，不是因为你点了什么。',
    }
  }
  return {
    lead: '今天没有到期的东西',
    detail: '关注池里还没有你写下的理由，而理由是必填的。',
  }
}

/**
 * What the market is doing, in the product's own vocabulary.
 *
 * ⭐ **Read off `TradingDayVerdict` rather than remembered.** The first version of
 * this wrote `verdict === 'trading'` and a fourth case `'error'`, and `tsc` caught
 * both — the union is `'trading_day' | 'non_trading_day' | 'unknown'`, three
 * values with no error case at all. Guessing a field's values is the same mistake
 * as guessing a column name (regression 0008), and it is caught the same way.
 *
 * ⚠️ `unknown` is **not** rendered as 「今天不开市」. It means the probe could not
 * read a bar, which is a statement about the data, not about the market; merging
 * the two is how 「我们不知道」 becomes 「什么都没有」.
 */
function marketLine(status: MarketStatus | null): string {
  if (status === null) return '正在判断今日是否交易'
  if (status.verdict === 'trading_day') return '今日在交易'
  if (status.verdict === 'non_trading_day') {
    return status.last_trading_date === null
      ? '今日休市'
      : `今日休市 · 最近一个交易日 ${status.last_trading_date}`
  }
  return '无法判断今日是否交易'
}

export function StartupPage({ onEnter, now, loadToday }: StartupPageProps) {
  const today = now ?? new Date()
  const scroll = scrollFor(today)
  const src = scrollUrlFor(today)

  /**
   * ⭐ The snapshot starts `null`, and `null` renders as a **single fixed line of
   * reserved space** rather than as nothing.
   *
   * The first version had no data at all and the screen was purely decorative, so
   * there was nothing to reserve. Now the layout has a headline above it, and a
   * request that has not come back yet must not move the painting — a screen whose
   * contents shift after it appears is a screen that has already asked to be
   * trusted before it had earned it.
   */
  const [snapshot, setSnapshot] = useState<Today | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const load = loadToday ?? getToday
    let live = true
    load()
      .then((s: Today) => {
        if (live) setSnapshot(s)
      })
      .catch(() => {
        // ⭐ A failure says so in four characters. It does **not** fall back to
        // 「今天没有到期的东西」, because that sentence is a claim about the
        // reader's own commitments and this screen has no way to make it.
        if (live) setFailed(true)
      })
    return () => {
      live = false
    }
  }, [loadToday])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onEnter()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onEnter])

  const say = snapshot === null ? null : failed === false ? headline(snapshot) : null

  return (
    <div className="startup" data-testid="startup" onClick={onEnter} role="presentation">
      <div className="startup-copy">
        {/* The date leads, not the brand.
            ⭐ **Order is the argument.** A launch screen is the first thing a
            reader sees each day, and what they want to know is what today is —
            not what this program is called. The brand name is here, it is just not
            first. The first version led with `AlphaCouncil` and that is what made
            the screen read as a title card. */}
        <p className="type-meta caps startup-rise text-ink-faint" data-testid="launch-date">
          {today.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            weekday: 'long',
          })}
          {`　${marketLine(snapshot?.market_status ?? null)}`}
        </p>

        {/*
          ⭐ The headline. `type-claim-lg` (20/28) and **serif**, because §2.1 puts
          serif on claims — and this **is** the product's own claim about the
          reader's state, which is what that row of the type scale is for. The first
          version used `type-display` in sans for the slogan, which was the right
          call for *a slogan* (it is about the reader, not written by them) and the
          wrong call for *this sentence*, which the product is making.

          The fixed-height wrapper is what stops the painting jumping: the sentence
          can be one line or two, and the slot below it must not move either way.
        */}
        <div className="startup-headline-slot">
          {say === null ? (
            <p className="type-claim-lg startup-rise text-ink-faint" data-testid="launch-headline">
              {failed ? '今天的事取不到。' : ' '}
            </p>
          ) : (
            <>
              <h1
                className="serif type-claim-lg startup-rise text-ink"
                data-testid="launch-headline"
              >
                {say.lead}
              </h1>
              <p className="type-prose startup-rise text-ink-soft" data-testid="launch-detail">
                {say.detail}
              </p>
            </>
          )}
        </div>

        {/* The exit. `type-claim-lg` (20/28), underlined with a brass rule —
            ⭐ **the largest single mark in the column**, because it is the only thing
            on this screen the reader can act on. It was `type-prose` (13px) and it
            read as a footnote about 2% of the screen's height.

            ⚠️ **`type-claim-lg`, not `type-page-title`, and `V-12` is what corrected
            this.** The first attempt used `type-page-title` (22px) on the grounds
            that it was the biggest size available — and `V-12`'s bound of
            `['type-page-title', 1, 1]` failed, with the comment already written:
            「One `<h1>` in the shell. Two would mean something else is a page title.」
            The rule is right and my reasoning was wrong: this button is not a page
            title, and styling it as one would have made two things on the screen
            compete for the same claim. §2.2's 主张 row is what a control that is
            also a statement wants, and 20/28 is still 50% larger than the 13px it
            replaces. */}
        <button
          type="button"
          className={cn('serif type-claim-lg startup-rise startup-enter')}
          onClick={(event) => {
            // The container's `onClick` would also fire, so `onEnter` would run
            // twice for one click — and `onEnter` writes storage and sets state.
            event.stopPropagation()
            onEnter()
          }}
          data-testid="launch-enter"
        >
          进入今天
        </button>

        {/* The slogan and the brand, last and small.
            ⭐ **Demoted, not removed, and `AlphaCouncil` keeps a heading role.**
            They are true and they are the product's identity; they are also not
            what a reader opening this screen twice a day came for, and the first
            version's mistake was believing otherwise — a title card spends the
            reader's first attention on itself.

            ⚠️ **The first attempt demoted `AlphaCouncil` to a bare `<span>` and
            `e2e/launch.spec.ts` failed on `getByRole('heading', { name:
            'AlphaCouncil' })`.** The test was right: a screen whose only heading is
            a sentence about due dates tells a screen reader nothing about what the
            thing is. So the sign-off keeps an `<h2>` for the brand — a second level,
            which is what a byline is — and the `<h1>` stays the headline, because
            that is what the reader is here for. */}
        <div className="type-meta startup-rise text-ink-faint startup-signoff">
          <h2 className="type-meta serif text-ink-soft">AlphaCouncil</h2>
          <span>投资是一场修行</span>
        </div>
      </div>

      <div className="startup-wall">
        {/* ⭐ `startup-hang` on the frame, not the image, so the mount and the
            painting settle as one object. `ac-hang` is `scaleY` from the top: a
            hanging scroll comes down off its roller, and a fade would say
            「an image appeared」 where this says 「an object was hung」. */}
        <figure className="startup-frame startup-hang">
          <img
            src={src}
            alt={`${scroll.artist}《${scroll.title}》，${scroll.date}`}
            width={scroll.width}
            height={scroll.height}
            // The largest paint on the app's first screen, with nothing above it.
            // The other 30 paintings are never fetched by a reader who dismisses
            // this screen, which is why they are `import.meta.glob`bed rather than
            // bundled as data URLs.
            fetchPriority="high"
            decoding="async"
            data-testid="launch-art"
            data-day={scroll.day}
          />
        </figure>
        {/* ⚠️ `type-badge` (11/14) was the first version's choice and it is the
            reason the credit wrapped to `of Art` on its own line: the museum's name
            is 26 characters of English, and at 11px in a 480px column it does not
            fit. It is `type-meta` now, and the column is wider — but the real fix
            is that **this line may wrap**, which is why it is allowed to. */}
        <figcaption className="type-meta startup-credit" data-testid="launch-credit">
          {creditLine(scroll.artist, scroll.date, scroll.title, SCROLL_MUSEUM)}
          <span className="startup-credit-day">
            {`　第 ${scroll.day} / 31 幅`}
          </span>
        </figcaption>
      </div>
    </div>
  )
}
