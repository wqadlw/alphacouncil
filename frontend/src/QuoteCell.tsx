/**
 * The row's right column: what an instrument is worth right now, or the row's
 * word for why it does not know.
 *
 * Shared by the pool page and the today page (spec 005 FR-5). Presentation
 * only — every decision about copy, tone and staleness was made by
 * `summarizeQuote`, where it is tested. Hovering holds the provenance (data
 * time and source) or the reason a number is absent; the full four-state
 * sentence lives one click away on the instrument page.
 */

import type { QuoteResult } from './api'
import { TONE_CLASS } from './format'
import { summarizeQuote } from './quoteSummary'

export default function QuoteCell({ result }: { result: QuoteResult | undefined }) {
  const cell = summarizeQuote(result)

  if (cell.note) {
    return (
      <p
        className={`shrink-0 self-center type-prose ${cell.emphasis === 'warn' ? 'text-warn' : 'text-ink-faint'}`}
        title={cell.detail ?? undefined}
 >
        {cell.note}
      </p>
    )
  }

  return (
    <div className="num shrink-0 self-center text-right" title={cell.detail ?? undefined}>
      {/* §2.2's cell row: 13 / 18. It was `text-[15px] leading-tight` — 15 is not a
          row in the table, and a pool cell is legible text rather than chrome, so
          rule 6's density licence does not apply to it. ⭐ `leading-tight` is gone
          rather than left in place: `.type-cell` declares 18px, the two are the same
          specificity, and `globals.css` comes after Tailwind's utilities, so the
          class would silently win and the utility would be a lie. */}
      <p className="type-cell">{cell.price}</p>
      <p className="type-prose">
        <span className={cell.change ? TONE_CLASS[cell.change.tone] : undefined}>
          {cell.change?.text}
        </span>
        {cell.stale && <span className="text-warn"> · 旧</span>}
      </p>
    </div>
  )
}
