/**
 * The recall queue's copy decisions (spec 028), asserted against the real strings.
 *
 * Two of the three decisions this feature makes live in **wording**, and wording is
 * exactly what gets "improved" later by someone who has not read why it was chosen.
 * So the sentences themselves are pinned — imported from the component, not copied
 * here, because a contract test that hard-codes the value it is checking stays green
 * when the button is reworded.
 *
 * The third — that the queue renders no count — is an E2E assertion, because only a
 * rendered page can prove a number is absent.
 */
import { describe, expect, it } from 'vitest'
import {
  RATINGS,
  RECALL_EMPTY_COPY as EMPTY_COPY,
  RECALL_ENROLLED_COPY as ENROLLED_COPY,
  RECALL_ENROL_COPY as ENROL_COPY,
} from './components/knowledge/RecallView'

describe('the recall queue copy (spec 028)', () => {
  it('again means my view has moved, and never that I forgot', () => {
    const again = RATINGS.find((r) => r.value === 'again')
    expect(again?.label).toBe('我的想法变了')

    // ⭐ The words that would make it a failure, checked as substrings so a
    // reword cannot slip past. For a *card*, `again` does mean the claim could
    // not be recalled; for a note it means the author's thinking has moved past
    // what they wrote — the signal that this note should be rewritten, marked, or
    // let converge. Labelling it a lapse teaches the reader to avoid the most
    // honest answer available.
    for (const forbidden of ['忘', '失败', '重来', '错误', 'fail', 'again', 'Forgot']) {
      expect(again?.label, `「${again?.label}」里出现了「${forbidden}」`).not.toContain(
        forbidden,
      )
    }
  })

  it('the scale reads as one question rather than a score', () => {
    // A scale whose bottom rung is a failure and whose top rung is 「太熟了」 is
    // measuring confidence; this one asks 「这条还成立吗?」.
    expect(RATINGS.map((r) => r.value)).toEqual(['again', 'hard', 'good', 'easy'])
    for (const entry of RATINGS) {
      expect(entry.label.length).toBeGreaterThan(2)
      expect(entry.hint.length).toBeGreaterThan(2)
    }
  })

  it('the empty queue says the state and gives no tally', () => {
    // ⭐ No digits. 「还剩 3 条」 turns a state into a score to clear, which is what
    // 「一句陈述，无推送、无红点、无催促词」 rules out.
    expect(EMPTY_COPY).not.toMatch(/[0-9]/)
    for (const forbidden of ['剩', '还有', '共', '条待']) {
      expect(EMPTY_COPY, `空状态文案里出现了「${forbidden}」`).not.toContain(forbidden)
    }
  })

  it('enrolment is offered as a decision, not reported as a debt', () => {
    // ⭐ Also digit-free. The vault never counts how many notes are *not*
    // enrolled, because computing it would mean inventing a tally in order to
    // refuse to show it.
    expect(ENROL_COPY).not.toMatch(/[0-9]/)
    expect(ENROLLED_COPY).not.toMatch(/[0-9]/)
    // ⭐ Only the words that signal a **debt**. 「条」 was in the first draft and
    // had to come out: it is the classifier a tally uses, and it is also the word
    // in 「这条在复习队列上」, which is the sentence I want. A keyword list written by
    // listing cannot see which meaning it is looking at. The tally case itself is
    // covered precisely by the digit assertion above — 「还剩 3 条」 needs a number
    // to exist, and that is the thing being checked.
    for (const forbidden of ['欠', '还没', '待办', '未读']) {
      expect(ENROL_COPY, `入队按钮里出现了「${forbidden}」`).not.toContain(forbidden)
      expect(ENROLLED_COPY, `已入队提示里出现了「${forbidden}」`).not.toContain(forbidden)
    }
  })
})
