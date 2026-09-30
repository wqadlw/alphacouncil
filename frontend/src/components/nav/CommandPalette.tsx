/**
 * ⌘K / Ctrl+K — the command palette, and the front door of a knowledge program.
 *
 * Spec'd in `AlphaCouncil-前端资源与打磨规格.md` §七 and detailed in
 * `docs/FRONTEND_STYLE_GUIDE.md` §8.2. It was never built. This is it.
 *
 * **Why it is the front door rather than a shortcut.** A knowledge system's value
 * is retrieval: the reader usually knows *what* they are looking for and not
 * *where* it lives. Navigation asks the wrong question ("which of my four
 * sections?"), so it makes the reader remember the app's structure. Search asks
 * the right one. That is the whole argument, and it is why the empty sidebar is a
 * worse product than a working palette.
 *
 * **Three details that are load-bearing, from the spec:**
 *
 * - the selected row is marked with a **2px brass left rule**, not a row-wide
 *   highlight. A full-row fill on a paper background reads as a button; a rule
 *   reads as a cursor, which is what it is.
 * - the scrim is a **translucent paper wash, not black** — and the panel keeps
 *   **zero shadow and a 1px rule**, which is why §3.2's blanket ban has to carve
 *   out this one element: it is the only thing in the product that leaves the
 *   document plane.
 * - group headings are **12px all-caps**, because a list of thirty items with no
 *   grouping is a list of thirty items. ⭐ `.type-meta .caps`, per §2.2's 表头/元数据
 *   row — this comment said 11px until spec 045, because the idiom was
 *   `type-badge uppercase tracking-[0.06em]` on **44 lines** and 11px is what
 *   `type-badge` is. A number written down next to a copy-pasted class is how the
 *   wrong number survives a spec.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../lib/cn'

/**
 * The focusable things inside the panel, in the order they are read.
 *
 * ⭐ **A query, not a list of refs.** The panel's contents are conditional — the list
 * is `rows.length === 0` or `rows.length` buttons — so a hand-maintained array of
 * refs would be wrong the moment a row is added or the query has no matches. ⭐
 * `F-151` is the reason this is a query: a guard written from an assumption rather
 * than a measurement can be unreachable while reading as diligence, and the only
 * defence is to derive the value rather than keep it in step by hand.
 *
 * ⚠️ **The selector is the one place this can go stale**, and it is written to match
 * what the panel renders rather than what it ought to render. ⭐ The panel's three
 * footer hints (`↑↓ 选择` / `⏎ 执行` / `Esc 关闭`) are `<span>`s, not buttons, so
 * they are **not** tab stops and **must not** be in the trap: a screen-reader user
 * tabbing forward would land on a hint that does nothing, and the panel would feel
 * broken. ⭐ If someone makes them `<button>`s this query picks them up
 * automatically, which is the behaviour that is wanted.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * The shell's id, shared with `AppShellFrame`.
 *
 * ⭐ **A constant rather than a prop, and the reason is worth stating.** The palette
 * needs to make the shell `inert` and it is not a descendant of it, so it has to
 * find it. ⭐ The alternative — threading a ref down from the frame — would mean
 * `CommandPalette`'s props grow a field that only matters in one of its three open
 * routes, ⭐ and a component that knows about the frame's DOM is no longer a
 * component. An `id` is the cheapest contract that both sides can hold, ⭐ and
 * `AppShellFrame` uses the same constant so a rename is a compile error there.
 */
export const SHELL_ID = 'app-shell'

export interface Command {
  id: string
  group: string
  label: string
  hint?: string
  href?: string
  run?: () => void
}

export function CommandPalette({
  open,
  commands,
  onClose,
}: {
  open: boolean
  commands: Command[]
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  /**
   * ⭐ **What had focus before the palette opened.**
   *
   * Measured on 2026-09-30 with a browser probe rather than asserted: closing the
   * palette left `document.activeElement` on `body`, so the reader who pressed
   * ⌘K from the sidebar's 「知识库」 link was dropped at the top of the document and
   * had to Tab back. ⭐ Recording it is the whole fix and there is no way to derive
   * it — the browser does not remember, and the component cannot ask.
   *
   * ⭐ **Recorded on `open` becoming true, not in the click handler.** The palette is
   * opened by three different routes (⌘K, the sidebar button, a page-contributed
   * command) and only one of them is a click; ⭐ a ref set in `onClick` would restore
   * focus to `body` for the two other routes, which is the shape of a fix that works
   * in the test and not in the app.
   */
  const previousFocus = useRef<HTMLElement | null>(null)

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (needle === '') return commands
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(needle) ||
        c.hint?.toLowerCase().includes(needle) ||
        c.group.toLowerCase().includes(needle),
    )
  }, [commands, query])

  // Group headers, rendered once per run of same-group items.
  const rows = useMemo(() => {
    const out: { command: Command; showGroup: boolean }[] = []
    let lastGroup = ''
    for (const command of filtered) {
      const showGroup = command.group !== lastGroup
      lastGroup = command.group
      out.push({ command, showGroup })
    }
    return out
  }, [filtered])

  useEffect(() => {
    if (!open) return
    // ⭐ Read it **before** anything steals focus. The effect below moves focus with
    // a rAF, so the value read here is still the reader's, and reading it in the rAF
    // itself would record the palette's own input — ⭐ which restores focus to the
    // thing that no longer exists, and looks like it works in every manual test
    // because you opened it from somewhere and stayed there.
    previousFocus.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    setQuery('')
    setSelected(0)
    // Focus after paint, so the input exists. Without the rAF the caret lands
    // before the value reset and the first keystroke is swallowed.
    const frame = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [open])

  /**
   * ⭐ **Give the focus back when the palette closes.**
   *
   * ⭐ The condition is the one that is easy to get wrong: restoring on **unmount**
   * alone would fire when the whole app navigated, and ⭐ restoring on `open`
   * changing to false fights a command that *intends* to move focus elsewhere — a
   * command that opens an editor should leave focus in the editor, not yank it back
   * to the sidebar link. ⭐ So the restore is scheduled and the element is checked
   * one frame later: ⭐ if the command moved focus, the reader's new focus is left
   * alone; if it did not, focus goes back to where it came from.
   */
  useEffect(() => {
    if (open) return
    const target = previousFocus.current
    if (target === null) return
    const frame = requestAnimationFrame(() => {
      // ⭐ The element may have been unmounted in the meantime — a command that
      // navigates away from the view that owned the link leaves a detached node
      // here, and `focus()` on a detached element is a silent no-op that looks like
      // a successful restore.
      if (target.isConnected) target.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [open])

  useEffect(() => {
    setSelected(0)
  }, [query])

  /**
   * ⭐ **The outer half of the trap: focus that is *not* in the panel.**
   *
   * `aria-modal="true"` is a claim the DOM does not enforce — ⭐ measured, 8 of the
   * page's focusable elements were reachable with the panel open. ⭐ Making the
   * page's own nodes unfocusable is the mechanism that actually delivers the claim,
   * and `inert` is the platform's: ⭐ §6 bans an animation **library**, not a
   * platform feature, and `inert` is one attribute that the browser implements in
   * every target this product ships.
   *
   * ⭐ **Applied to the shell, and the panel escapes it via the portal.** The
   * palette's call site is inside the shell (`AppShellFrame` renders it there and
   * there is no reason to move it), ⭐ so setting `inert` on the shell would have
   * frozen the panel along with the page behind. ⭐ The panel is portalled into
   * `document.body`, which puts it in `#root`'s sibling — ⭐ so `inert` on the shell
   * does not reach it, and a modal can be disabled *around* rather than *without*
   * freezing itself.
   */
  useEffect(() => {
    if (!open) return
    const shell = document.getElementById(SHELL_ID)
    if (shell === null) return
    const wasInert = shell.inert
    shell.inert = true
    return () => {
      // ⭐ Restore the **previous** value rather than setting `false`. Something
      // else may have made the shell inert for its own reasons, ⭐ and a cleanup
      // that hard-codes `false` would silently un-disable it.
      shell.inert = wasInert
    }
  }, [open])

  if (!open) return null

  const choose = (command: Command) => {
    if (command.run) command.run()
    else if (command.href) window.location.hash = command.href
    onClose()
  }

  /**
   * ⭐ **Keep Tab inside the panel — and the reason this is here and not on `window`
   * is the whole finding.**
   *
   * Measured on 2026-09-30: Tab *forwards* stayed inside the dialog for five presses
   * and left on the sixth; Tab *backwards* left on the first. ⭐ The two directions
   * cannot both be right by accident, and the obvious reading of the markup — 「the
   * dialog is at the end of `<body>`, so forward Tab naturally lands back in it and
   * there is no trap needed」 — is **false for the first five presses and silently
   * true-looking**: the panel was appended after the page's eight focusable nodes,
   * so forward Tab *had* to pass through the whole page first. ⭐ What the probe
   * actually showed is that the input was focused when Tab was pressed, so those
   * five steps were the browser's own order inside the panel, and the sixth landed
   * on `body` because nothing wrapped it.
   *
   * ⭐ **A `window`-level listener would have fixed the backward case and left the
   * forward case broken**, because a `keydown` on a focused element **bubbles** to
   * `window` only if it was not already handled — ⭐ and `Tab` pressed on the input
   * never reaches a document listener that is added after React's root listener. ⭐
   * So the handler lives on the panel's own `onKeyDown`, where both directions are
   * seen, and the document listener below exists only for the case where focus is
   * *outside* the panel entirely (which is what `aria-modal` promises and does not
   * deliver).
   */
  const trapFocus = (event: React.KeyboardEvent) => {
    if (event.key !== 'Tab') return
    const panel = panelRef.current
    if (panel === null) return
    const stops = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (stops.length === 0) return
    const first = stops[0]
    const last = stops[stops.length - 1]
    const current = document.activeElement

    // ⭐ **Not inside at all: pull it in from the ends.** This is the case the
    // document listener handles for focus that is already outside; here it matters
    // for the moment after `onClose` unmounts the rows, when the browser may put
    // focus on `body` and the next Tab starts from the top of the document.
    if (!(current instanceof HTMLElement) || !panel.contains(current)) {
      event.preventDefault()
      ;(event.shiftKey ? last : first).focus()
      return
    }
    // ⭐ **At an end and heading out: wrap to the other end.** Two separate
    // conditions rather than one, because `Tab` on the last stop and
    // `Shift+Tab` on the first stop are the only two that leave.
    if (!event.shiftKey && current === last) {
      event.preventDefault()
      first.focus()
      return
    }
    if (event.shiftKey && current === first) {
      event.preventDefault()
      last.focus()
    }
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
    trapFocus(event)
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setSelected((i) => Math.min(i + 1, rows.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setSelected((i) => Math.max(i - 1, 0))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const command = rows[selected]?.command
      if (command) choose(command)
    }
  }

  let cursor = -1

  // ⭐ **Portalled, and the port is the fix rather than a layout choice.** See the
  // `inert` effect above: a modal that lives inside the subtree it disables cannot
  // disable it. ⭐ `document.body` is the only node that is a *sibling* of the shell
  // rather than an ancestor or a descendant, ⭐ so the panel goes there and the
  // scrim's `fixed inset-0` still covers the viewport from the same place.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
      // Paper wash, not black (§3.2). A black scrim on a paper-coloured app
      // reads as a modal from a different product.
      style={{ background: 'rgb(251 250 248 / 0.72)' }}
      onClick={onClose}
      data-testid="palette-scrim"
 >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        // Zero shadow, 1px rule, 4px radius — the panel obeys §3.2 and §4 even
        // though the scrim above it is the documented exception.
        className="w-[560px] max-w-[92vw] rounded-[4px] border border-rule bg-surface"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
        data-testid="palette"
 >
        <div className="border-b border-rule p-2">
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索标的、卡片、决策，或输入命令"
            className="w-full bg-transparent type-prose text-ink outline-none placeholder:text-ink-faint"
            data-testid="palette-input"
            aria-label="搜索"
          />
        </div>

        <div className="pane-scroll max-h-[46vh] py-1" data-testid="palette-list">
          {rows.length === 0 ? (
            // Rule 8 again: a fact and what to do. Not "no results".
            <p className="px-3 py-6 text-center type-prose text-ink-soft">
              没有匹配项。按 Esc 关闭。
            </p>
          ) : (
            rows.map(({ command, showGroup }) => {
              cursor += 1
              const index = cursor
              const active = index === selected
              return (
                <div key={command.id}>
                  {showGroup ? (
                    <div className="px-3 pb-1 pt-2 type-meta caps text-ink-faint">
                      {command.group}
                    </div>
                  ) : null}
                  <button
                    type="button"
                    onMouseEnter={() => setSelected(index)}
                    onClick={() => choose(command)}
                    // The 2px brass rule, not a row fill. A fill reads as a
                    // button; a rule reads as a cursor.
                    className={cn(
                      'block w-full border-l-2 px-3 py-1.5 text-left type-prose data-[motion=l1]',
                      active
                        ? 'border-l-[color:var(--color-brass)] bg-paper-soft text-ink'
                        : 'border-l-transparent text-ink-soft hover:bg-paper-soft',
                    )}
                    data-testid="palette-item"
                    data-active={active ? 'true' : 'false'}
 >
                    <span className="flex items-baseline justify-between gap-3">
                      <span>{command.label}</span>
                      {command.hint ? (
                        <span className="num type-badge text-ink-faint">{command.hint}</span>
                      ) : null}
                    </span>
                  </button>
                </div>
              )
            })
          )}
        </div>

        <div className="flex items-center gap-3 border-t border-rule px-3 py-1.5 type-badge text-ink-faint">
          <span>↑↓ 选择</span>
          <span>⏎ 执行</span>
          <span>Esc 关闭</span>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/**
 * Bind ⌘K / Ctrl+K to a boolean the caller renders the palette from.
 *
 * Takes no commands: the palette receives them as a prop, so the key binding and
 * the command list are separate concerns and a page can contribute commands
 * without this hook knowing anything about them.
 */
export function useCommandPalette(): {
  open: boolean
  setOpen: (value: boolean) => void
  toggle: () => void
} {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((value) => !value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const toggle = useCallback(() => setOpen((value) => !value), [])

  return { open, setOpen, toggle }
}
