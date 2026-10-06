import { describe, expect, it } from 'vitest'
import {
  type DescribeError,
  type LoadState,
  RequestRunner,
  resourceKey,
} from './useResource'

/**
 * The data layer stands in for six pages' worth of removed boilerplate, so these
 * tests carry the weight the boilerplate used to.
 *
 * They drive `RequestRunner` directly rather than the React hook, and that is a
 * constraint turned into an advantage: this repo has **no DOM environment in
 * vitest** (no jsdom, and adding one is a new dependency the constitution does not
 * permit without approval), so a hook could not be rendered in a test at all. What
 * is actually subtle — which of two concurrent answers wins — is plain state
 * management and needs no renderer.
 *
 * The last two tests are the ones that matter. Settling two requests **out of
 * order** is the only way to prove the generation counter does something; a test
 * that resolves them in order would pass against an implementation with no counter
 * at all.
 */

const describeError: DescribeError = (cause) =>
  cause instanceof Error ? cause.message : 'failed'

/** A promise plus the handles to settle it later, for ordering races. */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** A runner plus the log of everything it published, in order. */
function harness() {
  const states: LoadState[] = []
  const runner = new RequestRunner((state) => states.push(state))
  return { runner, states, last: () => states[states.length - 1] }
}

describe('RequestRunner', () => {
  it('starts loading and settles with the data', async () => {
    const { runner, states, last } = harness()
    const pending = runner.run(() => Promise.resolve('ok'), describeError, 'k')
    expect(last().loading).toBe(true)
    await pending
    expect(last()).toEqual({ data: 'ok', error: null, loading: false })
    expect(states).toHaveLength(2)
  })

  it('reports a failure and stops loading', async () => {
    const { runner, last } = harness()
    await runner.run(() => Promise.reject(new Error('nope')), describeError, 'k')
    expect(last()).toEqual({ data: null, error: 'nope', loading: false })
  })

  it('runs the caller’s error describer', async () => {
    const { runner, last } = harness()
    await runner.run(
      () => Promise.reject('a bare string'),
      () => '说人话',
      'k',
    )
    expect(last().error).toBe('说人话')
  })

  it('keeps the data it already had when a later run fails', async () => {
    /**
     * Deliberate: a page showing an error *above* content it already has is more
     * useful than one that blanks. Blanking also destroys the only copy of the
     * list the reader was reading when the connection blipped.
     */
    const { runner, last } = harness()
    await runner.run(() => Promise.resolve('first'), describeError, 'k')
    await runner.run(() => Promise.reject(new Error('nope')), describeError, 'k')
    expect(last()).toEqual({ data: 'first', error: 'nope', loading: false })
  })

  it('clears a previous failure when a later run succeeds', async () => {
    const { runner, last } = harness()
    await runner.run(() => Promise.reject(new Error('nope')), describeError, 'k')
    await runner.run(() => Promise.resolve('ok'), describeError, 'k')
    expect(last()).toEqual({ data: 'ok', error: null, loading: false })
  })
})

describe('RequestRunner discards a superseded answer', () => {
  it('does not let a slow first run overwrite a fast second one', async () => {
    /**
     * The bug the generation counter exists for. Two requests in flight; the
     * second answers first and is the answer the page wants; then the first — for
     * a row the reader has already moved away from — answers and overwrites it.
     * Without the counter the page silently shows the wrong card and nothing in
     * the console says so.
     */
    const first = deferred<string>()
    const second = deferred<string>()
    const { runner, last } = harness()

    const slow = runner.run(() => first.promise, describeError, 'k')
    const fast = runner.run(() => second.promise, describeError, 'k')

    second.resolve('row-b')
    await fast
    expect(last().data).toBe('row-b')

    // The older answer arrives late and must be ignored.
    first.resolve('row-a')
    await slow
    expect(last().data).toBe('row-b')
  })

  it('does not let a superseded failure clobber fresh data', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const { runner, last } = harness()

    const slow = runner.run(() => first.promise, describeError, 'k')
    const fast = runner.run(() => second.promise, describeError, 'k')

    second.resolve('row-b')
    await fast

    first.reject(new Error('stale failure'))
    await slow
    expect(last()).toEqual({ data: 'row-b', error: null, loading: false })
  })

  it('a superseded run does not even end the newer one’s loading flag', async () => {
    /**
     * The subtle one. A late `finally`-equivalent from the abandoned request would
     * otherwise set `loading: false` while the request the page is actually
     * waiting on is still in flight — so the skeleton would vanish and the page
     * would show an empty list as though that were the answer.
     */
    const first = deferred<string>()
    const second = deferred<string>()
    const { runner, states } = harness()

    const slow = runner.run(() => first.promise, describeError, 'k')
    const fast = runner.run(() => second.promise, describeError, 'k')

    first.resolve('row-a')
    await slow
    expect(states[states.length - 1].loading).toBe(true)

    second.resolve('row-b')
    await fast
    expect(states[states.length - 1]).toEqual({ data: 'row-b', error: null, loading: false })
  })
})

/**
 * The resource boundary, which is the half the generation counter could not see.
   *
   * Measured 2026-10-06: the pool page links to an instrument with a plain
   * `<a href="#/i/sh/000001">`. That changes the hash and does not reload, so the
   * instrument page re-rendered with new `market` / `code` and kept showing the
   * previous instrument's name, follow reason, decisions, cards and history.
   *
   * Two runs with the same resource may share content. Two runs with different
   * resources may not. Every test in this block removes one line of the
   * implementation and must go red — see `.ai/regressions/` for the recorded run.
   */
  describe('RequestRunner across a change of resource', () => {
    it('does not republish the previous resource while the new one loads', async () => {
      const { runner, last } = harness()

      await runner.run(() => Promise.resolve('600519 的记录'), describeError, 'sh/600519')
      expect(last().data).toBe('600519 的记录')

      // The reader clicks the other row in the pool. No reload: the hash changes.
      const pending = runner.run(() => Promise.resolve('000001 的记录'), describeError, 'sz/000001')

      expect(last().loading).toBe(true)
      expect(last().data).toBeNull()

      await pending
      expect(last().data).toBe('000001 的记录')
    })

    it('does not fall back to the previous resource when the new one fails', async () => {
      /**
       * The nastier half. Clearing on load is not enough on its own: if the new
       * request fails and the runner republishes `#last`, the previous instrument
       * is back — this time with an error message attached, which reads as "this
       * company's record could not be read" rather than as "that is the wrong
       * company". A wrong answer labelled as a failure is still a wrong answer.
       */
      const { runner, last } = harness()

      await runner.run(() => Promise.resolve('600519 的记录'), describeError, 'sh/600519')
      await runner.run(() => Promise.reject(new Error('取不到')), describeError, 'sz/000001')

      expect(last()).toEqual({ data: null, error: '取不到', loading: false })
    })

    it('still keeps the content on screen when the same resource fails again', async () => {
      /**
       * The benefit the old code had for the wrong reason, now kept for the right
       * one: a reload is the same question asked again, so a blip must not destroy
       * the list the reader was reading.
       */
      const { runner, last } = harness()

      await runner.run(() => Promise.resolve('关注池'), describeError, 'sh/600519')
      await runner.run(() => Promise.reject(new Error('nope')), describeError, 'sh/600519')

      expect(last()).toEqual({ data: '关注池', error: 'nope', loading: false })
    })

    it('going back to a resource starts empty rather than restoring it', async () => {
      /**
       * Worth pinning because "keep a small per-resource cache" is the obvious
       * next idea and it is a different decision. This runner holds one resource,
       * so returning to the first one is a fresh load, not a restore.
       */
      const { runner, last } = harness()

      await runner.run(() => Promise.resolve('A'), describeError, 'a')
      await runner.run(() => Promise.resolve('B'), describeError, 'b')
      const pending = runner.run(() => Promise.resolve('A again'), describeError, 'a')

      expect(last().data).toBeNull()
      await pending
      expect(last().data).toBe('A again')
  })
})

describe('resourceKey', () => {
  it('separates the primitive dependencies every call site actually passes', () => {
    expect(resourceKey(['sh', '600519'])).not.toBe(resourceKey(['sh', '000001']))
    expect(resourceKey(['sh', '600519'])).toBe(resourceKey(['sh', '600519']))
    expect(resourceKey([])).toBe(resourceKey([]))
  })

  it('does not confuse a different order', () => {
    // Not a promise the hook needs, but a true one: `[tag, query]` and
    // `[query, tag]` are different resources, and a set-like key would lose that.
    expect(resourceKey(['a', 'b'])).not.toBe(resourceKey(['b', 'a']))
  })

  it('collapses objects, and that is the documented limit of the contract', () => {
    /**
     * `String(deps)` would make this worse: every object is `[object Object]`.
     * `JSON.stringify` at least separates objects that differ, so the failure is
     * narrow — two objects with identical contents look like one resource. That
     * is a documented contract, not an accident, and this test is what makes it
     * executable rather than a claim in a comment.
     */
    expect(resourceKey([{ code: '600519' }])).toBe(resourceKey([{ code: '600519' }]))
    expect(resourceKey([{ code: '600519' }])).not.toBe(resourceKey([{ code: '000001' }]))
  })

  it('reports a value with no stable serialisation instead of hiding it', () => {
    // A function serialises to null, so two different functions collide.
    expect(resourceKey([() => 1])).toBe(resourceKey([() => 2]))
    // And a symbol at the top level would make JSON.stringify return undefined.
    // deps is always an array, so the key is always a string — pinned here
    // because that is the property `run` relies on for its `!==` comparison.
    expect(typeof resourceKey([undefined, null, 0, ''])).toBe('string')
  })
})
