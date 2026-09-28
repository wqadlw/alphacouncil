/**
 * A relative "how long ago" label, for the recall queue (spec 029).
 *
 * ## Why relative, in the queue and nowhere else
 *
 * The queue's whole value is that these notes come back **unsought**. A row that
 * reads 「2026-09-20」 makes the reader do a subtraction against today's date to
 * learn what the number means. A row that reads 「8 天前」 *is* the meaning.
 *
 * ⭐ **This is also why the queue does not show note titles.** Showing them would
 * make the list scannable — and that is exactly the problem. A scannable list of
 * things you owe is a to-do list, and 「你欠 N 条」 is the feeling the product's red
 * lines reject outright (`项目总纲` §2.1⑤: 一句陈述，无推送、无红点、无催促词).
 *
 * A queue is an **information source**, not a work list. So: no title, no count, no
 * priority, no order the reader chose — just *when this came back*, which is the
 * one fact that makes the visit feel like a re-read rather than an item to clear.
 *
 * ## Why the unit changes
 *
 * 「3 天前」 and 「3 个月前」 are both true and neither is more useful; a reader
 * does not care about the difference, only that it has been a while. The unit
 * therefore widens with the gap — and the recent end stays in **days**, not hours,
 * because 「5 小时前」 invites the reader to wonder whether the schedule is working.
 * A note scheduled for today is 「今天」, which is the most reassuring answer and the
 * cheapest one.
 *
 * Deliberately not present: 「还有 N 天」, 「逾期」, anything in the imperative. The
 * past tense is the whole choice.
 */

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/**
 * @param iso    an instant, as the API sends it
 * @param now    injected so a test does not depend on the wall clock
 */
export function formatAgo(iso: string | null, now: Date = new Date()): string {
  if (iso === null) return '—'
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return '—'

  const elapsed = now.getTime() - then.getTime()

  // A due date in the future means the schedule moved (a deferral, or a reset that
  // put it back). Naming it as elapsed time would print a negative age, so the
  // label flips rather than lying about the sign.
  if (elapsed < 0) return '今天'

  if (elapsed < DAY) return '今天'
  const days = Math.floor(elapsed / DAY)
  if (days < 31) return `${days} 天前`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months} 个月前`
  return `${Math.floor(days / 365)} 年前`
}
