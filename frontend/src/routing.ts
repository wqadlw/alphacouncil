/**
 * Routing — one table, and everything else derived from it.
 *
 * **Why a table and not a bigger if-chain.** Before this there were three places
 * that each had to learn about a new page: `parseHash` (an if-chain), a
 * `HREF` constant, and a nested ternary computing `document.title`. Adding a
 * view meant editing all three, and **missing one produced no error at all** — a
 * page you cannot reach, with a title borrowed from another page. That is exactly
 * the failure this project treats as a defect everywhere else: it looks like it
 * worked.
 *
 * So `ROUTES` below is the only place a view is declared. Navigation, hash
 * parsing, page titles and the `HREF` constants are all read off it, and adding a
 * view is one entry.
 *
 * **The URL is a hash** (`#/i/sh/600519`) rather than a path, because the whole
 * thing ships as a static bundle with no rewrite rules in front of it — which is
 * how a desktop build loads it. SSR is explicitly out (constitution §3), so
 * Next.js is excluded, and the routing layer stays small enough to read.
 *
 * **An unrecognised hash becomes `unknown`** rather than falling back to today.
 * Silently showing the wrong page for a mistyped link is the kind of failure
 * that looks like success, and the backend reports an ambiguous ticker instead of
 * picking a market for you for the same reason.
 *
 * **The nav is generated from this table, and it carries no counts.** See
 * `ui.tsx` for why: `项目总纲` §2.1⑤ asks for "一句陈述，无推送、无红点、无催促词",
 * and a badge on a nav item turns "you owe three cards" into a number you can
 * see and climb.
 */

import { useEffect, useState } from 'react'

// ⭐ Type-only, so `routing.ts` does not pull the icon table (and therefore
// `lucide-react`) into every module that reads a route. ⭐ `import type` matters
// here beyond tidiness: this module is imported by `AppShellFrame`, the palette and
// `api.ts`-adjacent code, and a value import would make the 4236-icon barrel a
// dependency of the routing layer for every consumer.
import type { IconName } from './components/ui/Icon'
import type { QueueName } from './api'

/**
 * A view the app can be on. Instrument pages are parsed, not enumerated.
 *
 * ⚠️ **This union is a second declaration of what `ROUTES` already says**, and it
 * is the one place the "the table is the single source of truth" claim can leak.
 * Adding a row to `ROUTES` without adding the member here fails the build with
 * `Type '"vault"' is not assignable to type 'RouteName'` — which is loud and
 * immediate, and is the reason it has stayed correct for four specs.
 * Deriving it (`(typeof ROUTES)[number]['name']`) would remove the possibility,
 * but it also makes `RouteName` depend on declaration order, and the explicit
 * union is the one line a reader can check by eye.
 */
export type RouteName = 'today' | 'pool' | 'review' | 'retrospective' | 'vault'

export interface RouteDef {
  /**
   * The union member this view parses to.
   *
   * Written out rather than derived from `href` by slicing off `#/`: for the today
   * page that slice yields `''`, not `'today'`, and a name is not recoverable from
   * a string that happens to share a prefix with it. Deriving it looked clever
   * and was wrong in exactly one case — which is the worst ratio of cleverness to
   * bugs.
   */
  name: RouteName
  href: string
  /** Short label. **No digits, ever** — see `ui.tsx`. */
  label: string
  /** `document.title` suffix. Also digit-free. */
  title: string
  /**
   * ⭐ The nav glyph, by its **product** name rather than Lucide's — so this file
   * reads 「复盘 = retrospective」 and not 「复盘 = History」. See `ui/Icon.tsx` for why
   * the registry is keyed by meaning.
   *
   * ⭐ It lives here rather than in `AppShellFrame` because `ROUTES` is already the
   * **single declaration of what a view is** (see this file's header), and a second
   * table pairing names to glyphs would be the same fact in two homes — with the
   * failure mode that someone adds a view, updates the nav, forgets the glyph table,
   * and the row renders with a blank square.
   */
  icon: IconName
}

/**
 * Every enumerated view, in the order the nav shows them.
 *
 * The order is not alphabetical and not historical: it goes **from the general to
 * the specific**, with the two queues last because they are where the user lands
 * when something has come due — which is the point of the product.
 */
export const ROUTES: readonly RouteDef[] = [
  { name: 'today', href: '#/', label: '今天', title: '今天', icon: 'today' },
  { name: 'pool', href: '#/pool', label: '关注池', title: '关注池', icon: 'pool' },
  { name: 'review', href: '#/review', label: '复习', title: '复习', icon: 'review' },
  {
    name: 'retrospective',
    href: '#/retrospective',
    label: '复盘',
    title: '复盘',
    icon: 'retrospective',
  },
  { name: 'vault', href: '#/vault', label: '知识库', title: '知识库', icon: 'vault' },
]

/**
 * Where the app is.
 *
 * Carries the **name only** for enumerated views, not the whole `RouteDef`: the
 * definition is looked up from `ROUTES` when something needs a label or a title,
 * and duplicating it into every parsed route would be two copies of the same
 * fact — one of which could be edited without the other.
 */
export type Route =
  | { name: RouteName }
  | { name: 'instrument'; market: string; code: string }
  | { name: 'unknown'; raw: string }

const INSTRUMENT = /^#\/i\/([a-z]{2})\/([0-9]{6})$/

const BY_HREF = new Map(ROUTES.map((route) => [route.href, route]))
const BY_NAME = new Map(ROUTES.map((route) => [route.name, route]))

export function parseHash(hash: string): Route {
  // `#`, `` and `#/` all mean today, and `#/` is the canonical spelling — so the
  // table stores that one form and the other two are normalised onto it before
  // lookup. Without that, the nav would not light up on `#` and `#/`.
  const normalised = hash === '' || hash === '#' ? '#/' : hash
  const known = BY_HREF.get(normalised)
  if (known) return { name: known.name }
  const match = INSTRUMENT.exec(hash)
  if (match) return { name: 'instrument', market: match[1], code: match[2] }
  return { name: 'unknown', raw: hash }
}

export function instrumentHref(market: string, code: string): string {
  return `#/i/${market}/${code}`
}

/** The table entry behind an enumerated route name. */
export function definitionFor(name: RouteName): RouteDef {
  const found = BY_NAME.get(name)
  if (found === undefined) {
    // Unreachable while the table and the `RouteName` union agree, and the throw
    // is the point: if someone adds a union member without a table entry, this
    // fires at import in every test rather than rendering a dead link.
    throw new Error(`no route table entry for ${name}`)
  }
  return found
}

/**
 * The nav href that should read as "you are here", or `''` when none applies.
 *
 * A named helper rather than an inline check, because the union has **three**
 * members and excluding one leaves the other two — so TypeScript cannot narrow it
 * and the property access does not compile. Naming the "none of them" case once is
 * clearer than a cast.
 *
 * An instrument page has no nav entry, and an unknown address deliberately has
 * **no active item either**: lighting one up would claim the app knows where it
 * is when it has just said it does not.
 */
export function activeHref(route: Route): string {
  return route.name === 'instrument' || route.name === 'unknown'
    ? ''
    : definitionFor(route.name).href
}

export function titleFor(route: Route): string {
  switch (route.name) {
    case 'instrument':
      return `${route.code}.${route.market.toUpperCase()}`
    case 'unknown':
      return '这个地址看不懂'
    default:
      return definitionFor(route.name).title
  }
}

/**
 * Named hrefs, **derived from the table** rather than typed out.
 *
 * They stay exported because call sites read better as `TODAY_HREF` than as
 * `ROUTES[0].href` — but there is now only one place a value can come from, so
 * the two can never drift.
 */
export const TODAY_HREF = definitionFor('today').href
export const POOL_HREF = definitionFor('pool').href
export const REVIEW_HREF = definitionFor('review').href
export const RETROSPECTIVE_HREF = definitionFor('retrospective').href

/**
 * Map a server-side **queue name** to the view that shows it.
 *
 * The API sends `cards` / `reviews`, not paths, on purpose (spec 023): a URL in a
 * response would be a second copy of the route table, and the two would
 * eventually disagree. So the mapping lives here, next to the table it derives
 * from, and the server is left with no opinion about where anything lives.
 *
 * ⭐⭐ **The union is declared once, in `api.ts`, and imported here** — spec 049 measured
 * the import graph rather than deciding by preference: `api.ts` imports **nothing**,
 * `routing.ts` already imports an icon, and `TodayPage` imports from both. ⇒ `api.ts` is
 * the leaf, so converging *into* it is the direction that does not make a cycle.
 *
 * ⚠️ **Spec 049 §2.6 said converge into `routing.ts`, and the measurement said
 * otherwise.** The plan's version was written before the graph was read, and it would
 * have made `api.ts` import `routing.ts` — the direction that produces a cycle.
 * A plan is a prediction; a measurement is not (`regressions/0017`).
 *
 * Exhaustive over `QueueName` **by construction** — and ⭐ **now it actually is.** The
 * first version of this comment promised a compile error when a queue is added without a
 * route here, and the code was a ternary:
 * `queue === 'cards' ? REVIEW_HREF : RETROSPECTIVE_HREF`.
 * ⚠️ **A ternary over a union is not exhaustive**, so the promise was `regressions/0005`
 * in a comment — a document asserting something the code did not do. ⇒ a
 * `Record<QueueName, string>` makes adding a value to the union a real compile error.
 */
export type { QueueName } from './api'

const QUEUE_HREF: Record<QueueName, string> = {
  cards: REVIEW_HREF,
  reviews: RETROSPECTIVE_HREF,
}

export function queueHref(queue: QueueName): string {
  return QUEUE_HREF[queue]
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return route
}
