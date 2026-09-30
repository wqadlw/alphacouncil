/**
 * The three-pane shell: sidebar · list · detail.
 *
 * This is the answer to "a knowledge program is not a stack of pages". A program
 * has a **frame that persists** and **content that changes inside it**; a website
 * has a sequence of pages that each replace the whole window. The practical
 * consequences, all of which are the reason for the layout rather than decoration:
 *
 * - the reader never loses their place, because the sidebar and the list stay;
 * - the list and the detail scroll **independently** (`globals.css`
 *   `.pane-scroll`), so a 400-row log and a long record can sit side by side;
 * - every entity is reachable from **one** place — the ⌘K palette — rather than
 *   from a hierarchy the reader has to remember.
 *
 * The sidebar is **search-first, not navigation-first**, and the order reflects
 * that: the search box is at the top, above the sections. A knowledge system
 * lives on retrieval; navigation is the fallback for when you *don't* know what
 * you are looking for.
 *
 * ⭐ **No count badges on the nav.** `项目总纲` §2.1⑤ wants "一句陈述，无推送、
 * 无红点、无催促词" and red line 11 forbids check-in counters. A number beside a
 * nav item is the same thing wearing a smaller hat — it is asserted by
 * `e2e/nav.spec.ts`, which fails if a digit appears here.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { CommandPalette, useCommandPalette, SHELL_ID, type Command } from '../components/nav/CommandPalette'
import { Input, Rule } from '../components/ui'
import { Icon } from '../components/ui/Icon'
import { ROUTES, type RouteName } from '../routing'
import { cn } from '../lib/cn'

export interface ShellProps {
  route: RouteName | 'instrument' | 'unknown'
  instrument: { market: string; code: string } | null
  /** Extra commands contributed by the current page (entities, actions). */
  commands?: Command[]
  /**
   * The middle pane. `list` wins when given; otherwise the frame falls back to
   * its children, so a page can be written as ordinary JSX and still land inside
   * the frame without knowing the frame exists.
   */
  list?: ReactNode
  children?: ReactNode
  /** The right pane. Omitted on pages that are a single column. */
  detail?: ReactNode
  /** Shown instead of the list while it loads. */
  listSkeleton?: ReactNode
  listLoading?: boolean
  /** The page's own heading, rendered in the list pane's header. */
  title: string
  subtitle?: ReactNode
}

export function AppShellFrame({
  route,
  instrument,
  commands = [],
  list,
  children,
  detail,
  listSkeleton,
  listLoading,
  title,
  subtitle,
}: ShellProps) {
  const [query, setQuery] = useState('')
  const { open: paletteOpen, setOpen: setPaletteOpen, toggle: togglePalette } =
    useCommandPalette()

  const openPalette = useCallback(() => setPaletteOpen(true), [setPaletteOpen])

  const allCommands = useMemo<Command[]>(
    () => [
      ...ROUTES.map((entry) => ({
        id: `nav-${entry.name}`,
        group: '去往',
        label: entry.label,
        hint: entry.href,
        href: entry.href,
      })),
      ...commands,
    ],
    [commands],
  )

  // ⌘K, plus `/` as a second front door: typing a slash is faster than a chord
  // on the machines this ships to, and it is the convention the reader already
  // has from every other tool they use. An effect, not a memo — this registers a
  // listener, and a memo would re-run the cleanup on every render without ever
  // re-reading the deps, which is how you get a listener that fires twice.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing =
        target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
      if (!typing && event.key === '/') {
        event.preventDefault()
        togglePalette()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [togglePalette])

  const active = instrument
    ? ''
    : ROUTES.find((entry) => entry.name === route)?.href ?? ''

  return (
    // ⭐ **`id` as well as `data-testid`, and the two are not redundant.**
    // `CommandPalette` sets `inert` on this element while it is open, so that Tab
    // cannot reach the eight focusable things on the page behind. ⭐ That requires
    // finding the node from outside, and an `id` is the contract both files can
    // hold — ⭐ `SHELL_ID` is exported from the palette and used here, so a rename
    // is a type error in this file rather than a runtime no-op.
    <div className="flex h-full flex-col" id={SHELL_ID} data-testid="app-shell">
      {/* ── Top bar: identity, the search front door, the palette hint ─────── */}
      <header className="flex shrink-0 items-center gap-4 border-b border-rule bg-surface px-4 py-2">
        <a href="#/" className="serif type-claim text-ink no-underline" data-testid="brand">
          AlphaCouncil
        </a>
        <div className="relative max-w-[420px] flex-1">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={openPalette}
            readOnly
            placeholder="搜索标的、卡片、决策…"
            className="cursor-text pr-14 text-ink-faint"
            aria-label="搜索"
            data-testid="search-box"
          />
          <kbd className="num pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 type-badge text-ink-faint">
            ⌘K
          </kbd>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* ── Sidebar: navigation. Persistent, and the fallback, not the door ─ */}
        <nav
          className="w-[176px] shrink-0 border-r border-rule bg-paper-soft/40 py-3"
          aria-label="主导航"
          data-testid="nav"
 >
          <div className="px-3 pb-1 type-meta caps text-ink-faint">
            视图
          </div>
          {ROUTES.map((entry) => {
            const isActive = entry.href === active
            return (
              <a
                key={entry.href}
                href={entry.href}
                aria-current={isActive ? 'page' : undefined}
                data-testid={`nav-${entry.label}`}
                data-active={isActive ? 'true' : 'false'}
                className={cn(
                  // 2px left rule for selection, matching the table and the
                  // palette. Three places now use the same mark, which is what
                  // makes it read as a system rather than a set of decisions.
                  'flex items-center gap-2 border-l-2 px-3 py-1.5 type-prose no-underline data-[motion=l1]',
                  isActive
                    ? 'border-l-[color:var(--color-brass)] text-ink'
                    : 'border-l-transparent text-ink-soft hover:text-ink',
                )}
 >
                {/* Icon, at sm, and text-ink-faint while inactive.

                    sm because 14px is the tier §5 assigns to a glyph this small,
                    and the sidebar column is 176px. ink-faint because the glyph is
                    the LEAST important thing in the row - it repeats the label that
                    sits beside it - so it must not draw the eye off the words. That
                    is 规则 7 again, about contrast rather than hue: an icon at full
                    ink competes with a 13px label it is merely annotating. */}
                <Icon name={entry.icon} size="sm" className="text-ink-faint" />
                {entry.label}
              </a>
            )
          })}
        </nav>

        {/* ── List pane ────────────────────────────────────────────────────── */}
        <section className="flex min-w-0 flex-1 flex-col" aria-label={title}>
          <div className="shrink-0 border-b border-rule bg-surface px-4 py-2.5">
            {/* Serif, because this is a title (rule 1) — 17px, because a pane
                header is a label on a region rather than the document's main
                heading. The product's own spec asks for 22/30 on a page title;
                that was written when a page filled the window. In a three-pane
                frame the title labels a pane, and a 26px serif over a 400-row
                table is the layout this spec exists to replace. */}
            {/* ⭐ The page title, at the size §2.2 gives it: 22 / 30 serif. It was
          `text-[17px] leading-tight` — the **only** `text-[17px]` in the tree, five
          pixels under its own row, and the single reason a screenshot of any page
          looked like a panel header rather than the top of a document. */}
      <h1 className="serif type-page-title text-ink">{title}</h1>
            {subtitle ? <div className="mt-0.5 type-meta text-ink-soft">{subtitle}</div> : null}
          </div>
          <div className="pane-scroll min-h-0 flex-1">
            {listLoading && listSkeleton ? listSkeleton : (list ?? children)}
          </div>
        </section>

        {/* ── Detail pane ───────────────────────────────────────────────────── */}
        {detail ? (
          <section
            className="flex min-w-0 flex-1 flex-col border-l border-rule bg-surface/60"
            aria-label="详情"
            data-testid="detail-pane"
 >
            <div className="pane-scroll min-h-0 flex-1">{detail}</div>
          </section>
        ) : null}
      </div>

      {/* ⭐ **Still rendered here, and the portal is what makes that correct.**
          `CommandPalette` portals its panel into `document.body`, ⭐ so although this
          call site is lexically inside the shell, the DOM lands it as a **sibling** of
          `#root` — ⭐ which is why the `inert` the palette sets on the shell does not
          freeze the palette. ⭐ Moving the call to `App` would have been the obvious
          refactor and would have changed nothing: the portal decides where the node
          ends up, not where it was written. */}
      <CommandPalette
        open={paletteOpen}
        commands={allCommands}
        onClose={() => setPaletteOpen(false)}
      />
    </div>
  )
}

export { Rule }
