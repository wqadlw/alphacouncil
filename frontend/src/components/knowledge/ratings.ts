/**
 * ⭐⭐⭐ **The four FSRS grades, in the reader's own words, and this is their one home.**
 *
 * Spec 049. The measurement that produced this file:
 *
 * ```
 *   RecallView.tsx        again 我的想法变了   hard 想得起来，但有点犹豫  good 还是我的想法  easy 太熟了
 *   LessonRecallView.tsx  again 我的想法变了   hard 想得起来，但吃力      good 想得起来      easy 张口就来
 *   timelineAdapters.tsx  again 我的想法变了   hard 想起来了，但慢        good 记得          easy 不用想   <- neither
 * ```
 *
 * ⭐ **The third row was the defect.** `NoteReviewTimeline` renders in
 * `VaultPage.tsx:1016`, so a reader who pressed 「想得起来，但有点犹豫」 in the queue
 * found 「想起来了，但慢」 in the record of it. **The history could not answer
 * 「我当时按的是哪个」** — which is the same class of question spec 028 and spec 045
 * were opened for (「我复习过 5 次，为什么今天又来了」), one level deeper.
 *
 * ⚠️ **The first two rows stay different, and that is not drift.**
 * `RecallView.tsx:51-53` and `LessonRecallView.tsx:43` each argue it at length: a
 * note is something the reader wrote, so its `again` means 「**我的思想已经变了**」,
 * while a lesson is the system's own output and its `again` does not. Flattening them
 * would erase a real distinction **and** would be a third wording — the failure this
 * file exists to end.
 *
 * ⇒ So there are two tables, and everything that renders a grade imports from here.
 * ⚠️ `ratings.test.ts` pins that `timelineAdapters` uses *these* labels rather than
 * its own, because the alternative is a copy somebody edits without reading why.
 */

import type { ReviewRating } from '../../api'
import type { LessonRating } from '../../lessons'

/** A grade as the reader sees it on a button. */
export interface RatingChoice<T extends string> {
  value: T
  label: string
  /** Why the button says this. Empty is allowed \u2014 a lesson's are. */
  hint: string
}

/**
 * Notes: the reader's own sentences, and `again` is the one that matters.
 *
 * 「我的想法变了」 rather than 「我回忆不起来」: a note that has been overtaken by the
 * reader's thinking is information the product wants, and a scale that reads the same
 * as an ordinary forgetting would bury it.
 */
export const NOTE_RATINGS: RatingChoice<ReviewRating>[] = [
  { value: 'again', label: '我的想法变了', hint: '这条已经跟不上现在的判断了' },
  { value: 'hard', label: '想得起来，但有点犹豫', hint: '还在，不过已经不牢' },
  { value: 'good', label: '还是我的想法', hint: '重读一遍就回来了' },
  { value: 'easy', label: '太熟了', hint: '根本不用想' },
]

/**
 * Lessons: the same four wire values, the reader's words for a different thing.
 *
 * ⭐ The hints are empty here and that is deliberate \u2014 `recallContract.test.ts`
 * asserts every hint is longer than two characters, and it asserts that of
 * **NOTE** ratings. A lesson has less to say: it is a conclusion the product drew, so
 * 「想得起来」 needs no further explanation, and a hint invented to fill the field
 * would be a sentence nobody chose.
 */
export const LESSON_RATINGS: RatingChoice<LessonRating>[] = [
  { value: 'again', label: '我的想法变了', hint: '这条我现在不认了 —— 它该重新想一遍。' },
  { value: 'hard', label: '想得起来，但吃力', hint: '' },
  { value: 'good', label: '想得起来', hint: '' },
  { value: 'easy', label: '张口就来', hint: '' },
]

/**
 * Flatten a table for a `Record<Rating, string>` lookup.
 *
 * ⭐ A function rather than two more constants, because a third pair of constants is
 * how the four spellings happened in the first place.
 */
export function labelsOf<T extends string>(from: readonly RatingChoice<T>[]): Record<T, string> {
  const out = {} as Record<T, string>
  for (const entry of from) out[entry.value] = entry.label
  return out
}