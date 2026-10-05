/**
 * ⭐⭐⭐ **The demo banner: the one sentence that makes demo data impossible to mistake
 * for your own records.** (spec 057)
 *
 * ## Why it exists, measured
 *
 * ```
 *   the reader's own database, 2026-10-05:
 *     instruments 2 · watchlist_events 8 · decisions 5
 *     cards 0 · notes 0 · reviews 0 · lessons 0
 * ```
 *
 * ⭐ **The knowledge layer is empty**, and that layer is the whole difference between this
 * product and a P&L log — an external survey found the English trading-journal category is
 * P&L-first *by construction*, so the three queues that make this one different opened
 * empty every day, **not because they are broken but because there had never been anything
 * to review.**
 *
 * `dev.py demo` fills that. ⭐ **And a demo that looks exactly like real data is worse than
 * no demo at all**, because someone will eventually read its decisions as their own.
 *
 * ## What this sentence is, and is not
 *
 * - ✅ A **fact**: this is not your library.
 * - ⭐ **No digits** — 「5 张卡片」 is a number *about the reader* (red line 11), and a banner
 *   is the worst place to introduce one because it is the first thing on screen.
 * - ⭐ **No 「欢迎」** — that is reassurance, and red line 13 says the product does not
 *   reassure. It states the situation and stops.
 * - ⭐ **No 「import into my library」** — that would be a road from *fabricated* decisions to
 *   the reader's own record, and red lines 3/13/15 plus `agent-guide.md`'s
 *   「不替用户写决策记录」 exist to close exactly that road.
 *
 * ## ⚠️ This is the second of three layers, and the weakest guarantee of the three
 *
 * 1. the demo library lives in a **subdirectory** (`demo/`) — a prompt;
 * 2. **this banner** — a prompt;
 * 3. ⭐ `alphacouncil.demo.refuse_to_overwrite` — **raises** rather than warns.
 *
 * Only the third fails loudly when someone forgets. Two prompts, one guarantee, because an
 * environment variable can be forgotten and a filename can be renamed
 * (`spec 057` §2.1).
 */

import { useEffect, useState } from 'react'

import { getCapabilities, type CapabilitiesRead } from './api'

/**
 * Ask the server whether this is the demo library.
 *
 * ⭐ **One request at boot, and the docstring on the server field used to claim it was
 * free.** Measured: the interface has **no consumer of `/api/v1/capabilities` at all**, so
 * that claim was invented. ⇒ It costs one small request, and the field's description now
 * says so.
 *
 * ⚠️ **A failure is not a banner and not its absence.** If the request fails we render
 * nothing: ⭐ **「I could not check whether this is the demo」 is not a sentence a reader
 * should have to read**, and the guarantee is the server refusing to seed the real path
 * anyway. A blank here means 「nothing was claimed」, not 「it is safe to assume real」 —
 * which is why the server field, not this component, is where the refusal lives.
 */
export function DemoBanner() {
  const [isDemo, setIsDemo] = useState(false)

  useEffect(() => {
    let live = true
    getCapabilities()
      .then((caps: CapabilitiesRead) => {
        if (live) setIsDemo(caps.is_demo)
      })
      .catch(() => {
        // See the docstring: silence here is the honest rendering of 「did not find out».
      })
    return () => {
      live = false
    }
  }, [])

  if (!isDemo) return null

  return (
    // ⚠️ `role="status"` rather than `role="alert"`: an alert announces itself to a screen
    // reader on every render, and this banner appears on every page. It is a standing fact,
    // not an interruption. (`role="alert"` is for things that need acting on now.)
    <div
      role="status"
      data-testid="demo-banner"
      // A 2px top rule in `--color-warn`, not a colour fill. Rule 5: a category is marked
      // with a rule, and 规则 7 means colour must carry meaning — ⭐ this one means
      // 「nothing here is yours」, which is a meaning, and the only one on this page.
      className="border-t-2 border-t-[color:var(--color-warn)] bg-paper-soft px-4 py-1.5 type-meta text-ink-soft"
    >
      这是演示库。你的记录不在这里。
    </div>
  )
}
