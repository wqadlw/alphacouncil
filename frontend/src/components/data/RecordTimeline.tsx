/**
 * One place where this product renders an append-only log.
 *
 * Authority: `docs/FRONTEND_STYLE_GUIDE.md` §8.2 — `RecordTimeline`「渲染 append-only
 * 事件（`card_events` / `reviews` / `decisions`）」.
 *
 * ## Why this component exists at all
 *
 * ⭐ **Before this file there were two renderings of the same idea and they did not
 * look alike.** `InstrumentPage`'s `TimelineRow` drew the watchlist log with a
 * 2px left rule, an event number and a 「取代 #N」 link; `CardSection` drew the
 * card's lifecycle as a bare `<ul>` in `type-meta` with no rule, no number and no
 * shape. ⭐ Both were correct about *their* data and inconsistent about the product.
 * §8.2 names one component, so the fix is not "add a component" — it is **give the
 * two existing renderings one home** and let each keep only the part that is genuinely
 * its own.
 *
 * ⭐ That last clause is the design. The component owns **the shape of a row**; the
 * caller owns **what an event means**. A card's 「已收敛」 and a watchlist's 「改口」 are
 * different sentences about different things, and a component that knew both would be
 * a component with a `switch` in it.
 *
 * ## The shape it accepts, and why it is this shape
 *
 * ```ts
 * interface TimelineEvent {
 *   id: string            // stable, unique within the list — the React key
 *   what: string          // the sentence for **what happened**
 *   at: string            // an ISO instant; the row formats it
 *   detail?: string | null  // the reader's own words, if there were any
 *   tone?: TimelineTone     // ⭐ absent means 「nothing to emphasise」, not 「neutral」
 * }
 * ```
 *
 * ⭐ **Three fields and no more, and each is load-bearing:**
 *
 * * `what` — ⭐ **a sentence, not an enum.** The first draft took `kind: 'verified' |
 *   'converged' | 'added' | …` and a lookup table, and that is the design that has to
 *   put every future event type into one `switch` in this file. ⭐ With a sentence, the
 *   card adapter can say 「已对照出处」 and the watchlist adapter can say 「改口」 without
 *   either knowing the other exists — and a new event type needs no change here at all.
 * * `detail` — ⭐ **`null` means the reader wrote nothing, and the row says so.** The
 *   watchlist log renders 「（离开时没有留下说明）」 for a removal with no reason, and
 *   that sentence is the product's honesty about an absent input; it is not an empty
 *   `<p>` and it must not become one.
 * * `tone` — ⭐ **optional, and absent is meaningful.** 规则 7: 颜色只承载意义. A
 *   removed watchlist entry is the one case in this product that deserves a mark,
 *   because it is the only event whose consequence is an absence. Everything else is
 *   left unmarked rather than marked neutral.
 *
 * ## What it deliberately does not do
 *
 * ⭐ **No sort, no group, no collapse.** Three append-only logs in this product are
 * already ordered by the server, and ⭐ the server's order is a promise — the
 * watchlist page says so in a sentence on screen: 「按写入顺序排列 —— 这是不可修改的记录」.
 * A component that sorted would make that sentence a lie in one place and not the
 * other. ⭐ Sorting is the adapter's decision or it is nobody's.
 */

import { type ReactNode } from 'react'

import { formatMoment } from '../../format'
import { cn } from '../../lib/cn'

/** ⭐ `plain` is **not** 「grey」 — it is 「nothing to emphasise」. See `tone`. */
export type TimelineTone = 'neutral' | 'marked'

export interface TimelineEvent {
  /** Stable and unique within the list. Used as the React key. */
  id: string
  /**
   * ⭐ A finished sentence for what happened — 「已对照出处」, 「改口」, 「已收敛」.
   * Not an enum: see the file header.
   */
  what: string
  /** An ISO instant. The row formats it; the caller does not. */
  at: string
  /**
   * The reader's own words, when there were any.
   *
   * ⭐ `null` and `undefined` mean the same thing on purpose, and the row renders
   * `absentDetail` for both — because 「the reader wrote nothing」 is one state, and
   * having two spellings of it would let a caller pick the one that skips the
   * sentence without meaning to.
   */
  detail?: string | null
  tone?: TimelineTone
  /**
   * ⭐ Anything that belongs **after** the timestamp — the watchlist's 「事件 #12」 and
   * 「取代 #11」, which are facts about the record's position rather than about what
   * happened. ⭐ Rendered in the same row as `at` so the position facts and the time
   * read as one cluster, and passed as a node so a caller can put a link in them
   * without this file knowing what a link to a record is.
   */
  aside?: ReactNode
}

export interface RecordTimelineProps {
  events: readonly TimelineEvent[]
  /** What to say when there are no events. ⭐ Required — see `emptyText` below. */
  emptyText: string
  /** ⭐ Overridable because the absence sentence is the product's, not this file's. */
  absentDetail?: string
  className?: string
  /** `ol` by default; `ul` where the order is not the point. */
  as?: 'ol' | 'ul'
}

export function RecordTimeline({
  events,
  emptyText,
  absentDetail = '（当时没有留下说明）',
  className,
  as: Tag = 'ol',
}: RecordTimelineProps) {
  if (events.length === 0) {
    // ⭐ Rule 8 applies to a log with nothing in it as much as to a page: one
    // statement of fact, and no 「还没有…」 phrasing. The caller supplies the
    // sentence because 「没有记录」 and 「没有留下说明」 are different claims about
    // different things and this file cannot tell them apart.
    return <p className={cn('type-prose text-ink-soft', className)}>{emptyText}</p>
  }

  return (
    <Tag className={cn('mt-1.5', className)}>
      {events.map((event) => {
        const emphasised = event.tone === 'marked'
        return (
          <li
            key={event.id}
            className={cn(
              // Rule 5 — a category is marked with a 2px left rule, never a pill.
              //
              // ⭐⭐ **`.mark` was removed from here, and it was breaking the colour.**
              // `.mark` is a hand-written class in `globals.css` ⭐ — ⭐ `border-left:
              // 2px solid var(--color-rule)` as a **shorthand**, ⭐ in a rule that sits
              // outside every `@layer` ⭐ because it is after the `@import`. ⭐ An
              // unlayered rule beats the whole utilities layer, ⭐ so `border-l-transparent`
              // ⭐ and `border-l-[color:…]` both lost to it, ⭐ and **every row rendered
              // with the same left rule** ⭐ — ⭐ which is the defect the E2E found when
              // it asserted on computed styles instead of on class names.
              //
              // ⭐ **The class is still used elsewhere** ⭐ (the vault's error rows) ⭐
              // and removing it *here* is not a fix to `.mark` ⭐ — ⭐ it is this
              // component no longer depending on a rule it cannot override. ⭐ The
              // shorthand is also unnecessary: ⭐ width, style and colour are all set
              // below, ⭐ and a row whose tone changes then shifts by nothing.
              'border-b border-[color:var(--color-rule-soft)] border-l-2 border-solid py-1.5 pl-3',
              emphasised ? 'border-l-[color:var(--color-ink-faint)]' : 'border-l-transparent',
            )}
          >
            <div className="flex flex-wrap items-baseline gap-x-3">
              {/* ⭐ `type-prose`, not `type-meta`. The first version used `type-meta`
                  (12px all-caps row) and that was the card version's mistake: a log
                  entry is a *sentence about a decision*, and §2.2 gives 正文散文 13px.
                  Chrome belongs to the column headers, not to the record. */}
              <span className="type-prose text-ink">{event.what}</span>
              <span className="num type-meta text-ink-faint">{formatMoment(event.at)}</span>
              {event.aside}
            </div>
            {event.detail ? (
              <p className="mt-0.5 type-prose text-ink">{event.detail}</p>
            ) : (
              // ⭐ **The absence is stated, not left blank.** A row whose second line
              // is missing reads as "nothing to say", and the reader cannot tell that
              // apart from "the page failed to load it".
              <p className="mt-0.5 type-prose text-ink-faint">{absentDetail}</p>
            )}
          </li>
        )
      })}
    </Tag>
  )
}
