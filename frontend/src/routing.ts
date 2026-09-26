/**
 * Routing — two views, in the URL, with no dependency.
 *
 * The URL is a hash (`#/i/sh/600519`) rather than a path so that the whole thing
 * keeps working when the frontend is served as a static bundle with no rewrite
 * rules in front of it — which is how a desktop build ships it.
 *
 * **This is an interim answer, and it is marked as one.** The frontend spec names
 * TanStack Router alongside TanStack Query, and both belong to the same change:
 * moving off hand-rolled data fetching and hand-rolled navigation is one
 * deliberate migration of the data layer, not two half-migrations. Twenty lines
 * here are honest about being temporary; a half-installed router would not be.
 *
 * An unrecognised hash becomes `unknown` rather than falling back to the pool.
 * Silently showing the wrong page for a mistyped link is the kind of failure
 * that looks like success, which this project treats as a defect everywhere else.
 */

import { useEffect, useState } from 'react'

export type Route =
  | { name: 'pool' }
  | { name: 'instrument'; market: string; code: string }
  | { name: 'unknown'; raw: string }

const INSTRUMENT = /^#\/i\/([a-z]{2})\/([0-9]{6})$/

export function parseHash(hash: string): Route {
  if (hash === '' || hash === '#' || hash === '#/') return { name: 'pool' }
  const match = INSTRUMENT.exec(hash)
  if (match) return { name: 'instrument', market: match[1], code: match[2] }
  return { name: 'unknown', raw: hash }
}

export function instrumentHref(market: string, code: string): string {
  return `#/i/${market}/${code}`
}

export const POOL_HREF = '#/'

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return route
}
