/**
 * 「记一条教训」 — the one way a lesson comes into existence (spec 030).
 *
 * ⭐ **This is red line 7's interface, and the absence of a second control is the
 * feature.** There is no 「入队」 button here because there is no such endpoint:
 * recording a lesson writes it *and* its scheduling item in one transaction, so a
 * button here would be a control for something that cannot fail to happen. The
 * sentence under the field says so, because a reader who has just been told "it is
 * already on the queue" and cannot see any queue will reasonably wonder.
 *
 * It appears only once a review exists for the decision. That is not a UI
 * convenience — it is the server's rule (`LESSON_REVIEW_MISSING`, a 409): a lesson
 * is a statement about what a review taught you, so it has nothing to attach to
 * before the review is written, and attaching it to the *scheduled* review would
 * date it to a moment that has not happened.
 *
 * ## The collapsed state, borrowed from spec 029

 * One permanent row reading 记一条教训, expanding in place. Same reasoning as the
 * vault's 记一条: the owner's complaint was that a record function was missing, so a
 * control that has to be discovered is walking back the fix. The affordance is
 * always visible; only the form behind it is transient.
 */

import { useState } from 'react'

import { ApiError } from '../../api'
import { recordLesson, type Lesson } from '../../lessons'
import { Button, Rule, Textarea } from '../ui'

export default function LessonComposer({
  decisionId,
  onRecorded,
}: {
  decisionId: string
  onRecorded?: (lesson: Lesson) => void
}) {
  const [open, setOpen] = useState(false)
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const blank = content.trim() === ''

  async function submit() {
    if (blank || busy) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const recorded = await recordLesson(decisionId, content)
      setNotice(
        `已记下（${recorded.lesson.lesson_id}）—— 它已经在队列上，刚到期。` +
          '到时候它会自己回来找你。',
      )
      setContent('')
      onRecorded?.(recorded.lesson)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : '写入失败。')
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-5" data-testid="lesson-composer">
        <Rule />
        <div className="mt-2 flex items-baseline gap-2">
          <Button size="sm" onClick={() => setOpen(true)} data-testid="lesson-open">
            记一条教训
          </Button>
          <span className="text-[12px] text-ink-faint">
            这次复盘教出来的东西 —— 记下就入队。
          </span>
        </div>
      </div>
    )
  }

  return (
    <section className="mt-5" data-testid="lesson-composer-open-panel">
      <div className="flex items-baseline gap-2 pb-1.5">
        <h2 className="text-[11px] uppercase tracking-[0.06em] text-ink-faint">
          记一条教训
        </h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-[11px] text-ink-faint hover:text-ink-soft"
          data-testid="lesson-close"
        >
          收起
        </button>
      </div>
      <Rule />
      <div className="mt-1.5 flex flex-col gap-1.5">
        <Textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={3}
          placeholder={'正文 · 例如：\n先看批价再看渠道库存 —— 批价是先行指标'}
          aria-label="教训正文"
          data-testid="lesson-body"
        />
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            disabled={blank || busy}
            onClick={() => void submit()}
            data-testid="lesson-submit"
          >
            {busy ? '写入中…' : '记下'}
          </Button>
          <span className="text-[12px] text-ink-faint">
            {blank ? '一句话就够 —— 「下次先看批价」是可以的。' : '没有出处也能记。'}
          </span>
        </div>
      </div>

      {/*
        ⭐ The sentence that has to be here, and it is not decoration.

        There is no 「入队」 button, and a reader who has just been told the lesson
        is on the queue will look for the queue and not find a control. Saying why
        costs one line and removes the only question this screen can raise.
      */}
      <p className="mt-1 text-[12px] text-ink-faint" data-testid="lesson-auto-note">
        记下就入队 —— 这是红线 7 要求的，所以没有「入队」这个按钮可点。
        队列在知识库页的「该复习」里。
      </p>

      {error ? (
        <p
          className="mark mt-1.5 border-l-2 border-l-[color:var(--color-up)] py-1 text-[13px] text-[color:var(--color-up)]"
          data-testid="lesson-error"
        >
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          className="mark mt-1.5 border-l-2 border-l-navy py-1 text-[13px] text-navy"
          data-testid="lesson-notice"
        >
          {notice}
        </p>
      ) : null}
    </section>
  )
}
