/**
 * Browse the lessons, and sign one as a card.
 *
 * ⭐ **Why a list at all.** The only place a lesson was visible before this was the
 * recall queue — which shows the ones that came back. But **promotion is not tied to
 * being due**: a lesson you wrote last month and have not been asked about yet is
 * exactly the one most likely to be ready to sign, because you have had time to sit
 * with it. ⭐ So a queue cannot be the place to promote from, and that is not a gap in
 * the queue — it is the queue refusing to do a job that is not its job.
 *
 * The vault already has one view per kind of thing, so a 教训 view is where a reader
 * looks. And the client already had `listLessons` and `promoteLesson` — the API was
 * finished in `502e7f1`; only the surface was missing.
 *
 * ## What the form is
 *
 * Two fields, both required: a link and its title. ⭐ That is not friction, it is the
 * product. A card's provenance is a URL and a lesson has none, so this is where the
 * reader says 「这条我现在愿意署名，出处是……」 — and a reader who cannot says nothing
 * and keeps the lesson, which is already saved and already on its own queue. ⭐ The
 * refusal costs nothing, which is what makes declining a reasonable answer rather
 * than a failure, and the server's 400 says exactly that in as many words.
 *
 * So the form has **no 「skip」 button and no empty-state escape hatch** beyond
 * closing it. Closing *is* the skip.
 *
 * ## What is not here
 *
 * * **No edit, no delete.** A lesson is immutable (spec 030 §2.1), and the whole
 *   no-`reset` argument for the queue rests on it. A reader who disagrees writes
 *   another lesson.
 * * **No count.** A tally of how many lessons you have is a number you can start
 *   climbing.
 * * **No 「再转一次」.** `lesson_promotions.lesson_id` is the table's primary key, so a
 *   second promotion is impossible in the database; showing a control for it would be
 *   showing a button that can only fail.
 */

import { useCallback, useState } from 'react'

import { ApiError } from '../../api'
import { listLessons, promoteLesson, type Lesson } from '../../lessons'
import { formatMoment } from '../../format'
import { Badge, Button, Input, Rule } from '../ui'
import { useResource } from '../../useResource'

export default function LessonList() {
  const describe = useCallback(
    (cause: unknown) => (cause instanceof ApiError ? cause.message : '无法读取教训。'),
    [],
  )
  const rows = useResource<Lesson[]>(listLessons, [], describe)
  const [promoting, setPromoting] = useState<string | null>(null)
  const [done, setDone] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  async function promote(lessonId: string, url: string, title: string) {
    setPromoting(lessonId)
    setError(null)
    try {
      const promotion = await promoteLesson(lessonId, { url, title })
      setDone((previous) => ({ ...previous, [lessonId]: promotion.card_id }))
      await rows.reload()
    } catch (cause) {
      // ⭐ The server's 400 text is the product copy — 「拿不出出处就说明这条还只是
      // 一条教训 —— 它已经记下来了，不会丢」 — so it is shown verbatim rather than
      // replaced with a generic message. Rewriting it here would throw away the one
      // sentence that makes declining feel safe.
      setError(cause instanceof ApiError ? cause.message : '转卡失败。')
    } finally {
      setPromoting(null)
    }
  }

  if (rows.error) {
    return (
      <p
        className="px-4 py-3 text-[13px] text-[color:var(--color-up)]"
        data-testid="lesson-list-error"
      >
        {rows.error}
      </p>
    )
  }

  const items = rows.data ?? []

  if (items.length === 0) {
    return (
      <div data-testid="lesson-list-empty">
        <Rule />
        <p className="px-4 py-3 text-[13px] text-ink-soft">
          还没有教训。
        </p>
        <p className="px-4 pb-3 text-[12px] text-ink-faint">
          在复盘页写完一条复盘之后，下面会出现「记一条教训」。
        </p>
      </div>
    )
  }

  return (
    <section className="mt-3" data-testid="lesson-list">
      <div className="flex items-baseline gap-2 px-4 pb-1.5">
        <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">教训</h2>
      </div>
      <Rule />
      <ul>
        {items.map((lesson) => {
          const cardId = done[lesson.lesson_id]
          return (
            <li
              key={lesson.lesson_id}
              className="border-b border-rule-soft px-4 py-3 last:border-b-0"
              data-testid="lesson-row"
            >
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink">
                {lesson.content}
              </p>
              <p className="num mt-1 text-[11px] text-ink-faint">
                写于 {formatMoment(lesson.created_at)}
              </p>

              {/*
                ⭐ **No second 「转成卡片」 once one exists.** The two UNIQUE
                constraints on `lesson_promotions` make a repeat impossible in the
                database, so a control for it would only ever produce a failure. What
                replaces it is a statement of what happened.
              */}
              {cardId ? (
                <p className="mt-2" data-testid="lesson-promoted">
                  <Badge>已经是卡片了</Badge>
                  <span className="num ml-1 text-[11px] text-ink-faint">{cardId}</span>
                </p>
              ) : (
                <PromoteForm
                  busy={promoting === lesson.lesson_id}
                  onSubmit={(url, title) => void promote(lesson.lesson_id, url, title)}
                />
              )}
            </li>
          )
        })}
      </ul>
      {error ? (
        <p className="px-4 py-2 text-[12px] text-ink-soft" data-testid="lesson-promote-error">
          {error}
        </p>
      ) : null}
    </section>
  )
}

/**
 * The two required fields, and the button that stays disabled until both are there.
 *
 * ⭐ **Closing this form is the skip, and that is deliberate.** There is no 「以后再说」
 * and no empty state to click through, because a reader who cannot supply a source has
 * not got a card — they have got a lesson, which is already saved and already on its
 * own queue. The absence of a button is the accurate rendering of that.
 */
/**
 * ⭐ **No `lesson` prop.** The first version took the whole row and read none of it —
 * the id lives in the parent, which owns the mutation. `TS6133` caught it because
 * this file is under `--strict`.
 *
 * ⭐ That is ``F-54``'s speculative flexibility arriving through a prop instead of an
 * argument: it reads as plumbing, and it is the same defect. A JavaScript file would
 * have carried it indefinitely.
 */
function PromoteForm({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (url: string, title: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')

  const ready = url.trim() !== '' && title.trim() !== ''

  if (!open) {
    return (
      <div className="mt-2">
        <Button size="sm" onClick={() => setOpen(true)} data-testid="lesson-promote-open">
          转成卡片
        </Button>
      </div>
    )
  }

  return (
    <div className="mt-2 flex flex-col gap-1.5" data-testid="lesson-promote-form">
      <p className="text-[12px] text-ink-faint">
        转成卡片要给出处 —— 一个链接和它的标题。拿不出出处就说明这条还只是一条教训，
        而它已经在这里了。
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          size="sm"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="出处链接 · https://"
          aria-label="出处链接"
          className="w-[260px]"
          data-testid="lesson-source-url"
        />
        <Input
          size="sm"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="出处标题"
          aria-label="出处标题"
          className="w-[200px]"
          data-testid="lesson-source-title"
        />
        <Button
          variant="primary"
          size="sm"
          disabled={!ready || busy}
          onClick={() => onSubmit(url.trim(), title.trim())}
          data-testid="lesson-promote-submit"
        >
          {busy ? '写入中…' : '署名'}
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-[11px] text-ink-faint hover:text-ink-soft"
          data-testid="lesson-promote-cancel"
        >
          先不转
        </button>
      </div>
    </div>
  )
}
