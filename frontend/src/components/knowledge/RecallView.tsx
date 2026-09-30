/**
 * The note recall queue (spec 028) — 「该复习」 inside the knowledge vault.
 *
 * ## Three decisions the copy is carrying, not the code
 *
 * 1. ⭐ **`again` is 「我的想法变了」, not 「我忘了」.** The wire format sends the
 *    same `"again"` either way, so the difference has to be said here. For a
 *    note, a changed view is the most useful answer the reader can give — it
 *    means this note has been overtaken by their own thinking, and it is the
 *    moment to rewrite it. Labelling it a failure throws that away.
 *
 * 2. ⭐ **The full note is shown, not a title to recall from.** Anki hides the
 *    answer behind a prompt; that works when the prompt *is* the question. A
 *    note's title is not a prompt — 「关于流动性的一点想法」 does not say what to
 *    recall, it only tests whether you can guess from your own headline. A card's
 *    claim is a complete prompt, which is why cards can hide and notes cannot.
 *
 * 3. ⭐ **No count, anywhere.** Not in the heading, not in an empty state, not in
 *    a `remaining` field. 「一句陈述，无推送、无红点、无催促词」 — and the queue's
 *    length is the one number that turns "some things I wrote need revisiting"
 *    into a tally to clear. `test_the_queue_renders_no_count` holds it.
 *
 * ## Why this lives in the vault and not on the review page
 *
 * The review page is constrained in ways that make it the wrong home: the
 * dangerous quadrant asserts `document.body` has no digits at all, and the card
 * queue there is deliberately not given the `detail` slot. The vault is where
 * notes already are, so a 「该复习」 filter is where a reader looks for "the notes
 * I asked to be brought back to".
 */

import { useCallback, useState } from 'react'
import {
  deferNote,
  type Note,
  type NoteSchedule,
  type ReviewRating,
  getNote,
  listDueNotes,
  reviewNote,
} from '../../notes'
import { ApiError } from '../../api'
import { formatMoment } from '../../format'
import { formatAgo } from './formatAgo'
import { Button, Rule, Textarea } from '../ui'
import { useResource } from '../../useResource'
import { Markdown } from './Markdown'

/** ⭐ The four answers, in the reader's own words.
 *
 * `again` is the one that matters: **「我的想法变了」**, never 「忘了」. A note that
 * has been overtaken is information the product wants, and a rating scale that
 * calls it a lapse teaches the reader to avoid the most honest answer available.
 *
 * Exported because `recallContract.test.ts` asserts against **these** strings
 * rather than a copy of them — a test that hard-codes the copy it is checking
 * stays green when the button is reworded, which is the regression it exists to
 * prevent.
 */
export const RATINGS: { value: ReviewRating; label: string; hint: string }[] = [
  { value: 'again', label: '我的想法变了', hint: '这条已经跟不上现在的判断了' },
  { value: 'hard', label: '想得起来，但有点犹豫', hint: '还在，不过已经不牢' },
  { value: 'good', label: '还是我的想法', hint: '重读一遍就回来了' },
  { value: 'easy', label: '太熟了', hint: '根本不用想' },
]

/**
 * ⭐ Copy the product's rules put into words.
 *
 * Exported for the same reason as `RATINGS`: these are decisions, and a decision
 * that only exists in a component is one nobody reviews when the component is
 * edited. All three are **count-free** — 「一句陈述，无推送、无红点、无催促词」 —
 * which is the part most likely to be broken by a well-meaning 「还剩 N 条」.
 */
export const RECALL_EMPTY_COPY = '现在没有该复习的笔记。'
export const RECALL_ENROL_COPY = '到时候提醒我再读一遍'
export const RECALL_ENROLLED_COPY = '这条在复习队列上 —— 到时候它会自己回来找你。'

export default function RecallView({
  onDone,
}: {
  /** Called after every accepted answer, so the list can re-read itself. */
  onDone: () => void
}) {
  const [active, setActive] = useState<{ schedule: NoteSchedule; note: Note } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState('')

  const describe = useCallback(
    (cause: unknown) =>
      cause instanceof ApiError ? cause.message : '无法读取复习队列。',
    [],
  )
  const queue = useResource<NoteSchedule[]>(listDueNotes, [], describe)

  const open = useCallback(
    async (schedule: NoteSchedule) => {
      setError(null)
      try {
        setActive({ schedule, note: await getNote(schedule.note_id) })
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : '无法打开这条笔记。')
      }
    },
    [],
  )

  async function answerWith(rating: ReviewRating) {
    if (active === null || busy) return
    setBusy(true)
    setError(null)
    try {
      await reviewNote(active.schedule.note_id, rating)
      setActive(null)
      setAnswer('')
      onDone()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '记录失败。')
    } finally {
      setBusy(false)
    }
  }

  async function postpone() {
    if (active === null || busy) return
    setBusy(true)
    setError(null)
    try {
      await deferNote(active.schedule.note_id)
      setActive(null)
      setAnswer('')
      onDone()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '推迟失败。')
    } finally {
      setBusy(false)
    }
  }

  if (queue.error) {
    return (
      <p
        className="px-4 py-3 type-prose text-[color:var(--color-up)]"
        data-testid="recall-error"
 >
        {queue.error}
      </p>
    )
  }

  if (active !== null) {
    return (
      <section className="px-4 py-3" data-testid="recall-active">
        <div className="flex flex-wrap items-baseline gap-2 pb-1">
          {/* A note's title is its claim — it is the reader's own sentence about
              something, which is §2.2's 17–20 serif row, not a 15px heading. */}
          <h2 className="serif type-claim text-ink">{active.note.title}</h2>
          <span className="num ml-auto type-badge text-ink-faint">
            写于 {formatMoment(active.note.created_at)}
            {active.note.as_of ? ` · 数据截至 ${active.note.as_of}` : ''}
          </span>
        </div>

        {/*
          ⭐ The **whole** note, as source.

          The first draft of this comment proposed hiding the body and testing
          recall from the title, Anki-style. That is wrong here and the reason is
          specific rather than a preference: a note's title is not a prompt. It
          measures whether the reader can guess from their own headline, which is
          luck, not memory. A card's claim *is* a prompt, which is why the card
          review may hide it.
        */}
        {/* ⭐ **Rendered Markdown.** This was a `<pre>` of the raw body, ⭐ and the
              review screen is where a note is read most carefully — ⭐ so it is the
            worst place for a note to arrive looking like a file. ⭐ The 2px rule
        {/* ⭐ stays ⭐ and moves to `border-l-rule-soft`: ⭐ the body now has its own
            headings and lists, ⭐ and a rule around the whole thing would frame a page
            rather than mark a record. */}
        <div className="border-l-2 border-rule-soft py-2 pl-3">
          <Markdown source={active.note.body} />
        </div>

        <p className="type-prose text-ink-faint">
          这条当初是你自己说要「再看看」的。现在重读一遍，然后照实说。
        </p>

        <div className="mt-2 flex flex-wrap gap-1.5">
          {RATINGS.map((entry) => (
            <Button
              key={entry.value}
              size="sm"
              variant={entry.value === 'again' ? 'primary' : 'ghost'}
              disabled={busy}
              title={entry.hint}
              onClick={() => void answerWith(entry.value)}
              data-testid={`recall-${entry.value}`}
 >
              {entry.label}
            </Button>
          ))}
          <span className="mx-1 h-4 w-px self-center bg-rule" aria-hidden="true" />
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => void postpone()}
            data-testid="recall-defer"
 >
            还没想清楚，先放一放
          </Button>
        </div>

        {/*
          Free text is **not** sent. It would be the obvious place to record "what
          changed", and it is also a backlog: a note that asks for prose on every
          revisit becomes a thing to be cleared rather than a thing to think
          about. The answer that matters — 我的想法变了 — is the `again` button, and
          if the note really has moved, **rewriting it** is the response, which
          restarts its schedule honestly.
        */}
        <div className="mt-2">
          <Textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            rows={2}
            placeholder="想写点什么就先写在这 —— 但它不会被保存。"
            aria-label="草稿，不会保存"
            data-testid="recall-scratch"
          />
        </div>

        {error ? (
          <p
            className="mark mt-1.5 border-l-2 border-l-[color:var(--color-up)] py-1 type-prose text-[color:var(--color-up)]"
            data-testid="recall-answer-error"
 >
            {error}
          </p>
        ) : null}
      </section>
    )
  }

  if (queue.loading) {
    return (
      <p className="px-4 py-3 type-prose text-ink-faint" data-testid="recall-loading">
        读取中…
      </p>
    )
  }

  const items = queue.data ?? []
  if (items.length === 0) {
    // ⭐ **No number.** 「没有该复习的了」 says the state; 「还剩 3 条」 gives the
    // reader a tally, and a tally is something to clear.
    return (
      <section>
        <Rule />
        <p className="px-4 py-3 type-prose text-ink-soft" data-testid="recall-empty">
          现在没有该复习的笔记。
          {/*
            Saying nothing about how many notes are *waiting to be enrolled* is
            deliberate too. Enrolling is a per-note decision made where the note
            lives, and a hint here would turn "记下来的东西" into "东西还欠着".
          */}
        </p>
      </section>
    )
  }

  return (
    <section>
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="type-meta caps text-ink-faint">
          该重读的笔记
        </h2>
      </div>
      <Rule />
      {items.map((schedule) => (
        <button
          key={schedule.note_id}
          type="button"
          onClick={() => void open(schedule)}
          className="flex w-full items-baseline gap-3 border-b border-rule-soft px-4 py-2 text-left data-[motion=l1] hover:bg-paper-soft"
          data-testid="recall-item"
 >
          {/*
            ⭐ Relative, and the only number in the row. An absolute date made the
            reader subtract from today to learn what it meant.

            ⭐ And **no title**: a scannable list of things you owe is a to-do
            list, which is the one shape this product's red lines rule out. A queue
            is an information source — you are meant to be interrupted by
            something you wrote, not to work through a list.
          */}
          <span className="num shrink-0 type-meta text-ink-faint">
            {formatAgo(schedule.due_at)}
          </span>
          <span className="type-prose text-ink">
            {schedule.state === 'deferred' ? '先放一着的' : '该重读了'}
          </span>
        </button>
      ))}
    </section>
  )
}
