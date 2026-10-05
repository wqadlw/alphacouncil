/**
 * One place for the four states every fetch has.
 *
 * ## What this replaced
 *
 * Six pages each carried their own copy of the same fifteen lines: a `data` state,
 * a `loading` boolean, an `error` string, a `useCallback` that resets all three, and
 * a `useEffect` that calls it. Across the app that was roughly **35 hand-written
 * `setLoading` / `setError` call sites**, each one a place where the three states
 * could fall out of step — a page that clears the error but not the data, or
 * forgets the `finally` and spins forever after a failure.
 *
 * ## ⭐ It also removes the lint warnings, and that is a correctness argument
 *
 * Every page's load effect called `setState` synchronously inside the effect body,
 * which `react-hooks` flags as `set-state-in-effect` (six warnings, all of them
 * real: an extra render pass on every load). Here the state is set **inside the
 * async continuation**, so the effect itself only starts the request. The warning
 * goes away because the cascade was genuinely unnecessary, not because it was
 * suppressed.
 *
 * ## ⭐ Stale responses are discarded
 *
 * A page that changes what it is looking at — a different card, a different
 * decision — can have two requests in flight. Whichever answers *last* wins, which
 * is how a fast second request gets overwritten by a slow first one and the page
 * shows the wrong row. `RequestRunner` holds a generation counter so the older
 * response becomes a no-op.
 *
 * This is not hypothetical: the instrument and retrospective pages both refetch on
 * a changing id.
 *
 * ## Why the state machine is not a hook
 *
 * The generation counter is the only genuinely subtle thing here, and it is
 * **time-based** — nothing about it needs React. So it lives in `RequestRunner`,
 * a plain class, and `useResource` is a thin binding of it to `useState`.
 *
 * That split is not architecture for its own sake: this repo has **no DOM
 * environment in vitest** (no jsdom, and adding one is a new dependency the
 * constitution does not permit without approval), so a hook could not be tested at
 * all. The part worth testing is now testable, and `useResource.test.ts` drives
 * two concurrent requests and settles them **out of order** — which is the only
 * way to prove the counter works.
 *
 * ## What this deliberately does not do
 *
 * **No cache, and no cross-page invalidation bus.** Nothing writes from one view
 * and reads in another yet, so a shared cache would be an abstraction built for a
 * requirement that does not exist — and `reload()` already covers every call site
 * today. When the today page becomes the hub (spec 023) and genuinely needs
 * invalidation, that is when the bus gets built, with a caller in hand.
 */

import { useCallback, useEffect, useState } from 'react'

/** What a caller can be told about a request, as it happens. */
export interface LoadState {
  data: unknown
  error: string | null
  loading: boolean
}

export type DescribeError = (cause: unknown) => string

/**
 * Owns the in-flight generation counter.
 *
 * Every `run` claims the next generation; a response whose generation is no
 * longer current is dropped **silently** rather than reported, because it is not
 * an error — it is the answer to a question the caller has already moved on from.
 */
export class RequestRunner {
  #generation = 0

  readonly #publish: (state: LoadState) => void

  constructor(publish: (state: LoadState) => void) {
    this.#publish = publish
  }

  async run<T>(fetcher: () => Promise<T>, describe: DescribeError): Promise<void> {
    const mine = ++this.#generation
    // `data` is deliberately *not* cleared: a page showing an error above the
    // content it already has is more useful than one that blanks, and the red
    // lines treat "we could not reach the source" as its own state rather than as
    // "there is no data" (constitution 4.6, four states).
    this.#publish({ data: this.#last?.data ?? null, error: null, loading: true })
    try {
      const value = await fetcher()
      if (this.#generation !== mine) return
      this.#last = { data: value, error: null, loading: false }
      this.#publish(this.#last)
    } catch (cause: unknown) {
      if (this.#generation !== mine) return
      this.#last = { data: this.#last?.data ?? null, error: describe(cause), loading: false }
      this.#publish(this.#last)
    }
  }

  #last: LoadState | null = null
}

export interface Resource<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

export function useResource<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
  describeError: DescribeError,
): Resource<T> {
  // One runner per hook instance, held in a ref so a re-render reuses it — and so
  // the generation counter survives renders, which is the entire point.
  const holder = useRunnerHolder()
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true })
  holder.runner = holder.runner ?? new RequestRunner(setState)

  // ⭐⭐ **`describeError` is read through a ref, exactly like `fetcher`, and until
  // spec 055 it was not.** The comment inside the effect below explains why `fetcher` is
  // deliberately excluded from the deps — it is rebuilt on every render. ⭐
  // `describeError` has the same property whenever a caller passes an inline arrow, and it
  // **was** in the deps, so `run()` → `publish()` → render → new arrow → `run()` … is an
  // infinite loop.
  //
  // ⚠️ **It cost two E2E tests a 30-second timeout each and said nothing about why.** The
  // line, list and JSON reporters all printed only 「Test timeout of 30000ms exceeded」 —
  // no stack, no line, no assertion. ⭐ The cause was found by bisecting the change
  // (`git stash` on one file) rather than by reading any reporter. `F-250`.
  //
  // ⇒ So both arguments the caller passes *for the hook's own use* are now excluded from
  // the deps, and `deps` is once again the only thing that re-runs a request. ⭐ **That is
  // the contract this hook's own header already described** — the code now matches the
  // documentation instead of the other way round.
  const describeRef = useLatest(describeError)

  useEffect(() => {
    void holder.runner?.run(fetcher, (cause) => describeRef.current(cause))
    // `fetcher` is rebuilt every render, so it is deliberately not a dependency;
    // `deps` is the caller's statement of what actually changes the request. The
    // generation counter is what makes that safe — a superseded request's answer is
    // dropped, so re-running on every render would only waste requests, not
    // corrupt state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps])

  const reload = useCallback(() => {
    void holder.runner?.run(fetcher, (cause) => describeRef.current(cause))
  }, [holder, fetcher, describeRef])

  return {
    data: (state.data as T | null) ?? null,
    error: state.error,
    loading: state.loading,
    reload,
  }
}

/**
 * A mutable box created once per component instance.
 *
 * `useRef` would do, but this reads more plainly at the two use sites and avoids
 * the `useRef<T>()`-is-null-until-first-render question entirely.
 */
function useRunnerHolder(): { runner: RequestRunner | null } {
  const [box] = useState(() => ({ runner: null as RequestRunner | null }))
  return box
}

/**
 * Keep the newest value without making it a dependency.
 *
 * ⚠️ **A `useState` box rather than `useRef`,** for the same reason as `useRunnerHolder`:
 * the initialiser runs once, so the value is never null on the first render and there is
 * no `useRef<T>()` question for a caller to answer. ⭐ The box is written during render,
 * which is sound here because the value is only ever *read* later — inside an effect or a
 * callback — and never during render.
 */
function useLatest<T>(value: T): { current: T } {
  const [box] = useState(() => ({ current: value }))
  box.current = value
  return box
}

/** The submitting half: a flag, a failure, and a runner. */
export interface Submit {
  submitting: boolean
  error: string | null
  run: <T>(action: () => Promise<T>) => Promise<T | null>
  clearError: () => void
}

export function useSubmit(describeError: DescribeError): Submit {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(
    async <T,>(action: () => Promise<T>): Promise<T | null> => {
      setSubmitting(true)
      setError(null)
      try {
        return await action()
      } catch (cause: unknown) {
        setError(describeError(cause))
        return null
      } finally {
        setSubmitting(false)
      }
    },
    [describeError],
  )

  const clearError = useCallback(() => setError(null), [])

  return { submitting, error, run, clearError }
}
