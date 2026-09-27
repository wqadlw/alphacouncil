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
        className={`shrink-0 self-center text-[13px] ${cell.emphasis === 'warn' ? 'text-warn' : 'text-ink-faint'}`}
        title={cell.detail ?? undefined}
      >
        {cell.note}
      </p>
    )
  }

  return (
    <div className="num shrink-0 self-center text-right" title={cell.detail ?? undefined}>
      <p className="text-[15px] leading-tight">{cell.price}</p>
      <p className="text-[12px] leading-tight">
        <span className={cell.change ? TONE_CLASS[cell.change.tone] : undefined}>
          {cell.change?.text}
        </span>
        {cell.stale && <span className="text-warn"> · 旧</span>}
      </p>
    </div>
  )
}
