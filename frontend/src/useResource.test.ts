import { describe, expect, it } from 'vitest'
import { type DescribeError, type LoadState, RequestRunner } from './useResource'

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
    const pending = runner.run(() => Promise.resolve('ok'), describeError)
    expect(last().loading).toBe(true)
    await pending
    expect(last()).toEqual({ data: 'ok', error: null, loading: false })
    expect(states).toHaveLength(2)
  })

  it('reports a failure and stops loading', async () => {
    const { runner, last } = harness()
    await runner.run(() => Promise.reject(new Error('nope')), describeError)
    expect(last()).toEqual({ data: null, error: 'nope', loading: false })
  })

  it('runs the caller’s error describer', async () => {
    const { runner, last } = harness()
    await runner.run(
      () => Promise.reject('a bare string'),
      () => '说人话',
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
    await runner.run(() => Promise.resolve('first'), describeError)
    await runner.run(() => Promise.reject(new Error('nope')), describeError)
    expect(last()).toEqual({ data: 'first', error: 'nope', loading: false })
  })

  it('clears a previous failure when a later run succeeds', async () => {
    const { runner, last } = harness()
    await runner.run(() => Promise.reject(new Error('nope')), describeError)
    await runner.run(() => Promise.resolve('ok'), describeError)
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

    const slow = runner.run(() => first.promise, describeError)
    const fast = runner.run(() => second.promise, describeError)

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

    const slow = runner.run(() => first.promise, describeError)
    const fast = runner.run(() => second.promise, describeError)

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

    const slow = runner.run(() => first.promise, describeError)
    const fast = runner.run(() => second.promise, describeError)

    first.resolve('row-a')
    await slow
    expect(states[states.length - 1].loading).toBe(true)

    second.resolve('row-b')
    await fast
    expect(states[states.length - 1]).toEqual({ data: 'row-b', error: null, loading: false })
  })
})
