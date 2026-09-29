/**
 * The sentence one due kill criterion makes (spec 040).
 *
 * ## ⭐ Five sentences, and the last three are the feature
 *
 * Before spec 040 there was one: 「你写的失效条件「…」观察期已到 —— 去核实数据。」
 * The system had no metric source, so it had adjudicated nothing, and the sentence said
 * exactly that.
 *
 * Now it does adjudicate, and the page owes the reader **five** distinct sentences.
 * Three of them say **we cannot tell you**:
 *
 * | state | who is speaking |
 * |---|---|
 * | `crossed` / `not_crossed` | the comparison, over the reader's own threshold |
 * | `warming` | ⭐ us — the metric is too young, and here is how many bars are missing |
 * | `undetermined` | ⭐ us — the catalogue has never heard of this metric |
 * | `no_bars` | ⭐ us — the source has nothing for this instrument |
 *
 * ⭐ **Collapsing the last three into 「条件没成立」 would be the most misleading thing
 * this product could do**, because the reader would take it as news about their own
 * judgement. The condition did not fail to hold — it was never tested. Red line 6 in
 * constitution §4.6: 「把『无法判断』降级成『看起来合理』的默认值」.
 *
 * ## ⭐ `crossed` is the only state allowed to say 已触发
 *
 * The old test pinned 「已触发」 as a string that must **never** appear, and the reason it
 * recorded was 「the system has no metric source and has decided nothing」. That reason is
 * gone, so the assertion is gone with it — ⭐ **not because it became inconvenient, but
 * because the fact it rested on stopped being true.** A test whose reason has expired
 * should be deleted, not preserved as a superstition.
 *
 * ## 红线 13: `not_crossed` must not read as relief
 *
 * 「没越过」 is a fact and stops there. It is not 「还好」, it is not a green tick, and it
 * says nothing about whether the reader's judgement was good. ⭐ Dressing it as comfort
 * is the same move as a 成绩 badge (红线 9), wearing a different hat.
 */

import type { MetricReading } from './api'

/** A number with the precision a price needs and an indicator does not. */
function formatValue(value: number): string {
  // ⭐ Integers print as integers. `1235.5800000001` in a sentence about the reader's own
  // money reads as a precision the data does not have, and invites them to distrust the
  // rest of the number.
  return Number.isInteger(value) ? value.toLocaleString('en-US') : value.toFixed(2)
}

export interface CriterionSentence {
  /** The clause that replaces 「去核实数据」. */
  verdict: string
  /** ⭐ `true` only when the comparison actually ran. Drives the row's accent colour. */
  crossed: boolean
  /**
   * ⭐ Whether the reader is being told something they could act on today. `false` for the
   * three 「we don't know」 states, and the row is styled to say so.
   */
  adjudicable: boolean
}

export function criterionVerdict(metric: MetricReading | null | undefined): CriterionSentence {
  // ⭐ No bars at all is checked before anything else, and it is its own sentence. It is
  // not 「the metric is unknown」 — the catalogue may well know the metric perfectly well,
  // and there was simply nothing to compute it from.
  //
  // ⭐ `undefined` is accepted alongside `null` on purpose. The server sends
  // `metric: null` when it has no bars, and the type says so — but a payload from a build
  // that predates spec 040 simply has no such key, and `metric.state` on `undefined`
  // throws **during render**, which white-screens the one page the reader opens to find
  // out what went wrong. ⭐ Every other 「we don't know」 in this product costs the reader
  // a sentence; this one would have cost them the page.
  if (metric === null || metric === undefined) {
    return {
      verdict: '观察期已到 —— 但取不到这个代码的日线，这条判据没有被求值过。',
      crossed: false,
      adjudicable: false,
    }
  }

  switch (metric.state) {
    case 'crossed':
      return {
        // ⭐ 「已越过」 not 「已触发」, and the value is right there. The reader wrote the
        // threshold; the page is reporting the comparison they asked for, not rendering a
        // verdict on their position.
        verdict: `已越过 —— ${metric.label} 现在 ${formatValue(metric.value as number)}${
          metric.as_of === null ? '' : `（${metric.as_of}）`
        }。`,
        crossed: true,
        adjudicable: true,
      }
    case 'not_crossed':
      return {
        // ⭐ No adjective. 「没有越过」 and stops. Not relief, not a warning, and
        // emphatically not a comment on the decision.
        verdict: `没有越过 —— ${metric.label} 现在 ${formatValue(metric.value as number)}${
          metric.as_of === null ? '' : `（${metric.as_of}）`
        }。`,
        crossed: false,
        adjudicable: true,
      }
    case 'warming': {
      // ⭐ The count is the whole reason this sentence is worth having. 「还在预热」 alone
      // is a dead end; 「还差 48 根」 tells the reader this resolves on its own, which is
      // the difference between a deferral and a shrug.
      //
      // ⭐ `bars_available` is sent by the server rather than derived here. The first
      // draft counted calendar days minus weekends in TypeScript — ⭐ which is spec 038's
      // mistake one layer down: a quantity the server knows exactly, recomputed in a
      // second language, wrong by the number of public holidays. A promise of 「还差 N 根」
      // that is short by three days is a promise the page does not keep.
      const missing =
        metric.bars_available === null
          ? null
          : Math.max(0, (metric.period ?? 0) - metric.bars_available)
      return {
        verdict:
          missing === null || missing === 0
            ? `观察期已到 —— ${metric.label} 还没有值，这条判据没有被求值过。`
            : `观察期已到 —— ${metric.label} 还差 ${missing} 根日线才有值，这条判据暂时没有被求值。`,
        crossed: false,
        adjudicable: false,
      }
    }
    case 'undetermined':
      return {
        // ⭐ The metric name is quoted back **as typed**, because the whole point is that
        // we do not recognise it. Rendering a catalogue label here would imply we do.
        verdict: `观察期已到 —— 「${metric.label}」不在我们能算的指标里，这条判据没有被求值过。`,
        crossed: false,
        adjudicable: false,
      }
    case 'no_bars':
      return {
        verdict: '观察期已到 —— 这个代码没有日线，这条判据没有被求值过。',
        crossed: false,
        adjudicable: false,
      }
  }
}
