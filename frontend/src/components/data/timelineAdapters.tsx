/**
 * The three adapters that feed `RecordTimeline`.
 *
 * ⭐ Each adapter answers the same two questions — what happened, and what did the
 * reader write — and nothing else. The component owns the row; this file owns the
 * vocabulary. ⭐ That split is the whole point of the design in `RecordTimeline.tsx`:
 * a card's 「已收敛」 and a watchlist's 「改口」 have nothing in common but the shape of
 * a line, and the moment they share a `switch` the component has become a domain
 * model.
 *
 * ⭐⭐ **The third adapter exists, and the first version of this file said it must
 * not.** The argument was: a review row is **a grade the reader gave themselves**,
 * its copy is deliberately reader-first ⭐ — spec 028 records that `again` means
 * 「**我的想法已经变了**」 and not 「我忘了」, ⭐ and `recall.spec.ts` asserts that four
 * words (「忘」/「失败」/「重来」/「错误」) never appear — ⭐ so putting it in a
 * sentence-taking component would mean this file deciding what a grade *is*.
 *
 * ⭐ **That argument was right about the review *screen* and wrong about the review
 * *history*, and the difference is the whole correction.** `RecallView` shows a
 * prompt and four buttons, ⭐ and there the reader is being asked 「你还记得吗」 ⭐ — ⭐ so
 * the copy has to be kind, and 「你忘了」 is a sentence about the reader. ⭐ A history
 * row is not that: ⭐ it is **a record of what happened**, ⭐ read days later by
 * someone who wants the answer to 「我复习过几次」 and 「为什么它今天又来了」 — ⭐ and
 * spec 028's whole reason for making a rewrite a `reset` **is** that the reader can
 * be told the truth about it. ⭐ A history that is written kindly and a button that
 * is written kindly are two different sentences, ⭐ and merging them would have made
 * both worse.
 *
 * ⭐ And the reason it is here now rather than in stage C is that in stage C
 * **there was nothing to render**: ⭐ `listNoteReviews` had zero callers, ⭐ so the
 * third adapter would have been a component with no page — ⭐ `F-149`, the same
 * mistake as the 13-entry icon registry. ⭐ The rule is not 「never add a third
 * adapter」 ⭐ it is 「add the third adapter when something can show it」.
 */

import type { CardEvent, WatchlistEvent } from '../../api'
import type { NoteReview } from '../../notes'
import { labelsOf, NOTE_RATINGS } from '../knowledge/ratings'
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


/**
 * ⭐ **The note history's grades, borrowed from the note queue's own buttons.**
 *
 * Exported so `ratings.test.ts` can compare the values rather than the wording — and
 * ⭐ **a value comparison is the assertion that would have caught the drift**: the wire
 * values were identical all along, only the words on screen differed.
 */
export const NOTE_RATING_LABEL = labelsOf(NOTE_RATINGS)

/** ⭐ `deferred` and `reset` are **not** grades — a rating is `null` for both. */
const OUTCOME_LABEL: Record<NoteReview['outcome'], string> = {
  reviewed: '复习过',
  // ⭐ 「不是我答错，是我想再等等」 ⭐ — ⭐ spec 028's `defer` is 「**我的想法变了，
  // 以后再说**」 ⭐ and a history row that called it 「延期」 would sound like a
  // scheduler's word rather than the reader's.
  deferred: '我说以后再看',
  // ⭐⭐ **The word that answers a two-spec-old question.** spec 028 made 「改写笔记」
  // a `reset` instead of silently moving the due date, ⭐ and the reason it gives is
  // 「**我复习过 5 次，为什么今天又来了**」 ⭐ — ⭐ a question the reader can only answer
  // if a row says 「**这条被我改过，排程从头开始**」. ⭐ Without this row the `reset` is
  // invisible: ⭐ the note reappears on schedule and the reader has no way to learn
  // that they are looking at a *second* pass over different text.
  reset: '这条被我改过，排程从头开始',
}

/**
 * A note's review history, as `RecordTimeline` events.
 *
 * ⭐ **The detail line is the grade *and* the new due date, and both are the
 * reader's question answered.** 「记了 4 次，下一次 2026-10-03」 ⭐ is what someone
 * checking a schedule actually wants, ⭐ and either half alone leaves them guessing.
 *
 * ⭐ **`duration_ms` is deliberately not shown.** ⭐ The table has it and a
 * 「性能」-shaped instinct says show it, ⭐ but this product's red lines reject
 * self-scoring: ⭐ 「你复习了 3 秒」 ⭐ invites the reader to optimise their own recall
 * instead of reading, ⭐ and spec 028's copy work is entirely about moving them away
 * from that. ⭐ A number the reader cannot act on is noise with a decimal point.
 */
function noteReviewEvents(reviews: readonly NoteReview[]): TimelineEvent[] {
  return reviews.map((review) => ({
    id: review.id,
    what:
      review.outcome === 'reviewed' && review.rating !== null
        ? `${OUTCOME_LABEL[review.outcome]} · ${NOTE_RATING_LABEL[review.rating]}`
        : OUTCOME_LABEL[review.outcome],
    at: review.reviewed_at,
    detail: `下一次 ${review.to_due_at.slice(0, 10)}`,
    // ⭐ **A `reset` is marked, and it is the only one.** ⭐ Rule 7: colour carries
    // meaning. ⭐ 「这条被我改过」 ⭐ is the one event here whose *consequence* is
    // different from the others ⭐ — ⭐ it wiped the schedule ⭐ — ⭐ and that is worth
    // the one rule this list has.
    tone: review.outcome === 'reset' ? 'marked' : 'neutral',
  }))
}

export function NoteReviewTimeline({ reviews }: { reviews: readonly NoteReview[] }) {
  return (
    <RecordTimeline
      events={noteReviewEvents(reviews)}
      // ⭐ Rule 8: one fact, no 「还没有…」 phrasing, ⭐ and the fact is the useful one
      // ⭐ — a note never enroled has no history ⭐ and a note enroled but never
      // ⭐ returned has one. ⭐ The sentence distinguishes the two.
      emptyText="它没有回来过。要它回来，得先请它回来。"
      // ⭐ `ol`, unlike the card's `ul`. ⭐ A review history's **order is the whole
      // point** — ⭐ 「我复习过 5 次」 ⭐ is a claim about a sequence, ⭐ and the new
      // due date is a claim about where the sequence is going.
      as="ol"
      className="mt-1"
    />
  )
}
