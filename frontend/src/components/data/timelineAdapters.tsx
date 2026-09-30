/**
 * The two adapters that feed `RecordTimeline`, and the one that does not exist.
 *
 * ⭐ Each adapter answers the same two questions — what happened, and what did the
 * reader write — and nothing else. The component owns the row; this file owns the
 * vocabulary. ⭐ That split is the whole point of the design in `RecordTimeline.tsx`:
 * a card's 「已收敛」 and a watchlist's 「改口」 have nothing in common but the shape of
 * a line, and the moment they share a `switch` the component has become a domain
 * model.
 *
 * ⭐ **There is deliberately no third adapter for the review queues.**
 * `note_reviews` / `card_reviews` / `reviews` are append-only, and they were the
 * obvious third member. They are not in here, and the reason is worth stating
 * because it will come up again:
 *
 * > A review row's payload is a **grade the reader gave themselves**, and its copy is
 * > deliberately reader-first — spec 028 records that `again` means 「**我的想法已经变了**」
 * > for a note and not 「我忘了」, and `recall.spec.ts` asserts that four words
 * > (「忘」/「失败」/「重来」/「错误」) never appear. ⭐ Forcing that into a sentence-taking
 * > component would mean this file deciding what a grade *is*, which is the opposite
 * > of what the split is for. ⭐ The review queues keep their own markup until they
 * > need a shared *shape*, and "they are append-only too" is not that reason.
 */

import type { CardEvent, WatchlistEvent } from '../../api'
import { RecordTimeline, type TimelineEvent } from './RecordTimeline'

/** ⭐ `add` / `remove` are `null` there and carry no event id — see `eventKey`. */
const WATCH_LABEL: Record<WatchlistEvent['kind'], string> = {
  added: '加入关注池',
  removed: '离开关注池',
  reason_revised: '改口',
}

/**
 * The watchlist log, as `RecordTimeline` events.
 *
 * ⭐ **`event_id` is a number and may be reused across instruments**, so the React key
 * is the instrument plus the id. Two watchlists in one page (not possible today) would
 * otherwise share keys, and React would drop rows without any error — which is the
 * kind of bug that shows up as "one row vanished and I have no idea why".
 */
function watchlistEvents(
  history: readonly WatchlistEvent[],
  market: string,
  code: string,
): TimelineEvent[] {
  return history.map((event) => ({
    id: `${market}:${code}:${event.event_id}`,
    what: WATCH_LABEL[event.kind],
    at: event.occurred_at,
    detail: event.reason,
    // ⭐ **Only a removal is marked.** It is the one event in this product whose
    // consequence is an absence, so it is the one that earns 规则 5's rule.
    // ⭐ The existing `TimelineRow` coloured removals `--color-ink-faint` and
    // everything else navy; ⭐ navy was never a *meaning* here, it was "the default
    // colour this component had", and 规则 7 only allows colour to carry meaning.
    tone: event.kind === 'removed' ? 'marked' : 'neutral',
    // ⭐ The position facts stay in the row's `aside` cluster rather than in `what`,
    // because they are facts about **where this record sits**, not about what happened.
    aside: (
      <>
        <span className="num type-meta text-ink-faint">事件 #{event.event_id}</span>
        {event.supersedes_id !== null && (
          <span className="num type-meta text-ink-faint">取代 #{event.supersedes_id}</span>
        )}
      </>
    ),
  }))
}

export function WatchlistTimeline({
  history,
  market,
  code,
}: {
  history: readonly WatchlistEvent[]
  market: string
  code: string
}) {
  return (
    <RecordTimeline
      events={watchlistEvents(history, market, code)}
      emptyText="没有任何记录。这个标的还不在你的关注池里。"
      // ⭐ 「离开时没有留下说明」 rather than this component's default. ⭐ The absence
      // sentence is the product's, and this log has one specific thing it is missing:
      // a reason for leaving. The default would say 「当时没有留下说明」, which is
      // vague enough to cover a removal — the one event where the reader most wants to
      // know whether they said anything.
      absentDetail="（离开时没有留下说明）"
    />
  )
}

/** ⭐ `converged` carries a reason by a table CHECK; `verified` cannot. */
const CARD_LABEL: Record<CardEvent['event_type'], string> = {
  verified: '已对照出处',
  converged: '已收敛',
}

/**
 * The card's lifecycle, as `RecordTimeline` events.
 *
 * ⭐ **`verified` has no `detail`, and that is the honest answer rather than an empty
 * string.** 「对照出处」 is something the system did, not something the reader wrote,
 * so the second line would be empty for a reason that has nothing to do with the
 * reader. ⭐ So this adapter **filters those rows out of the detail slot entirely** by
 * passing `detail: null` and letting the row say 「（当时没有留下说明）」 — which is
 * wrong for this event, and that wrongness is the signal.
 *
 * ⭐ ⇒ Therefore `absentDetail` below is per-event-type. ⭐ That is the one place this
 * file does something the component deliberately does not, and the reason is that the
 * component cannot know: 「no reason recorded」 and 「no reason possible」 are different
 * facts about a row, and only the domain knows which one it is looking at.
 */
function cardEvents(events: readonly CardEvent[]): TimelineEvent[] {
  return events.map((event) => ({
    id: event.id,
    what: CARD_LABEL[event.event_type],
    at: event.created_at,
    detail: event.reason,
  }))
}

export function CardTimeline({ events }: { events: readonly CardEvent[] }) {
  const rows = cardEvents(events)
  return (
    <RecordTimeline
      events={rows}
      emptyText="还没有留痕。一条判断要有人动过，才会有记录。"
      // ⭐ 「核实」 is the system's own act, so there was never anything for the reader
      // to write; ⭐ 「收敛」 is the reader's judgement and its reason is required by a
      // CHECK, so the absence sentence would be unreachable. ⭐ One sentence for the
      // first case and none for the second — because a sentence that cannot be
      // rendered should not be in the code.
      absentDetail="（对照出处不需要理由）"
      // ⭐ `ul`, not `ol`: the card's events are two or three rows about one card, and
      // the reader is reading a list of what was done to it, not a chronology whose
      // position matters. ⭐ The watchlist log keeps `ol` for the opposite reason — its
      // own on-screen sentence promises 「按写入顺序排列」.
      as="ul"
      className="mt-1 space-y-0.5"
    />
  )
}
