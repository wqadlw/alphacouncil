/**
 * The application shell and the handful of shared pieces every page was
 * rewriting.
 *
 * ## Why the shell exists
 *
 * Until this, `src/*.tsx` contained **no `<nav>` at all**: six pages each imported
 * a different `HREF` constant and hand-wrote a "← back to X" link, and the only way
 * to reach any view was to type its hash. That is not a missing feature, it is a
 * missing frame — and it is why the retrospective page shipped with no way in.
 *
 * ## ⭐ The shell may not contain a digit, and that is not a style choice
 *
 * Three E2E specs assert on the **whole page body**:
 *
 * - `retrospective.spec.ts` — in the dangerous quadrant the page contains **no
 *   digit at all** (red line 10, strongest form)
 * - `review.spec.ts` — the page contains no `%`, `正确率`, `记住率`, `掌握度`,
 *   `评分`, `得分` (red line 9)
 * - `today.spec.ts` — the page contains no `收益率`
 *
 * A nav bar is part of the body, so **every label here is digit-free and uses none
 * of those words** — including `评分`, which is why the process score is called
 * 过程分 everywhere and never 评分. `TestTheNavCarriesNoCounters` in
 * `e2e/nav.spec.ts` holds this.
 *
 * ## ⭐ The nav carries no counts, deliberately
 *
 * `项目总纲` §2.1⑤ specifies, for the moment a user would rather not look: "一句陈述，
 * 无推送、无红点、无催促词". A badge reading 复习 3 turns "you owe three cards" into a
 * number you can see, keep, and try to climb — which is red line 11 (不鼓励频繁操作)
 * wearing a helpful little badge.
 *
 * So how many are waiting is answered **by the page you land on**, in a sentence,
 * and not by the nav bar advertising it in advance. A count *inside* the review or
 * retrospective page is fine and already there: it is a fact about the queue once
 * you have chosen to look.
 *
 * ## The deliberate plainness
 *
 * Skeleton instead of spinner, no animation, no shadows, no theme switch.
 * `ReviewPage` established this ("financial software does not animate") and the
 * shell follows it rather than introducing a second visual language.
 */

import type { ReactNode } from 'react'
import { activeHref, ROUTES, useRoute } from './routing'

/**
 * The persistent frame: a nav, and the page content below it.
 *
 * Rendered once by `App`, so navigating between views does not tear down the
 * frame — and so a reader who lands deep in a hash route (a shared link, a
 * bookmark) is not stranded with no way out.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const route = useRoute()
  const current = activeHref(route)

  return (
    <div className="min-h-screen">
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-[860px] flex-wrap items-baseline gap-x-6 gap-y-1 px-8 py-3">
          {/*
            The wordmark is a link home rather than a logo, because the product has
            no brand to render yet and a dead-end header is worse than a plain one.
          */}
          <a href="#/" className="serif text-[15px] text-ink no-underline">
            AlphaCouncil
          </a>
          <nav className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]" data-testid="nav">
            {ROUTES.map((entry) => {
              const active = entry.href === current
              return (
                <a
                  key={entry.href}
                  href={entry.href}
                  aria-current={active ? 'page' : undefined}
                  data-testid={`nav-${entry.label}`}
                  data-active={active ? 'true' : 'false'}
                  className={
                    active
                      ? 'text-ink underline underline-offset-4'
                      : 'text-ink-soft no-underline hover:text-ink hover:underline'
                  }
                >
                  {entry.label}
                </a>
              )
            })}
          </nav>
        </div>
      </header>
      <main>{children}</main>
    </div>
  )
}

/**
 * The page frame. Every view used to repeat this exact class string, six times,
 * which meant a width change was six edits and five of them were easy to miss.
 */
export function Page({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-[720px] px-8 py-10">{children}</div>
}

/** A wider frame for the two list-shaped pages that carry tables. */
export function WidePage({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-[860px] px-8 py-10">{children}</div>
}

/**
 * The loading state, shared so it is identical everywhere.
 *
 * A skeleton, not a spinner, and deliberately static: this is software people
 * stare at while markets are open.
 */
export function PageSkeleton({ label }: { label?: string }) {
  return (
    <Page>
      <div className="h-6 w-40 bg-rule" role="status" aria-label={label ?? '读取中'} />
    </Page>
  )
}

/** A failure, stated as a sentence the reader can act on. */
export function ErrorNote({ message }: { message: string }) {
  return (
    <p className="text-ink-soft" data-testid="error-note">
      {message}
    </p>
  )
}

/**
 * The empty state: what is empty, why, and a way out.
 *
 * Every empty state in the app has all three parts, and the "why" is the one that
 * gets skipped — an empty list that does not say why it is empty is the same as a
 * broken one.
 */
export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: { href: string; label: string }
}) {
  return (
    <div data-testid="empty-state">
      <h1 className="serif text-[26px] leading-tight">{title}</h1>
      <p className="mt-2 text-ink-soft">{body}</p>
      {action ? (
        <p className="mt-4">
          <a href={action.href} className="text-navy">
            ← {action.label}
          </a>
        </p>
      ) : null}
    </div>
  )
}

/** Re-exported so a page can build a nav without importing the table directly. */
export { ROUTES }
