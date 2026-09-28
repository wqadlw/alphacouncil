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
 * - group headings are **uppercase 11px**, because a list of thirty items with no
 *   grouping is a list of thirty items.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '../../lib/cn'

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

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]"
      // Paper wash, not black (§3.2). A black scrim on a paper-coloured app
      // reads as a modal from a different product.
      style={{ background: 'rgb(251 250 248 / 0.72)' }}
      onClick={onClose}
      data-testid="palette-scrim"
    >
      <div
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
            className="w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-faint"
            data-testid="palette-input"
            aria-label="搜索"
          />
        </div>

        <div className="pane-scroll max-h-[46vh] py-1" data-testid="palette-list">
          {rows.length === 0 ? (
            // Rule 8 again: a fact and what to do. Not "no results".
            <p className="px-3 py-6 text-center text-[13px] text-ink-soft">
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
                    <div className="px-3 pb-1 pt-2 text-[11px] uppercase tracking-[0.06em] text-ink-faint">
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
                      'block w-full border-l-2 px-3 py-1.5 text-left text-[13px] data-[motion=l1]',
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
                        <span className="num text-[11px] text-ink-faint">{command.hint}</span>
                      ) : null}
                    </span>
                  </button>
                </div>
              )
            })
          )}
        </div>

        <div className="flex items-center gap-3 border-t border-rule px-3 py-1.5 text-[11px] text-ink-faint">
          <span>↑↓ 选择</span>
          <span>⏎ 执行</span>
          <span>Esc 关闭</span>
        </div>
      </div>
    </div>
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
