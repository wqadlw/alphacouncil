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
import { useModalFocus } from '../../useModalFocus'

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

  // ⭐ **The three things a modal owes, in one place.** ⭐ This used to be three
  // effects and a `trapFocus` in this file, because that is where the missing
  // behaviour turned up. ⭐ A Drawer is a modal that arrives from the side and it
  // needs the same three things, ⭐ and 「reuse the palette's mechanism」 with the
  // mechanism inside a page-level component is copy-paste with a delay.
  useModalFocus({ open, panelRef })


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
    setQuery('')
    setSelected(0)
    // Focus after paint, so the input exists. Without the rAF the caret lands
    // before the value reset and the first keystroke is swallowed.
    const frame = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [open])

  useEffect(() => {
    setSelected(0)
  }, [query])

  if (!open) return null

  const choose = (command: Command) => {
    if (command.run) command.run()
    else if (command.href) window.location.hash = command.href
    onClose()
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
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
        // ⭐ **`tabIndex={-1}`, and the mutation check found the reason.** The
        // palette's list is either the rows or the 「没有匹配项」 paragraph, ⭐ so a
        // query with no matches can leave the panel with **one** focusable thing —
        // the input — and the hook's empty-panel branch calls `panel.focus()`.
        // ⭐ On a `div` with no `tabindex`, `focus()` is a **silent no-op**: the
        // reader is left on the page behind with the panel still open and nothing
        // looks wrong. `-1` makes the panel focusable programmatically without
        // adding it to the tab order, ⭐ which is the whole difference.
        tabIndex={-1}
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
