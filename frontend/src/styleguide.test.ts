/**
 * The style guide's acceptance list, as tests.
 *
 * `docs/FRONTEND_STYLE_GUIDE.md` §10 lists V-01 … V-08. Written as prose they
 * are intentions, and intentions do not fail a build — which is how the twelve
 * specified components (§8) came to be **zero** built while the document that
 * asked for them sat in the repo looking authoritative.
 *
 * So this file makes each item something a run has to pass. Two of them
 * (V-01, V-02) are the load-bearing ones: they are the rules whose violation is
 * invisible in review and obvious in a screenshot — a 6px radius reads as
 * "polished" until you notice the whole app is now a SaaS admin panel, and a
 * `box-shadow` reads as "subtle depth" until you notice the research report
 * grew a drop shadow.
 *
 * ## What this file deliberately does not check
 *
 * **V-03 (serif only on claims) and V-08 (empty states) are not here.** Both need
 * to know what a given piece of text *is*, and a grep cannot. A `serif` class on
 * a page title and a `serif` class on a reader's own words are the same three
 * hundred characters in the source; only a human reviewer or a page-level
 * assertion can tell them apart. Asserting them here would produce a green test
 * that proves nothing — worse than no test, because it would be cited as
 * evidence the rule holds. They stay human-review items and the guide says so.
 */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * The `src` directory, as an absolute path.
 *
 * **Was `new URL('.', import.meta.url).pathname` with a leading-slash strip, and
 * that silently resolved to nothing on Windows.** `URL.pathname` is percent-encoded
 * and always begins with `/`, so on this machine it produced
 * `/D:/AAA/.../frontend/src`; stripping the slash left `D:/AAA/.../frontend/src`,
 * which is an *absolute Windows path being used as relative* — it does not throw,
 * it just does not exist relative to the cwd vitest runs in. The `? : '.'`
 * fallback then quietly turned every scan into a scan of `frontend/`, and
 * `FILES.filter((f) => f.endsWith('.css'))` came back **empty**, because the one
 * stylesheet is at `src/styles/globals.css` and there is no `.css` at the
 * frontend root.
 *
 * The consequence was not a red build. It was **V-06's first assertion never
 * running**: `for (const file of CSS)` over an empty array, thirty-seven tests
 * green, and a deliberate `@keyframes` in the stylesheet detected by nothing.
 * This repository already has the rule for that shape — "if the scan stops finding
 * things, every rule passes by having checked nothing" — written above the
 * duration checks. It was simply not applied to the file walk.
 *
 * `fileURLToPath` is the supported way to go from a `file:` URL to a path, on
 * every platform, and it does not need the caller to know which platform it is on.
 */
const SRC_DIR = fileURLToPath(new URL('.', import.meta.url))

/** Every `.ts` / `.tsx` / `.css` under `src`, skipping tests. */
function sourceFiles(dir: string = SRC_DIR): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'dist') continue
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      out.push(...sourceFiles(full))
      continue
    }
    if (/\.(ts|tsx|css)$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

const FILES = sourceFiles()

/**
 * The stylesheet, on its own.
 *
 * **Hoisted here on 2026-09-30, and it used to sit 240 lines further down** — past
 * the block that now asserts it is non-empty. A guard that has to be written after
 * the thing it guards is a guard nobody writes, so the list and its assertion are
 * now together, and the eleven `for (const file of CSS)` loops below can all reach
 * a list that is known to hold something.
 */
const CSS = FILES.filter((f) => f.endsWith('.css'))

/** ⭐ The E2E specs, ⭐ and the vitest/vite config files ⭐ - ⭐ everything under
 * ⭐ `e2e/` plus the two configs at the frontend root that import packages.
 * ⭐ ⭐ Derived from the filesystem ⭐ rather than a literal path ⭐ - ⭐ the
 * ⭐ repo's own rule about constants (F-162) and the reason this file has three
 * ⭐ fewer dead names than the ones it recorded. */
const E2E_DIR = join(SRC_DIR, '..', 'e2e')
const E2E_FILES: string[] = existsSync(E2E_DIR)
  ? readdirSync(E2E_DIR)
      .filter((entry) => entry.endsWith('.spec.ts'))
      .map((entry) => join(E2E_DIR, entry))
  : []
/**
 * A path relative to `src`, for a message a person can act on.
 *
 * **The `+ 1` was a bug the new guard caught on its first run.** It assumed
 * `SRC_DIR` ends in a separator, which the old expression's trailing-slash strip
 * happened to provide: `new URL(...).pathname` is `/D:/…/src/`, and removing the
 * final `/` left the separator between `src` and the file name intact. That was
 * accidental — the old `SRC_DIR` *was* `D:/…/src`, with no trailing slash, so the
 * `+ 1` was already eating the first character of every relative path, and no
 * assertion was reading one closely enough to notice. `tyles/globals.css` is what
 * a reader would have been shown in every failure message.
 *
 * `fileURLToPath` does not add a trailing separator, so the slice is now exact.
 */
const RELATIVE = (file: string) => file.slice(SRC_DIR.length).replace(/^[\\/]/, '').replace(/\\/g, '/')

/**
 * Strip comments, preserving line numbering.
 *
 * ⭐ **This function exists because the first version of this file failed on its
 * own documentation.** All three initial failures were the rule *describing*
 * itself:
 *
 * - `globals.css:38  box-shadow: none;` — the global ban, flagged as a violation
 * - `components/ui/index.tsx:9  A stock library's \`rounded-lg\` is 8px` — prose
 * - `globals.css:72  never a rounded pill` — prose
 *
 * That is a general property of lint-by-grep, not a quirk: **the file that
 * documents a rule always contains the rule's forbidden string.** Left alone it
 * produces two bad outcomes, and the tempting one is worse — a maintainer
 * "fixes" the failure by deleting the comment that explains the rule, and the
 * knowledge is gone while the test goes green.
 *
 * Comments are replaced with spaces rather than removed, so a line number in a
 * failure message still points at the line the reader has open. String literals
 * are left alone, since a class name is what we are looking for.
 *
 * Naive about `//` inside a string (a URL would be truncated) — acceptable for
 * this codebase, and worth revisiting only if a source string ever needs it.
 */
function stripComments(source: string, isCss: boolean): string {
  const blank = (text: string) => text.replace(/[^\n]/g, ' ')
  let out = source
  if (isCss) {
    out = out.replace(/\/\*[\s\S]*?\*\//g, blank)
  } else {
    out = out.replace(/\/\*[\s\S]*?\*\//g, blank)
    // `//` to end of line, but not when it is preceded by `:` — which is the
    // shape of `http://`, and clipping a URL mid-string would be its own lie.
    out = out.replace(/(^|[^:])\/\/[^\n]*/g, (match, lead: string) => lead + blank(match.slice(lead.length)))
  }
  return out
}

/**
 * Every source file whose **code** matches `pattern`, with the line that matched.
 *
 * ⭐ `only` narrows the walk. It exists for V-12's usage count, where counting the
 * stylesheet would count the scale's own definition as a use of itself.
 */
function occurrences(
  pattern: RegExp,
  only: string[] = FILES,
): { file: string; line: number; text: string }[] {
  const hits: { file: string; line: number; text: string }[] = []
  for (const file of only) {
    const isCss = file.endsWith('.css')
    stripComments(readFileSync(file, 'utf8'), isCss)
      .split(/\r?\n/)
      .forEach((text, index) => {
        // A fresh regex per line: a shared /g regex carries lastIndex between
        // calls, so the second line it is tested against starts mid-string and
        // silently matches nothing. That failure is invisible — the test passes
        // for the wrong reason.
        if (pattern.test(text)) {
          hits.push({
            file: RELATIVE(file),
            line: index + 1,
            text: readFileSync(file, 'utf8').split(/\r?\n/)[index].trim(),
          })
        }
      })
  }
  return hits
}

function describeHits(hits: { file: string; line: number; text: string }[]): string {
  return hits.map((h) => `${h.file}:${h.line}  ${h.text}`).join('\n')
}

describe('the file list is not empty', () => {
  // Every check below is `expect(hits).toEqual([])`. If the walk found nothing,
  // all of them pass by having checked nothing — the exact failure this repo has
  // already produced four times (§"harness" in HANDOFF). So assert the substrate.
  it('actually found the source tree', () => {
    expect(FILES.length).toBeGreaterThan(20)
    expect(FILES.some((f) => f.endsWith('globals.css'))).toBe(true)
  })

  /**
   * The stylesheet is a **separate list** and it needs its own assertion.
   *
   * `actually found the source tree` above was green while `CSS` was empty,
   * because the walk resolved to the frontend root: it found 60-odd `.tsx` and
   * zero `.css`. So every rule written as `for (const file of CSS)` iterated
   * nothing and reported clean. This file has eleven such loops and not one of
   * them had a guard — the shape the comment above warns about, sitting in the
   * same file as the warning.
   *
   * A list that a rule iterates and a rule that never iterates it are
   * indistinguishable from the outside, so the list itself is asserted here, once,
   * next to where it is built.
   */
  it('found the stylesheet, so the rules that read it are not vacuous', () => {
    expect(
      CSS.length,
      'CSS is empty: every rule written as `for (const file of CSS)` is iterating ' +
        'nothing and reporting clean. This is what happened on 2026-09-30 — SRC_DIR ' +
        'resolved to the frontend root, and the one stylesheet is at ' +
        '`src/styles/globals.css`.',
    ).toBeGreaterThan(0)
    expect(
      CSS.map(RELATIVE).join(', '),
      'the stylesheet list should name the file that holds every token in §2.2',
    ).toContain('styles/globals.css')
  })
})

describe('V-01 · no shadows', () => {
  it('emits no box-shadow anywhere', () => {
    // ⭐ `box-shadow: none` is **allowed**, and the one place it appears is
    // `globals.css`'s universal `*` rule — the ban itself.
    //
    // The first draft of this test rejected it, on the reasoning that a lint
    // should not have exceptions. That reasoning is wrong here, and deleting the
    // line to make the test pass would have been a real regression: the global
    // rule is defence in depth. Nothing in `components/` emits a shadow today, so
    // it buys nothing *today* — its value is that a component added in six months
    // from a stock library, or one `shadow-sm` that slips through review, still
    // renders flat. A lint that would have you delete the guard in order to pass
    // is measuring the wrong thing.
    //
    // So the rule is stated precisely: **`none` may appear; no value that casts
    // anything may.** That is a stronger assertion than "no box-shadow at all",
    // because it also covers `0 1px 2px` and `inset` and Tailwind's
    // `shadow-[...]` arbitrary syntax.
    //
    // ⭐ The `(?=\S)` is load-bearing and its absence is a bug that has already
    // happened here. Written as `box-shadow\s*:\s*(?!none\b)`, the `\s*` matches
    // the space, the lookahead sees `none` and fails — so the engine backtracks
    // `\s*` to **zero width**, the lookahead now sits on the space (where `none`
    // does not match, so it succeeds), and `box-shadow: none` is reported as a
    // violation. The symptom was an assertion failure whose message was *empty*,
    // because the matched text was the blanked-out comment region. `(?=\S)` pins
    // the match to a position where a real value starts, and removes the
    // backtracking degree of freedom entirely.
    //
    // The ⌘K scrim needs no allowlist because it is a background colour, not a
    // shadow — the payoff of choosing a paper wash over a drop shadow.
    //
    // ⭐ **The Tailwind utilities matter more than the property, and the mutation
    // check is what proved it.** The first version of this rule matched only
    // `box-shadow:` and `drop-shadow`, so injecting `shadow-md` into a class
    // string left the suite green. That is the realistic failure: nobody writes
    // raw CSS in a Tailwind codebase, and a stock `Card` or `Popover` arrives
    // pre-loaded with `shadow-sm`. The global `* { box-shadow: none }` would have
    // hidden it, which is worse — the class sits there looking meaningful and
    // starts working the moment anyone edits that one line.
    const hits = occurrences(
      // `box-shadow:` is CSS; `boxShadow:` is the same declaration spelled as a
      // React inline style, which is how a shadow gets added by someone who never
      // opens a stylesheet. Both are banned, and matching only the CSS spelling
      // would leave the React one as a hole exactly the width of the obvious one.
      //
      // The `/i` is not tidiness: the first version read `box-?shadow`, which is
      // case-sensitive, so `style={{ boxShadow: … }}` passed. The mutation check
      // is the only reason that was found — a lowercase-only pattern looks
      // correct when you write it.
      /box-?shadow\s*:\s*(?!none\b|'none')(?=\S)|drop-shadow|(?<![\w-])shadow-(?!none\b)(?=\S)/i,
    )
    expect(describeHits(hits), `shadow found:\n${describeHits(hits)}`).toBe('')
  })

  it('still bans the shadow globally, so the rule survives a careless import', () => {
    const css = stripComments(
      readFileSync(join(SRC_DIR, 'styles', 'globals.css'), 'utf8'),
      true,
    )
    expect(css).toMatch(/\*\s*\{[^}]*box-shadow:\s*none/)
  })
})

describe('V-02 · radius never exceeds 4px', () => {
  it('has no rounded-full and no rounded above 4px', () => {
    // `rounded-lg` is 8px, `rounded-xl` 12px, `rounded-2xl` 16px. A stock
    // component library reaches for those by reflex, and the difference between
    // "a report" and "an admin panel" is exactly 4px.
    const hits = occurrences(/rounded-(full|2xl|xl|lg|3xl)|rounded-\[([5-9]|\d{2,})px\]/)
    expect(describeHits(hits), `radius over 4px:\n${describeHits(hits)}`).toBe('')
  })

  it('uses an explicit small radius rather than a bare rounded', () => {
    // `rounded` alone is 4px on Tailwind's scale, so it is legal — but it is
    // also the value that becomes 8px the first time someone assumes `rounded`
    // is the small one. The guide asks for the number to be visible.
    const hits = occurrences(/(?<!-)rounded(?![-\[\w])/)
    expect(describeHits(hits), `ambiguous radius:\n${describeHits(hits)}`).toBe('')
  })
})

describe('V-05 · numbers are tabular', () => {
  it('keeps the token rule in the stylesheet', () => {
    const css = readFileSync(join(SRC_DIR, 'styles', 'globals.css'), 'utf8')
    expect(css).toMatch(/font-variant-numeric:\s*tabular-nums/)
  })
})

describe('V-06 · decorative motion is allowed, decorative motion is accountable', () => {
  /**
   * **Reversed 2026-09-30 by ADR-0033.** The owner's decision: a deliberately
   * aesthetic product, which the guide's own §5.2 ("the interface is the product,
   * not a landing page") and §7.2's six bans had ruled out.
   *
   * What changed is the *scope*, not the *teeth*. The first version of this rule
   * asserted that the stylesheet defines no `@keyframes` at all, and its own
   * comment said why that shape was chosen:
   *
   * > Stronger than grepping: if the stylesheet defines no `@keyframes` at all,
   * > then shimmer, count-up, fade-in-up and slide-in are all impossible **by
   * > construction rather than by review.**
   *
   * That sentence is the reason this block is not simply deleted. Making a class
   * of effect unrepresentable is a stronger guarantee than reviewing each use, and
   * this repository's whole claim is that it prefers construction to review. A
   * reversed rule that leaves nothing behind is a *weaker* repository, so the two
   * assertions below take over the job:
   *
   * 1. every keyframe animation must be reachable by `prefers-reduced-motion`
   * 2. motion may not be applied to the data itself (§7.1's L0)
   *
   * Between them they still stop the specific things §7.2 named, and the reduced
   * -motion rule is the one that matters for a person who gets motion sick.
   */

  // `CSS` is the module-level list, asserted non-empty in the block above.
  const keyframeRules = (): { where: string; name: string }[] => {
    const found: { where: string; name: string }[] = []
    for (const file of CSS) {
      const css = stripComments(readFileSync(file, 'utf8'), true)
      for (const m of css.matchAll(/@keyframes\s+([\w-]+)/g)) {
        found.push({ where: RELATIVE(file), name: m[1] })
      }
    }
    return found
  }

  it('every keyframe animation is switched off under prefers-reduced-motion', () => {
    const reduced = CSS.map((f) => stripComments(readFileSync(f, 'utf8'), true))
      .join('\n')

    /**
     * Two shapes are accepted, and the difference matters.
     *
     * **Whole-tree.** A `prefers-reduced-motion` block that sets
     * `animation-duration` (or `animation: none`) on `*` — or on `[data-motion]`,
     * or any selector matching the tree — switches off *everything*, including
     * keyframes declared later in the file. This stylesheet already has one.
     *
     * **Per-name.** Otherwise the animation has to be named in the block.
     *
     * The first version of this assertion tested `reduced.includes('prefers-reduced-motion')`
     * and treated that as proof every animation was covered. **It is not**, and the
     * stylesheet's own existing block is what exposed it: that block was present, so
     * the flag was true, so a `@keyframes` with no name in it passed. The rule was
     * satisfied by a block that had been there before motion was allowed at all.
     *
     * So the question is not "is there a reduced-motion block" but "does the block
     * reach this animation" — which is a question about selectors, answered below.
     */
    const wholeTree = /@media[^{]*prefers-reduced-motion[^{]*\{[\s\S]*?\}/.test(reduced)
      ? /@media[^{]*prefers-reduced-motion[^{]*\{([\s\S]*?)\n\}/.exec(reduced)?.[1] ?? ''
      : ''
    // A block that reaches the tree: `*`, `:root`, `html`, `body`, or a
    // `[data-motion]`-style attribute selector that the components already carry.
    const blanket = /(^|[,{}])\s*(\*|:root|html|body|\[[\w-]+\])\s*(,|\{)/.test(wholeTree)
    const named = (name: string) =>
      new RegExp(`animation[^;{}]*\\b${name}\\b`).test(wholeTree)

    const names = keyframeRules()
    const unguarded = names.filter((n) => !(blanket || named(n.name)))

    expect(
      unguarded.map((n) => `${n.where}  @keyframes ${n.name}`),
      'each @keyframes must be switched off by a prefers-reduced-motion block, either ' +
        'by a selector that reaches the tree or by naming the animation:\n' +
        unguarded.map((n) => `${n.where}  ${n.name}`).join('\n'),
    ).toEqual([])

    /**
     * A blanket block does **not** cover an `animation` shorthand that carries
     * `!important`.
     *
     * This is real CSS and it was found by trying to break the rule rather than
     * by reading it. The stylesheet's own block is
     * `[data-motion], * { animation-duration: 0.01ms !important }`, which beats a
     * plain `animation: name 700ms` — the longhand is what the shorthand expands
     * to, and the override arrives later with equal specificity. But a shorthand
     * written as `animation: name 700ms linear !important` out-ranks it, and the
     * animation runs at full duration for a reader who asked for less.
     *
     * So a `!important` on an `animation` shorthand is a keyframe the blanket
     * block does not reach, and it is the one shape where "there is a
     * reduced-motion block" and "the motion is switched off" come apart.
     */
    const importantAnimations = CSS.flatMap((file) => {
      const css = stripComments(readFileSync(file, 'utf8'), true)
      const out: string[] = []
      for (const m of css.matchAll(/animation\s*:[^;{}]*!important/g)) {
        out.push(`${RELATIVE(file)}  ${m[0].trim()}`)
      }
      return out
    })
    expect(
      importantAnimations,
      'an `animation` shorthand with !important out-ranks the blanket ' +
        '`animation-duration: 0.01ms !important` in the reduced-motion block, so the ' +
        'animation still runs at full length. Use a longhand, or drop the !important.',
    ).toEqual([])

    // And the substrate: a stylesheet with keyframes and no reduced-motion block at
    // all is the failure this assertion exists to catch, so it is checked rather
    // than assumed.
    expect(
      names.length === 0 || wholeTree.length > 0,
      'the stylesheet declares @keyframes but has no prefers-reduced-motion block',
    ).toBe(true)
    expect(
      names.length === 0 || blanket || names.every((n) => named(n.name)),
      'the prefers-reduced-motion block does not reach any animation — a block that ' +
        'names a selector nothing uses is the same as no block at all',
    ).toBe(true)
  })

  it('never animates the data itself — §7.1 L0 still holds', () => {
    // This is the one ban from §7.2 that survives the reversal, because it is the
    // one about product meaning rather than decoration: an animated number is a
    // number the reader has to watch settle, and the guide's own note is that it
    // implies a return. A row of figures, a chart, a price — those are L0.
    //
    // Scanned in the **stylesheet**, not in JSX. The first version matched
    // `animate-*` in component source, which is the wrong artefact twice over: it
    // can only see a Tailwind class name and never the `animation` declaration
    // that actually moves a thing, and it would fire on a class that is written
    // but never applied. The selectors in the stylesheet are where the animation
    // meets the element it moves, so that is where the question belongs.
    // ⭐ **Substring, not a word boundary, and that was found by failing to catch
    // `.ticker-price`.** ⭐ A boundary pattern with `[^\w-]` on both sides
    // ⭐ deliberately excludes a hyphen, because `close` must not fire on
    // ⭐ `disclose` ⭐ — ⭐ and the same exclusion means `ticker-price` never matches
    // ⭐ `price` ⭐, ⭐⭐ which is precisely a price ⭐⭐. ⭐
    //: ⭐ So the word list is matched inside the identifier, split on hyphen and
    //: ⭐ underscore first, and each part compared whole. ⭐ `.ticker-price`
    //: ⭐ splits to `['ticker', 'price']` ⭐⭐ and `price` is in the list ⭐⭐;
    //: ⭐ `.disclose` ⭐ is one part ⭐, ⭐ not in the list ⭐, ⭐ and stays legal ⭐⭐.
    const DATA_WORDS = new Set([
      'count', 'countup', 'figure', 'figures', 'price', 'prices', 'value', 'values',
      'number', 'numbers', 'total', 'totals', 'amount', 'amounts', 'pnl',
      'quote', 'quotes', 'close', 'closes', 'volume', 'volumes', 'candle', 'candles',
      'ohlc', 'change', 'changes', 'pct', 'nav', 'equity', 'drawdown', 'sharpe',
    ])
    /** Every identifier part in a selector that names a figure. */
    const dataParts = (selector: string): string[] =>
      [...selector.matchAll(/[A-Za-z][\w-]*/g)]
        .flatMap((w) => w[0].split(/[-_]+/))
        .map((w) => w.toLowerCase())
        .filter((w) => DATA_WORDS.has(w))

    const offenders: string[] = []
    for (const file of CSS) {
      const css = stripComments(readFileSync(file, 'utf8'), true)
      // A rule block: selector, declarations, and — if it has one — an animation.
      for (const m of css.matchAll(/([^{}]+)\{([^{}]*animation[^{}]*)\}/g)) {
        const [, selector, body] = m
        const parts = dataParts(selector)
        if (parts.length > 0) {
          offenders.push(
            `${RELATIVE(file)}  ${selector.trim()} → ${body.trim().slice(0, 60)}` +
              `   (${[...new Set(parts)].join(', ')})`,
          )
        }
      }
    }
    expect(
      offenders,
      `an animation on a data-bearing selector (§7.1 L0 — data does not move):\n${offenders.join('\n')}`,
    ).toEqual([])
  })
})


describe('V-07 · the dependency budget', () => {
  it('has only the approved runtime packages', () => {
    // `docs/FRONTEND_STYLE_GUIDE.md` §6 records the owner's approvals, and
    // 宪法 §3.2.1 lists them by name. The constitution bans unapproved additions,
    // and this is the check that makes that ban mechanical instead of a matter
    // of remembering.
    //
    // ⚠️ **This only sees the top-level `dependencies`.** Transitive packages are
    // invisible here. ⭐ Their licences *are* checked, though — since spec 031 the npm
    // tree is scanned by `backend/scripts/check_licenses.py`, which reads the installed
    // `node_modules` rather than a declared list, and fails on copyleft that would ship.
    // So the two checks are complementary: this one is 「did you approve the top-level
    // package」, that one is 「does anything in the tree carry a licence we cannot ship」. — `backend/scripts/check_licenses.py` uses
    // `importlib.metadata`, so it sees **Python distributions only**. That gap
    // was survivable at four packages and is not at 209, so the npm tree is
    // scanned separately (see the spec 026 changelog); turning that scan into a
    // gate is the obvious next step and is recorded in the spec's §6.
    const pkg = JSON.parse(
      readFileSync(join(SRC_DIR, '..', 'package.json'), 'utf8'),
    ) as { dependencies: Record<string, string> }
    const approved = new Set([
      'react',
      'react-dom',
      'lucide-react',
      'class-variance-authority',
      'clsx',
      'tailwind-merge',
      // Spec 034: candlesticks. ⭐ Approved by the owner's instruction to take over
      // TSP's display layer wholesale ("怎么展示数据的，全部拿过来") plus "继续"
      // on 2026-09-29, after the four §3.2 points were put in front of them.
      // Licence Apache-2.0 (measured from package.json, not assumed — I first
      // called it MIT and was wrong). v4.2.0; its 4.x typings were read, which is
      // how the v3-style addCandlestickSeries was confirmed and the v5 addSeries
      // (zero mentions) was avoided. Record: .ai/specs/034-kline/dependency-record.md
      'lightweight-charts',
      // Spec 026: Markdown editor, approved by the owner 2026-09-28 and
      // licence-checked (MIT). ⭐ **Approved, installed, imported by nothing, and
      // shipped at 0 bytes** ⭐ — ⭐ which is the only indefensible state, and the
      // reason **V-16** exists: ⭐ this list says a package is *allowed*, ⭐ and
      // nothing here says anything is *using* it. ⭐ V-16 reports all three unless
      // its exemption carries a reason, ⭐ and that reason is the measured cost
      // (**+362.82 kB / +110.59 kB gzip**) ⭐ plus the fact that these three
      // ⭐ cannot read Markdown back out without a fourth package.
      // ⭐ Decision pending — see `.ai/memory/decisions.md` ADR-0032.
      '@milkdown/core',
      '@milkdown/react',
      '@milkdown/preset-commonmark',
    ])
    const actual = Object.keys(pkg.dependencies).sort()
    expect(actual.filter((name) => !approved.has(name))).toEqual([])
  })
})

describe('the A-share colour convention survives', () => {
  it('keeps red for up and green for down', () => {
    // Not a V-item, but the one rule whose violation would make the product lie
    // to a reader who parses it in under a second. Every other token can be
    // restyled; swapping these two turns every quote in the app backwards.
    const css = readFileSync(join(SRC_DIR, 'styles', 'globals.css'), 'utf8')
    expect(css).toMatch(/--color-up:\s*#c0392b/)
    expect(css).toMatch(/--color-down:\s*#1e7a46/)
  })
})

/* ── V-09 · the two motion levels, and only those ────────────────────────────
 *
 * V-06 above **bans** motion. It says nothing about the motion the guide *allows*,
 * and that asymmetry is a hole with a specific shape: `transition: all 4s` on a
 * table row passes every existing check. §7.1 gives exact ranges — L1 100–120ms,
 * L2 180–220ms, both on one easing — and nothing read them. A rule with numbers in
 * it that no test quotes is a wish.
 */
describe('V-09 · transition durations are L1 or L2', () => {
  /**
   * Every `<number>ms` inside a `transition` / `transition-duration` declaration.
   *
   * ⭐ **The declaration, not the line — and this was wrong the first time.**
   *
   * The first version read a line, kept it if the line mentioned `transition`, and
   * harvested `ms` off that same line. `globals.css` writes the shorthand across
   * four lines, as CSS is meant to be written:
   *
   * ```css
   * [data-motion='l1'] {
   *   transition:                              ← the only line that says "transition"
   *     background-color 100ms cubic-bezier(0.2, 0, 0.2, 1),   ← and this is where
   *     border-color 100ms cubic-bezier(0.2, 0, 0.2, 1),       ← the durations
   *     color 100ms cubic-bezier(0.2, 0, 0.2, 1);              ← actually are
   * }
   * ```
   *
   * So it found **1** duration where there are 7, and — because the rule is
   * "expect zero violations" — it reported **green**. A one-line predicate that
   * mostly reads whitespace is the most confident kind of wrong.
   *
   * ⭐ **What caught it was the vacuity guard in the test below**, on its first
   * run, before a single component was touched. That guard is not ceremony: it is
   * the only thing standing between "no violations" and "no violations *found*".
   * ⭐ When an anti-vacuity assertion fails, read it as a claim about the assertion
   * itself first — it is evidence that the thing it guards does not work yet.
   *
   * The fix is to read the **declaration**, bounded by `;`, which is also where CSS
   * says a declaration ends. `[^;]` spans newlines; `.` would not, which is the
   * other half of why a line-scoped or `.`-scoped variant cannot work here.
   */
  function declaredDurations(): { where: string; value: number }[] {
    const out: { where: string; value: number }[] = []
    for (const file of FILES.filter((f) => f.endsWith('.css'))) {
      const css = stripComments(readFileSync(file, 'utf8'), true)
      // ⭐ **`animation` as well as `transition`, and that is not tidiness — it is a
      // hole ADR-0033 opened.** This function read only `transition`, which was
      // complete while the stylesheet had no `@keyframes` at all. The reversal
      // brought keyframes back, so an `animation:` shorthand could now declare
      // `4000ms` and nothing in this file would look at it: §7.1's two ranges
      // stopped being the whole of the motion budget the moment motion stopped
      // being spelled `transition`.
      for (const decl of css.matchAll(
        /(transition|animation)(?:-duration)?\s*:\s*([^;]+);/gi,
      )) {
        const head = (decl[0].split('\n')[0] ?? '').trim()
        for (const match of decl[2].matchAll(/(\d*\.?\d+)ms/g)) {
          out.push({ where: `${RELATIVE(file)}  ${head}`, value: Number(match[1]) })
        }
      }
    }
    return out
  }

  /** §7.1's two ranges, the reduced-motion off switch, and L3. */
  const ALLOWED: { label: string; test: (ms: number) => boolean }[] = [
    { label: 'L1 100–120ms', test: (ms) => ms >= 100 && ms <= 120 },
    { label: 'L2 180–220ms', test: (ms) => ms >= 180 && ms <= 220 },
    {
      // ⭐ `0.01ms` is not a duration choice, it is the "off" switch in
      // `prefers-reduced-motion`. Any value that is not visually zero but is
      // imperceptible is what the media query needs, because `transition: none`
      // would make the *property change* instant and some transitions are relied on
      // to not be instant. Written out rather than hidden in a `.includes([...])`
      // so a reader can see why this one number is not one of §7.1's two.
      label: 'reduced-motion off switch (0.01ms)',
      test: (ms) => ms > 0 && ms < 1,
    },
    {
      // ⭐ **L3 · 600–1600ms · a one-shot entrance, and the launch screen only.**
      //
      // §7.1 has two levels and both describe a *state change the reader
      // triggered*. The launch screen is not that: it arrives on its own, at most
      // once a day, and the reader has nothing to interrupt while it does. So it
      // needs a third band rather than being forced through L2 — a 220 ms
      // unrolling scroll is a flick, and a launch screen that flicks is a splash
      // screen with better manners.
      //
      // The ceiling is the point. Past about 1.6 s an entrance stops being an
      // entrance and becomes a wait, and a wait on the way into the product is
      // the one thing this product must never be. The floor is there for the same
      // reason from below: under 600 ms there is no settle in it, and the effect
      // is only detectable by someone measuring it.
      label: 'L3 600–1600ms (one-shot entrance)',
      test: (ms) => ms >= 600 && ms <= 1600,
    },
  ]

  it('declares a duration only in L1, L2 or the reduced-motion switch', () => {
    const bad = declaredDurations().filter(
      (d) => !ALLOWED.some((a) => a.test(d.value)),
    )
    expect(
      bad.map((d) => `${d.where}  ${d.value}ms`),
      `transition duration outside §7.1:\n${bad.map((d) => `${d.where}  ${d.value}ms`).join('\n')}`,
    ).toEqual([])
  })

  it('found the durations to check, so the rule above is not vacuous', () => {
    // ⭐ Same reason as the file-list check at the top: every assertion in this block
    // is "expect zero". If the scan stops finding durations — someone deletes the
    // motion, or moves it out of CSS — every rule passes by having checked nothing,
    // and the guide's §7.1 silently stops being enforced.
    const found = declaredDurations()
    expect(found.length).toBeGreaterThanOrEqual(4)
    expect(found.some((d) => ALLOWED[0].test(d.value))).toBe(true)
    expect(found.some((d) => ALLOWED[1].test(d.value))).toBe(true)
  })

  it('confines the L3 entrance band to the launch screen', () => {
    // ⭐ **A band nobody can misuse is not a band, it is a permission.** L3 exists
    // because the launch screen needs 700–1200 ms and L2's 220 ms ceiling is a
    // flick. Without this, the next person who wants a slow drawer just writes
    // `1600ms`, and the number that was a bound on one specific screen becomes a
    // general licence to be slow.
    //
    // So the band is tied to the thing it was written for: an L3 duration may only
    // be declared in a rule that also carries a `startup-` selector. That is a
    // coarse test — it does not check the *specific* selector — and it is
    // deliberately coarse, because the failure being prevented is "L3 escapes the
    // launch screen", not "L3 is spelled correctly".
    const offenders: string[] = []
    for (const file of FILES.filter((f) => f.endsWith('.css'))) {
      const css = stripComments(readFileSync(file, 'utf8'), true)
      // ⭐ **The class name, with no boundary in front of it.** The first version
      // required `(^|[,\s])startup-`, on the reasoning that `foo-startup-x` should
      // not count. It also failed to count `.startup-hang` — a CSS class selector
      // has a `.` in front of it — so the rule reported **the one legitimate L3
      // declaration in the tree** as an offence, on its first run. The boundary was
      // guarding against a collision that cannot happen here (there is exactly one
      // screen) and it cost the rule its only real subject.
      for (const rule of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const [, selector, body] = rule
        // An `@keyframes` block names the animation, not the screen it runs on, so
        // its durations are judged by who *references* the name, not by its
        // selector — and there is no reference to check here, so it is skipped
        // rather than guessed at.
        if (/^@(keyframes|media|supports)\b/.test(selector.trim())) continue
        for (const m of body.matchAll(/(\d*\.?\d+)ms/g)) {
          const ms = Number(m[1])
          if (!ALLOWED[3].test(ms)) continue
          if (!selector.includes('startup-')) {
            offenders.push(
              `${RELATIVE(file)}  ${selector.trim().slice(0, 60)}  ${m[0]}  (L3)`,
            )
          }
        }
      }
    }
    expect(
      offenders,
      `an L3 duration outside the launch screen:\n${offenders.join('\n')}`,
    ).toEqual([])
  })

  it('has at least one L3 duration, so the band above is not an empty permission', () => {
    // The launch screen is the reason L3 exists, so if the tree has no L3
    // duration then the band is describing a screen that is not there, and the
    // rule above would be guarding nothing. Same reasoning as the file-list check.
    const found = declaredDurations()
    expect(found.some((d) => ALLOWED[3].test(d.value))).toBe(true)
  })

  it('never says `transition: all`', () => {
    // ⭐ `all` animates every property that later becomes animatable — including
    // ones a future edit adds without anyone deciding to. `max-height`,
    // `grid-template-rows`, a custom property: all layout, all unpainted, all
    // absent from §7.1's intent. This is the L2 line in `globals.css`, and it is the
    // only place `all` is legal *nowhere*.
    const hits = occurrences(/transition\s*:\s*all\b|(?<![\w-])transition-all\b/)
    expect(describeHits(hits), `transition: all:\n${describeHits(hits)}`).toBe('')
  })

  it('honours prefers-reduced-motion', () => {
    const css = stripComments(readFileSync(join(SRC_DIR, 'styles', 'globals.css'), 'utf8'), true)
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
  })
})

/* ── V-13 · every page that has a claim to make, makes it in the claim's type ──
 *
 * ⭐ **This is a weaker assertion than the rest, and the weakness is stated here
 * rather than left for someone to discover.** V-12 proves 「主张用的是 `.type-claim`
 * 且它就是 17px / 26px 衬线」 — but it cannot prove 「这一页**有**主张」, because no
 * grep can tell whether a page was *supposed* to have one. So this test takes the
 * judgement that grep cannot make — **which pages owe the reader a claim** — and
 * writes it down as data. ⭐ That is the same trade V-03 and V-08 already make, in
 * the file header's own words: a test that could only be satisfied by understanding
 * what a piece of text *is* stays a human item.
 *
 * ⭐ So the list below is the assertion, and it is not derived from the spec — it is
 * derived from **what each page is for**:
 *
 * | page | the claim it owes | why |
 * |---|---|---|
 * | today | the criterion sentence | spec 040's whole output; the reader wrote it |
 * | instrument | the follow reason + the change | 「我为什么关注它」 + the number that may invalidate it |
 * | review | the quadrant verdict | 象限判语, named as such in §2.2 |
 * | retrospective | the score, the guidance, the rationale | a retrospective is three claims |
 * | vault | the note's own title | a note's title is the reader's sentence about a thing |
 * | card section | the card's sentence | §2.2's 卡片 row, verbatim |
 *
 * ⭐ **`pool` is deliberately absent**, and the reason is the interesting part. A
 * watchlist is a **list**, and §2.2's density licence (规则 6) is exactly what lets
 * a list be a list. Making twenty tickers into twenty claims would be the failure
 * this guide spends ten sections preventing — it is the 「数据密度」 it names in its
 * own keywords being given up for a type rule. ⭐ An empty list here would be a
 * defect; that judgement is recorded rather than encoded.
 */
const PAGES_OWING_A_CLAIM: [file: string, what: string][] = [
  ['TodayPage.tsx', 'the criterion sentence'],
  ['InstrumentPage.tsx', 'the follow reason and the change'],
  ['ReviewPage.tsx', 'the quadrant verdict'],
  ['RetrospectivePage.tsx', 'the score, the guidance and the rationale'],
  ['VaultPage.tsx', "the note's own title"],
  ['CardSection.tsx', "the card's own sentence"],
]

describe('V-13 · the pages that owe a claim, use the claim type', () => {
  it('every page that owes a claim renders one in the claim type', () => {
    const failures: string[] = []
    for (const [file, what] of PAGES_OWING_A_CLAIM) {
      const path = join(SRC_DIR, file)
      if (!existsSync(path)) {
        failures.push(`${file} does not exist — the page list is stale`)
        continue
      }
      const source = readFileSync(path, 'utf8')
      const usesClaim = /(?<![\w-])type-claim(?:-lg)?(?![\w-])/.test(
        stripComments(source, false),
      )
      if (!usesClaim) failures.push(`${file} owes a claim (${what}) but uses none`)
    }
    expect(failures, `claims missing or unclaimed:\n${failures.join('\n')}`).toEqual([])
  })

  it('the claim is serif, because §2.1 puts serif on claims', () => {
    // ⭐ The two halves of a claim, checked separately because they were wrong
    // separately. V-12 pins the *size*; this pins the *face*, and the A6 pass found
    // that `TodayPage`'s criterion sentence — the largest sentence in the product and
    // the output of spec 040 — carried the size only in its first draft and no
    // `serif` at all, so it rendered at claim proportions in the report's voice
    // rather than the reader's.
    //
    // ⭐ **This is checked as "size implies face", not "every claim has `serif`
    // next to it"**, because `serif` and `type-claim` are two homes for two
    // questions and they are frequently on different lines (the size on the element,
    // the face written once above it for a whole block). A stricter pairing test
    // would fail on correct code.
    const failures: string[] = []
    for (const [file, what] of PAGES_OWING_A_CLAIM) {
      const source = stripComments(readFileSync(join(SRC_DIR, file), 'utf8'), false)
      if (!/(?<![\w-])serif(?![\w-])/.test(source)) {
        failures.push(`${file} uses a claim type for ${what} but never reaches for \`serif\``)
      }
    }
    expect(failures, `claims without the face:\n${failures.join('\n')}`).toEqual([])
  })
})

/* ── V-10 / V-11 · the icon registry, and the ban it makes mechanical ──────────
 *
 * ⭐ §5 was the only section of the guide that had **an approved dependency and
 * zero uses**: `lucide-react` was installed on 2026-09-28 with the owner's approval
 * and recorded in 宪法 §3.2.1, and this file's own V-07 allowlist named it — ⭐ while
 * the product imported it nowhere. `status.md` carried 「Lucide 图标一个都没用上」 as
 * a standing line for exactly that long.
 */
describe('V-10 · no emoji as a functional icon', () => {
  it('renders no emoji as a functional mark, in JSX text or in a string literal', () => {
    // ⭐ **The first version of this banned emoji everywhere, and it was wrong** — it
    // reported 150-odd hits, every one of them the `⭐` this repository uses as a
    // comment marker in its own source. ⭐ Those are not icons; they are the reason
    // those comments exist. ⭐ §5's sentence is 「⛔ 禁止 emoji 作**功能图标**」 — *as a
    // functional icon* — and the first version quietly widened it to 「禁止 emoji」,
    // which is a different and much more expensive rule.
    //
    // ⭐ **It mattered because a lint that cannot be satisfied without editing 200
    // comment lines is a lint that gets deleted**, and the 200 lines carry the
    // reasoning this project runs on. The correction is not a relaxation: it is the
    // narrower rule, which is the one that keeps §5's actual prohibition testable.
    //
    // ⭐ So the scan is over **what reaches the screen** — JSX text and string
    // literals — and not over comments at all. The three ranges are the blocks that
    // actually get pasted, and ⭐ **Dingbats is the one that matters**: ✅ ⚠ ✗ ⌨ all
    // live there, and all four were used as functional marks in this codebase's own
    // history — `DataTable` used ⌨ for its unsorted column until the comment above it
    // records why it stopped.
    //
    // ⭐ Written as escapes rather than literally: ⭐ **the file must not contain the
    // character it bans**, for the same reason a comment about `text-decoration`
    // cannot quote its own delimiter.
    const hits = occurrences(
      /[\u{1F300}-\u{1FAFF}\u{2705}\u{274C}\u{26A0}\u{2328}\u{FE0F}]/u,
    )
    expect(describeHits(hits), `emoji as a functional mark:\n${describeHits(hits)}`).toBe('')
  })

  it('picks out the marks the guide names, so the ranges above are not guesswork', () => {
    // ⭐ The range above is an argument, and an argument that names nothing is not an
    // argument. ⭐ This asserts that the four glyphs §5's ban is actually about are
    // inside it — and that ⭐ `▲`/`▼`, which §2.3 *requires* for 涨跌, are **not**:
    // they are Arrows-block U+25B2/U+25BC, deliberately outside every range here,
    // because §2.3 mandates them as a double-encoding and a rule that caught them
    // would be making a colour-coded convention unreadable.
    const banned = /[\u{1F300}-\u{1FAFF}\u{2705}\u{274C}\u{26A0}\u{2328}\u{FE0F}]/u
    for (const glyph of ['✅', '❌', '⚠', '⌨', '🎉']) expect(banned.test(glyph)).toBe(true)
    for (const glyph of ['▲', '▼', '↕', '·', '→', '⌘', 'K', '⌫']) {
      expect(banned.test(glyph), `${glyph} must stay legal — §2.3 requires ▲▼`).toBe(false)
    }
  })
})

describe('V-11 · the icon registry has no dead entries', () => {
  // ⭐ Parsed from the source rather than imported, because this file runs under
  // vitest's node environment and pulling a React component tree in for a lint rule
  // is the wrong dependency. ⭐ Anchored to `const REGISTRY = {` so it cannot latch
  // onto a lookalike object literal elsewhere.
  function registryEntries(): string[] {
    const source = readFileSync(join(SRC_DIR, 'components', 'ui', 'Icon.tsx'), 'utf8')
    const block = source.match(/const REGISTRY = \{([\s\S]*?)\n\} as const/)
    if (block === null) throw new Error('REGISTRY is not where Icon.tsx says it is')
    return [...block[1].matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1])
  }

  it('finds a registry to check, so the rules below are not vacuous', () => {
    // ⭐ Same guard as everywhere else in this file. The two rules below are "expect
    // zero", so a parser that silently matches nothing would make both pass by
    // having checked nothing — which is how `DataTable`'s sort arrow survived at 9px
    // and how the whole scale could have been deleted with V-12 still green.
    //
    // ⭐ **The floor is 5 because the registry has exactly five entries, and it was
    // 10 when this was written.** The first run had thirteen — the five views plus
    // eight interface actions nobody had placed — and V-11 immediately reported all
    // eight as dead. ⭐ That is the rule working exactly as intended on its first
    // real input: 「装了一个图标库」 and 「注册表里有八个用不上的图标」 are the same
    // mistake wearing different names. The eight were deleted rather than the
    // threshold lowered to match them, ⭐ because lowering the threshold to fit the
    // data is how an assertion becomes a rubber stamp.
    expect(registryEntries().length).toBeGreaterThanOrEqual(5)
  })

  it('every registered icon is named somewhere outside the registry itself', () => {
    // ⭐ **The first version of this rule reported all five icons as dead while the
    // sidebar was rendering them**, because it looked for `name="today"` and the
    // sidebar passes `name={entry.icon}` — the name lives in `ROUTES` as a string
    // literal and reaches the component through a prop. ⭐ A rule that cannot see
    // indirection is not wrong so much as **written against a shape nobody uses**,
    // and the fix is to ask the question that is actually true: **does this name
    // appear as a literal somewhere else in `src`?** That covers the direct form, the
    // table form, and any future one, and it cannot be satisfied by the registry
    // quoting itself.
    //
    // ⭐ `Icon.tsx` is excluded by path rather than by stripping its own registry,
    // because a name can also appear in that file's **comments** — the registry's
    // docstring names all five — and a comment is not a use.
    const others = FILES.filter((f) => !f.endsWith(join('components', 'ui', 'Icon.tsx')))
    const dead = registryEntries().filter(
      (name) => !occurrences(new RegExp(`['"\`]${name}['"\`]`), others).length,
    )
    expect(
      dead,
      `icons no other file names — use them or delete them:\n${dead.join('\n')}`,
    ).toEqual([])
  })

  it('the sidebar gives every view a glyph, so no row renders blank', () => {
    // ⭐ Not the same rule as the one above. A view whose `icon` is missing renders a
    // row with a label and nothing beside it, and ⭐ **no assertion in this file could
    // see it**: there is no icon to be dead, because it was never registered. ⭐ The
    // registry's own header in `routing.ts` names this as the failure mode a second
    // table would cause, and this is the check that it does not happen.
    const routes = readFileSync(join(SRC_DIR, 'routing.ts'), 'utf8')
    const rows = [...routes.matchAll(/name:\s*'(\w+)'[\s\S]*?icon:\s*'(\w+)'/g)]
    expect(rows.length, 'ROUTES rows without an icon could not be parsed').toBeGreaterThanOrEqual(5)
    const registered = new Set(registryEntries())
    const missing = rows.filter((row) => !registered.has(row[2] ?? ''))
    expect(
      missing.map((row) => `${row[1]} → ${row[2]}`),
      'routes whose glyph is not in the registry',
    ).toEqual([])
  })
})

/* ── V-12 · font sizes come from the type scale, and only from there ────────── */

describe('V-12 · the type scale is the only place a font size is written', () => {
  it('has no hand-written pixel size in any component', () => {
    // ⭐ The regex starts at a **digit**, which is what keeps
    // `text-[color:var(--color-up)]` out of it. There are 28 of those — they are
    // *colours* that Tailwind v4 happens to spell with the same bracket syntax as a
    // length, and a rule that flagged them would be a rule nobody could satisfy.
    //
    // ⭐ And it is deliberately not `text-\[11px\]`. §2.2's judgement — 13px for
    // anything read as a paragraph, 11/12px for chrome — is a judgement about what a
    // piece of text **is**, and no regex knows that. The enforceable half is: the
    // seven classes in `globals.css` are the only vocabulary, so the judgement
    // happens once, when a class is written, instead of 298 times at a call site.
    const hits = occurrences(/(?<![\w-])text-\[(\d|\.)/)
    expect(
      describeHits(hits),
      `hand-written font size:\n${describeHits(hits)}`,
    ).toBe('')
  })

  it('defines the eight sizes §2.2 rules on, at the numbers it gives', () => {
    // ⭐ **This is the assertion that makes the previous one honest.** A ban on
    // hand-written sizes is satisfied by having *no* scale at all — delete the
    // classes, replace them with inline styles, and V-12's first test is green
    // while every page renders at the browser's default 16px. So the scale itself is
    // pinned, class by class, to the table in §2.2:
    //
    //   页面标题 22/30 · 主张 17–20/26 · 页面主数字 24/28 · 正文 13/20 · 单元格 13/18
    //   表头/元数据 12/16 · 徽章 11/14
    //
    // ⭐ The 11/12px ban is §2.2's own ⛔ on the 正文散文 row, so it is asserted
    // here rather than in the first test — this is where the numbers live.
    //
    // ⭐ **These are `@utility`, not loose CSS, and the assertion says so.** The
    // first version registered them as plain `.type-prose { … }` and the tests
    // matched them as plain classes, so they were happy. Converting them to
    // `@utility` (Tailwind v4's mechanism for a custom utility) broke every
    // assertion at once, which is the only reason this note exists: **a test that
    // asserts 「a class with these numbers exists」 cannot tell a registered utility
    // from a loose rule, and the difference is not cosmetic.** Two things come with
    // `@utility` that a loose rule does not have:
    //
    // 1. **Variants.** `md:type-prose` and `hover:type-claim` become expressible; a
    //    plain class in `globals.css` gets no variants at all.
    // 2. **Layer.** A loose rule written after `@import "tailwindcss"` sits outside
    //    every cascade layer, so at equal specificity it outranks the whole
    //    utilities layer — which is exactly the source-order hazard the migration
    //    kept documenting on `leading-*`. Registered utilities live *in* the layer.
    //
    // So the pattern is `^@utility <name> {`, and a later "simplification" back to a
    // plain class fails here instead of silently losing both.
    const css = readFileSync(join(SRC_DIR, 'styles', 'globals.css'), 'utf8')
    const block = (name: string): string =>
      css.match(new RegExp(`^@utility ${name}\\s*\\{[^}]*\\}`, 'm'))?.[0] ?? ''

    const expected: [name: string, size: string, leading: string][] = [
      ['type-page-title', '22px', '30px'],
      ['type-claim', '17px', '26px'],
      ['type-claim-lg', '20px', '28px'],
      ['type-display', '24px', '28px'],
      ['type-prose', '13px', '20px'],
      ['type-cell', '13px', '18px'],
      ['type-meta', '12px', '16px'],
      ['type-badge', '11px', '14px'],
    ]
    for (const [name, size, leading] of expected) {
      const found = block(name)
      expect(found, `.${name} is not registered as an @utility at all`).not.toBe('')
      expect(found, `.${name} is not ${size} / ${leading}`).toMatch(
        new RegExp(
          `font-size:\\s*${size.replace('.', '\\.')}\\s*;[\\s\\S]*line-height:\\s*${leading.replace('.', '\\.')}\\s*;`,
        ),
      )
    }
    // ⭐ §2.2's row for table headers / metadata / counts, and its modifier. ⭐ The
    // all-caps and the tracking are asserted on `.caps` and **not** on `.type-meta`,
    // because they are a *look*, not a size — see the reasoning in `globals.css`.
    // Putting them on the size class would make "small" and "shouted" synonymous.
    expect(block('caps')).toMatch(/text-transform:\s*uppercase/)
    expect(block('caps')).toMatch(/letter-spacing:\s*0\.06em/)
    // ⭐ And the assertion that `.type-meta` did **not** quietly acquire them.
    expect(block('type-meta')).not.toMatch(/text-transform/)

    // ⭐ **A size class must not choose the family, and this is the assertion that
    // says so.** §2.1 puts serif on 标题与主张, which reads like a property of those
    // rows — and the first version of `globals.css` did exactly that, putting
    // `font-family: var(--font-serif)` on `.type-page-title` and `.type-claim*`.
    //
    // ⭐ The migration found the reason within the hour: a claim is not always
    // words. `RetrospectivePage` renders a score and `StopLossPrompt` renders a
    // number of years, both already carrying `.num` — mono, tabular, rule 2. A class
    // that declares both size and family wins at equal specificity over `.num`, so
    // three numbers would have been silently set in Songti. And `.serif` already
    // exists, is used 34 times, and is the honest home for §2.1's rule: a size says
    // how big, `.serif` says who is speaking.
    for (const name of ['type-page-title', 'type-claim', 'type-claim-lg', 'type-display']) {
      expect(block(name), `.${name} must not declare a font-family`).not.toMatch(/font-family/)
    }
    // ⭐ The body sizes do pin sans, because inheriting is how a 13px paragraph ends
    // up in a serif the author put there for a heading two lines up.
    for (const name of ['type-prose', 'type-cell', 'type-meta', 'type-badge']) {
      expect(block(name), `.${name} should pin --font-sans`).toMatch(
        /font-family:\s*var\(--font-sans\)/,
      )
    }
    // ⭐ And §2.1's rule still has a home — `.serif`, which is **not** an `@utility`
    // because it is not a size and it predates the scale. It stays a plain class.
    expect(css).toMatch(/^\.serif\s*\{[^}]*font-family:\s*var\(--font-serif\)/m)
  })

  it('uses the scale, rather than leaving it declared and unused', () => {
    // ⭐ A class nothing imports is a comment with a selector. §0's own diagnosis
    // was a document that sat in the repo looking authoritative; a scale that
    // `globals.css` defines and no page uses is the same failure one layer down.
    //
    // ⭐ **Usage is counted over components only, and that detail was the first
    // thing this assertion got wrong.** `occurrences()` walks the CSS too, and the
    // definition `.type-page-title {` matches its own name — the preceding `.` is
    // not a word character, so the lookbehind passes. Every class therefore scored
    // exactly one use and the real number was zero. A rule that counts the thing it
    // is measuring as one of its own samples is a rule whose number means nothing.
    // The scale's home is the stylesheet; its users are in `.tsx`.
    //
    // ⭐ **And the bound is per class, because one number would have been wrong in
    // both directions.** The first version wanted ≥ 5 of everything and failed on
    // `.type-page-title` at 1 — which is not a defect but the truth: the shell
    // renders exactly one `<h1>` for the whole application, so five uses would mean
    // five page titles. A threshold that cannot distinguish 「used once, correctly」
    // from 「never adopted」 is not a threshold. So each row carries the range its
    // role actually implies, and `max` exists because for a page title a *second*
    // use is the bug.
    const components = FILES.filter((f) => f.endsWith('.tsx') || f.endsWith('.ts'))
    const bounds: [name: string, min: number, max: number][] = [
      // One `<h1>` in the shell. Two would mean something else is a page title.
      ['type-page-title', 1, 1],
      // A card's sentence, a note's title, a company's name. §2.2's claim row — the
      // one the tree was missing entirely before this spec.
      ['type-claim', 5, 40],
      ['type-claim-lg', 3, 20],
      // The quote on an instrument page, plus at most a second hero figure. ⭐ Kept
      // small on purpose: §7.1's L0 says the data never moves, and a display class
      // that spread would turn "a figure" into "a headline".
      ['type-display', 1, 6],
      ['type-prose', 40, 400],
      ['type-cell', 3, 200],
      ['type-meta', 10, 200],
      ['type-badge', 20, 400],
    ]
    for (const [name, min, max] of bounds) {
      const uses = occurrences(new RegExp(`(?<![\\w-])${name}(?![\\w-])`), components).length
      expect(
        uses,
        `.${name} is used ${uses} time(s); the scale expects ${min}–${max}`,
      ).toBeGreaterThanOrEqual(min)
      expect(uses, `.${name} is used ${uses} time(s); the scale expects ${min}–${max}`)
        .toBeLessThanOrEqual(max)
    }
  })

  it('uses `.caps` for the table header look rather than hand-rolling it', () => {
    // ⭐ **This assertion exists because the migration found the third spelling.**
    // `DataTable`'s `<th>` carried `uppercase tracking-[0.06em]` — §2.2's 「全大写 +
    // letter-spacing: 0.06em」 written out as two Tailwind utilities, in a codebase
    // that already had a class for it. ⭐ And it was on `type-badge` (11px) rather
    // than the 12px §2.2 gives a header.
    //
    // A grep for the utilities is the check that would have caught it on day one,
    // and it is here rather than left to review because 「同一个概念一个家」 fails in
    // exactly this shape: not a bug, just the third place somebody spelled it.
    //
    // ⭐ **Components only — and this is `F-139` again, one test over.** The first
    // version walked every file and reported `globals.css:188
    // text-transform: uppercase;`, which is `.caps`'s **own definition**. The scale's
    // home is the stylesheet and a rule about how *components* spell it cannot read
    // the stylesheet, for the same reason a usage count cannot. Two tests in one
    // commit, one lesson, because the lesson is easy to state and easy to forget:
    // any scan over "the source" must say whether the thing it is looking for is
    // allowed to live there.
    const components = FILES.filter((f) => f.endsWith('.tsx') || f.endsWith('.ts'))
    const hits = occurrences(
      /\buppercase\b|tracking-\[0\.06em\]|\btracking-wide\b|\btracking-wider\b|\btracking-widest\b/,
      components,
    )
    expect(describeHits(hits), `caps look hand-rolled:\n${describeHits(hits)}`).toBe('')
    const caps = occurrences(new RegExp('(?<![\\w-])caps(?![\\w-])'), components).length
    expect(caps, `.caps is defined in globals.css but used ${caps} time(s) in components`).toBeGreaterThanOrEqual(20)
  })
})

/**
 * V-14 — an append-only log has one rendering (spec 045 stage C).
 *
 * Authority: `docs/FRONTEND_STYLE_GUIDE.md` §8.2 names `RecordTimeline` as the place
 * an append-only event stream is drawn, and ⭐ the constitution's 「一个概念一个家」 is
 * the rule this test exists to make mechanical.
 *
 * ⭐ **Why the rule had to become a test.** Before stage C this product drew the same
 * idea two ways on purpose-free grounds: the watchlist log with a 2px left rule, an
 * event number and a 「取代 #N」; the card's lifecycle as a bare `<ul>` in `type-meta`
 * with none of those. ⭐ Both were correct about their data, and nothing was broken —
 * which is why review did not catch it and why no status code ever will. ⭐ The class
 * of defect is 「同一个概念两个家」, and it is invisible to every other test here.
 *
 * ⭐ **What is checked, and the two things that are deliberately not.** The rule is
 * 「a page may not map a `.events` / `.history` array onto a list element itself」 —
 * i.e. it catches the *shape* of the second home, not the presence of a second
 * vocabulary. ⭐ It does not police which words a label uses: `改口` and 「修改理由」 are
 * both defensible sentences about the same event, and a test that insisted on one
 * spelling would be enforcing a taste. ⭐ Nor does it require `RecordTimeline` to be
 * used at all — the two call sites are asserted by count below, so a future fourth log
 * that has no common shape can opt out and say so, ⭐ but it cannot opt out silently.
 */
describe('V-14 — an append-only log has one rendering', () => {
  // ⭐ Page files only. `RecordTimeline` itself and the adapters are the component, and
  // a rule about pages cannot read the component it is protecting — F-139, third time.
  const pages = FILES.filter(
    (file) => !file.includes('/components/') && (file.endsWith('.tsx') || file.endsWith('.ts')),
  )

  it('has no page mapping an event array onto a list element', () => {
    // ⭐ **`.map` and nothing else, and the first version of this regex was wrong
    // twice.** It also matched `length > 0 &&`, so it reported
    // `{card.events.length > 0 && <CardTimeline events={card.events} />}` — ⭐ the
    // correct delegation, in the file that delegates. ⭐ That is `F-148` for the third
    // time in three commits, and it is worth naming the shape: a rule written as
    // 「do not touch this field」 catches the guard that makes the good case good.
    // ⭐ **A rule about a shape must be written against the shape it forbids**, which
    // here is 「mapping the array into JSX yourself」, not 「naming the array in a page».
    //
    // ⭐ `occurrences` already strips comments, so this cannot match the explanation
    // above it. ⭐ The first version stripped comments a second time by hand and
    // called a `read()` helper that does not exist in this file — ⭐ caught by the
    // compiler, and the reason it is written down: do not re-implement what the helper
    // does, and do not call a function you have not read.
    const hits = occurrences(/\.(events|history)\s*\.\s*map\s*\(/, pages)
    expect(
      describeHits(hits),
      `a page draws an event log itself instead of using RecordTimeline:\n${describeHits(hits)}`,
    ).toBe('')
  })

  it('has every log going through the one component', () => {
    // **A count, not a name.** The logs in this product are a card's lifecycle, the
    // watchlist's, and a note's review history. A test that named the files would pass
    // unchanged after somebody deleted one adapter and inlined the list again, so the
    // assertion is on the *number* — that is what fails when a home is abandoned.
    //
    // Three, and it was two when this was written. The review history arrived together
    // with the note panel that can show it; had the adapter been added without that
    // panel, this count would have been raised first and a dead adapter would have
    // shipped. The number guards against a registry grown on faith, and it only works
    // if it is raised when a caller appears, not when it is convenient.
    //
    // ⭐ **The path filter takes both separators.** `FILES` holds raw platform paths and
    // only `RELATIVE()` normalises them, so the first version filtered on
    // `'/components/data/'` and found **zero** files — ⭐ and then asserted `toBe(2)`
    // against nothing and reported 「found 0」, ⭐ which reads as "somebody deleted both
    // adapters" and was actually "the filter never matched a file". A filter that can
    // match nothing is a test that reports a false cause.
        const adapters = occurrences(
      /export function (CardTimeline|WatchlistTimeline|NoteReviewTimeline)\(/,
      FILES.filter((file) => /components[\\/]data[\\/]/.test(file)),
    )
    expect(
      adapters.length,
      `expected 3 RecordTimeline adapters, found ${adapters.length}:\n${describeHits(adapters)}`,
    ).toBe(3)
  })

  it('uses `.mark` only where no utility sets a border colour', () => {
    // ⭐⭐ **This exists because a 2px left rule rendered in the wrong colour, and no
    // class-name assertion could see it.**
    //
    // `.mark` is hand-written in `globals.css` — `border-left: 2px solid
    // var(--color-rule)` as a **shorthand** — in a rule that sits outside every
    // `@layer`, because it is written after the `@import`. ⭐ An unlayered rule beats
    // the whole utilities layer, ⭐ so on `RecordTimeline`'s rows the utility classes
    // `border-l-transparent` and `border-l-[color:var(--color-ink-faint)]` both lost,
    // ⭐ and **every row of every log rendered with the same left rule** — ⭐ which
    // silently deleted the only thing rule 7 asks colour to do in that component.
    //
    // ⭐ The fix was to stop using `.mark` there. ⭐ **This test is the other half of
    // that fix**: it says the rule is only for elements whose border colour is *not*
    // set by a utility, ⭐ so the next component to reach for it to get a 2px rule
    // finds out here rather than by looking at a screenshot.
    const uses = FILES.filter((f) => f.endsWith('.tsx'))
    // ⭐ **Three quote characters, not two.** ⭐ The first two versions matched `['"]`
    // ⭐ and both missed `` className={`mark …`} `` ⭐ — ⭐ a template literal, ⭐ which
    // is what the tone-dependent rows use, ⭐ and which is exactly where a conditional
    // border colour lives. ⭐ A scan that cannot see template literals ⭐ cannot see
    // half the places a className is written, ⭐ and it is the same defect as
    // `F-154`'s path separator: ⭐ a pattern that assumes a shape the codebase does
    // not always have.
    //
    // ⭐ **And the mutation check is what found it** ⭐ — ⭐ the fix script reported
    // 「36 classNames changed」 ⭐ and the rule then reported one more, ⭐ in a
    // template literal ⭐ that the script's own pattern had skipped. ⭐ A fix tool and
    // a gate that disagree is a *good* outcome ⭐ and the disagreement has to be
    // resolved in the gate's favour ⭐ by widening what the fix tool sees.
    const hits = uses
      .map((file) => ({ file, text: stripComments(readFileSync(file, 'utf8'), false) }))
      .flatMap(({ file, text }) =>
        text
          .split(/\r?\n/)
          .map((line, index) => ({ file, line, index }))
          .filter(({ line }) => /['"`][^'"`]*\bmark\b[^'"`]*['"`]/.test(line))
          .map(({ file: f, line, index }) => ({ file: RELATIVE(f), line: index + 1, text: line.trim() })),
      )
    // ⭐ **Every occurrence is a hit, and the filter that said otherwise was the
    // mistake.** ⭐ One version excluded lines containing `border-l-`, ⭐ on the
    // theory that those were fine ⭐ — ⭐ and they are not: ⭐ `.mark`'s `border-left`
    // **shorthand** is unlayered, ⭐ so it beats `border-l-[color:…]` in exactly those
    // lines. ⭐ A probe found **thirty-six** live examples across twelve files ⭐ whose
    // rows **all render with `--color-rule`**, ⭐ not the colour they ask for — ⭐ so
    // the filter was protecting the bug. ⭐ The rule is therefore the simple one:
    // **`.mark` and a `border-*` utility do not go on the same element.**
    expect(
      describeHits(hits),
      [
        '`.mark` sets `border-left: 2px solid var(--color-rule)` in globals.css,',
        'in a rule outside every @layer, so a `border-l-*` utility on the same',
        'element loses to it. Every hit below asks for a colour it will not get:',
        describeHits(hits),
      ].join('\n'),
    ).toBe('')
  })

  it('renders an absent detail rather than an empty second line', () => {
    // ⭐ **This asserts wiring, not behaviour, and the difference is the point.**
    //
    // The first version asserted `toContain('absentDetail')` — ⭐ which is a check that
    // the *word* appears in the file, and the word appears in the props interface, the
    // destructuring, the JSDoc and the default. ⭐ A mutation that replaced the render
    // site `{absentDetail}` with `{''}` left every one of those five mentions intact,
    // so the test stayed green while the component rendered an empty second line — ⭐
    // the exact defect this test was written to prevent. So the assertion is on the
    // **render expression**, which is the thing that can actually be wrong.
    //
    // ⚠️ **And it still is not a behaviour test, because this repository cannot render
    // a component in a test.** There is no `jsdom` and no `@testing-library/react` in
    // `devDependencies` — ⭐ all ten test files are pure logic or source scans — and
    // adding a DOM environment would be a dependency-budget decision (V-07) that this
    // stage did not make. ⭐ So the honest scope of this test is 「the sentence is
    // wired to the render site and the adapter supplies a real one」, and the honest
    // consequence is written into the failure message: ⭐ an empty second line is not
    // something this suite can see, only a reviewer reading the component can.
    //
    // ⭐ Built with `join`, not with `/` in a literal, for the reason the assertion
    // count filter above needed both separators. ⭐ One normalisation mistake in this
    // file would otherwise be made twice, in two different ways.
    const component = readFileSync(
      [SRC_DIR, 'components', 'data', 'RecordTimeline.tsx'].join('/'),
      'utf8',
    )
    expect(
      component,
      'RecordTimeline has no absent-detail sentence; an empty second line is not an answer',
    ).toContain('{absentDetail}</p>')
    expect(
      readFileSync([SRC_DIR, 'components', 'data', 'timelineAdapters.tsx'].join('/'), 'utf8'),
      'an adapter passes an empty absence sentence, so the row renders nothing where it must state the absence',
    ).toContain('absentDetail="（离开时没有留下说明）"')
  })
})

/**
 * V-15 — a modal is not inside the subtree it disables (spec 045 stage D).
 *
 * ⭐ **Why a source rule when the behaviour has an E2E test.** The E2E test is the
 * real assertion; this one exists because the E2E test is *also* satisfied by a
 * palette that has no `inert` at all ⭐ if the Tab trap happens to be working, and
 * the failure that matters — a frozen modal — ⭐ looks like a working modal to every
 * test that does not try to type into it. ⭐ This rule pins the **mechanism**, so
 * the trap and the `inert` each have to be there.
 *
 * ⭐ **The rule is structural, not textual.** 「the palette must be portalled」 could
 * be checked by looking for `createPortal`, and that version is weaker than it looks:
 * a `createPortal` in the file says nothing about *where it portals to*. ⭐
 * `document.body` is the assertion, because it is the specific fact that makes the
 * panel a **sibling** of `#root` rather than a descendant of the shell.
 */
describe('V-15 — the modal escapes the subtree it disables', () => {
  // ⭐ **Two files, and the split is the point.** The three behaviours live in
  // `useModalFocus` (so a Drawer can reuse them) and the one thing only the palette
  // does is the portal. ⭐ The first version of this rule read only
  // `CommandPalette`, and it passed while the hook carried all four claims ⭐ — so a
  // rule that follows a refactor has to be pointed at the file that ended up owning
  // the thing.
  const palette = readFileSync(
    [SRC_DIR, 'components', 'nav', 'CommandPalette.tsx'].join('/'),
    'utf8',
  )
  const hook = readFileSync([SRC_DIR, 'useModalFocus.ts'].join('/'), 'utf8')
  const shell = readFileSync([SRC_DIR, 'app', 'AppShellFrame.tsx'].join('/'), 'utf8')

  it('portals the panel to document.body, not into the shell', () => {
    // ⭐ The argument is the whole point, so the assertion is on the argument and not
    // on the presence of the function. ⭐ A `createPortal(node, someDivInsideTheShell)`
    // satisfies 「the palette is portalled」 and fails here, ⭐ which is the version of
    // this rule that would have let the bug through.
    //
    // ⭐ **`\s*[,)]` after `document.body`, and the mutation check is why.** The first
    // version ended the pattern at `document\.body`, ⭐ so `document.body
    // .firstElementChild` — the portal target being the shell's own first child, ⭐
    // which puts the panel straight back inside the subtree it disables — matched as
    // a prefix and the mutant survived. ⭐ A rule that checks a *prefix* of a value
    // is not checking the value, and `F-148` has a mirror image: ⭐ I have now been
    // wrong in both directions on the same rule, wide in stage C and narrow here.
    expect(
      palette,
      'the panel must portal into document.body itself, or `inert` on the shell freezes it',
    ).toMatch(/createPortal\([\s\S]*?document\.body\s*[,)]/)
  })

  it('the palette delegates the three behaviours instead of re-implementing them', () => {
    // ⭐ **The two-homes rule, applied to a refactor.** A Drawer is a modal that
    // arrives from the side and needs the same three things, ⭐ so 「reuse the
    // palette's mechanism」 is only true while the mechanism is not inside the
    // palette. ⭐ This asserts the delegation and the *absence* of the logic, ⭐ and
    // the second half is the one that would catch a paste.
    //
    // ⭐ **Two things the first version got wrong, both found by mutation, and both
    // the same mistake: a regex cannot tell code from prose.**
    //
    // 1. it matched `/useModalFocus\(\{[^}]*open[^}]*panelRef[^}]*\}\)/` against
    //    the **raw** source, ⭐ so commenting the call out satisfied it — the text
    //    `// useModalFocus({ open, panelRef })` still contains every token. ⭐ A
    //    delegation that has been commented out is the most likely way for a
    //    refactor to be silently undone.
    // 2. `[^}]*open[^}]*` also matches `useModalFocus({ open: !open, panelRef })`, ⭐
    //    which is a call with the flag **inverted** — ⭐ exactly the mistake a
    //    refactor makes while moving code, and it type-checks because both are
    //    objects with the same keys. ⭐ The compiler is no help here.
    //
    // ⭐ So the assertion is the **exact** call on **comment-stripped** source.
    // `stripComments` is this file's own helper and its whole reason for existing.
    const paletteCode = stripComments(palette, false)
    expect(paletteCode, 'the palette does not call the shared hook').toMatch(
      /useModalFocus\(\{\s*open,\s*panelRef\s*\}\)/,
    )
    for (const [label, pattern] of [
      ['its own focus recording', 'previousFocus.current'],
      ['its own inert write', '.inert ='],
      // ⭐ **`panel`-scoped, and this narrowing is the third time on this rule.**
      // The first version banned the bare string `addEventListener('keydown'`, ⭐ and
      // the palette legitimately has one: `useCommandPalette` binds ⌘K on `window`,
      // ⭐ which is the shortcut and has nothing to do with a focus trap. ⭐ A
      // negative assertion written wider than the thing it forbids fails on correct
      // code, ⭐ and the reflex to narrow it must not become 「delete the assertion」 —
      // so the pattern names the panel, which is what would actually be duplicated.
      ['its own panel-scoped keydown listener', "panel.addEventListener('keydown'"],
    ] as const) {
      expect(paletteCode, `the palette still has ${label}`).not.toContain(pattern)
    }
  })

  it('makes the shell inert while open, and undoes it on close', () => {
    // ⭐ **Three claims, because the two halves fail differently.** Setting `inert`
    // and never clearing it produces a page that looks fine and cannot be clicked;
    // ⭐ clearing it to a hard-coded `false` produces the same bug the moment
    // something else wants the shell inert, ⭐ so the restore must assign the value
    // it read.
    expect(hook, 'the hook never sets inert on anything').toMatch(/\.inert = true/)
    expect(hook, 'the hook restores inert to a literal instead of the value it read')
      .toMatch(/target\.inert = wasInert/)
  })

  it('records what had focus, and gives it back', () => {
    // ⭐ `previousFocus.current = null` would pass a test that only looks for the
    // ref's existence, ⭐ so the assertion is on the *recording* — `activeElement` —
    // and on the `isConnected` check that keeps a restore from silently becoming a
    // no-op against a detached node.
    expect(hook, 'nothing records where focus came from').toMatch(
      /previousFocus\.current[\s\S]{0,120}activeElement/,
    )
    expect(
      hook,
      'the restore does not check the element is still in the document',
    ).toContain('isConnected')
  })

  it('traps Tab on the panel, not on the document', () => {
    // ⭐ **The placement, because it is the whole finding.** A `window` listener sees
    // `Tab` only when nothing above it handled the event, ⭐ and a `keydown` on the
    // focused input is handled by React's root listener first ⇒ **backward Tab would
    // work and forward Tab would silently not.** `F-164`.
    //
    // ⭐ **Comment-stripped, for the same reason as the delegation assertion above** —
    // ⭐ a comment that says 「the trap is installed on `panel.addEventListener`」 would
    // otherwise satisfy this test, ⭐ and that sentence is exactly what someone
    // writing a comment about a refactor would write.
    const hookCode = stripComments(hook, false)
    expect(hookCode, 'the trap is not installed on the panel itself').toContain(
      "panel.addEventListener('keydown'",
    )
    expect(hookCode, 'the trap is installed on the document or the window').not.toMatch(
      /window\.addEventListener\('keydown'|document\.addEventListener\('keydown'/,
    )
    // ⭐ **Both directions, as two conditions.** One condition traps one direction,
    // ⭐ and a half-trap passes any test that only walks forwards.
    expect(hookCode, 'the forward wrap is missing').toMatch(
      /!event\.shiftKey && current === last/,
    )
    expect(hookCode, 'the backward wrap is missing').toMatch(
      /event\.shiftKey && current === first/,
    )
    // ⭐ **And the "no stops at all" branch, which is the one an empty result list
    // reaches.** ⭐ The palette's list is `rows.length === 0` or `rows.length`
    // buttons, ⭐ so a query with no matches leaves the panel with **one focusable
    // thing — the input**. ⭐ A branch that assumes at least two stops, ⭐ or that
    // falls back to focusing a `div` with no `tabindex` (a silent no-op), ⭐ leaves the
    // reader on the page behind with the panel still open. ⭐ Asserted because the
    // E2E trap test only ever walks a *populated* panel.
    expect(hookCode, 'the empty-panel branch is missing').toMatch(
      /stops\.length === 0[\s\S]{0,200}panel\.focus\(\)/,
    )
    expect(
      stripComments(palette, false),
      'the panel cannot take programmatic focus without a tabindex',
    ).toMatch(/tabIndex=\{-1\}/)
  })

  it('has one id contract between the shell and the hook', () => {
    // ⭐ Both sides use the same constant, so a rename is a type error in
    // `AppShellFrame` rather than a runtime no-op where the page silently stops
    // going inert. ⭐ Asserting the *contract* rather than the literal id means the
    // test does not have to be edited when the id is, ⭐ and the constant lives with
    // the code that uses it — the hook, which is what has to find the element.
    expect(hook, 'the hook does not export the shell id it looks up').toMatch(
      /export const SHELL_ID/,
    )
    expect(shell, 'the shell does not set the id the hook looks for').toMatch(
      /id=\{SHELL_ID\}/,
    )
    expect(palette, 'the palette still owns the id it no longer uses').not.toContain(
      'SHELL_ID',
    )
  })
})

/**
 * The import specifiers a source file names, as bare package names.
 *
 * ⭐ **Four forms, because a codebase uses four.** ⭐ `import x from 'a'` ⭐,
 * ⭐ `import 'a'` (a side-effect import) ⭐, ⭐ `export … from 'a'` ⭐, and
 * ⭐ `import('a')` (dynamic). ⭐ The first version matched only the first ⭐ and
 * ⭐ would have reported a package as uncalled ⭐ on the strength of a file that
 * ⭐ imported it in a form the pattern did not know ⭐ — ⭐ which is `F-154` again:
 * ⭐ a pattern that assumes a shape the codebase does not always have.
 *
 * ⭐ **Comments are stripped first, by the file's own `stripComments`.** ⭐ This
 * ⭐ function's own docstring names `@milkdown/preset-commonmark` ⭐ and several
 * ⭐ other packages ⭐ in order to explain the rule ⭐ - ⭐ and without stripping,
 * ⭐ every one of those sentences would have counted as a call site ⭐ and the rule
 * ⭐ would have passed for the wrong reason.
 */
function bareImports(file: string): string[] {
  const source = stripComments(readFileSync(file, 'utf8'), false)
  const found: string[] = []
  const forms = [
    /^\s*import\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"]/gm,
    /^\s*export\s+(?:type\s+)?(?:\*|\{[\s\S]*?\})\s+from\s+['"]([^'"]+)['"]/gm,
    /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g,
  ]
  for (const form of forms) {
    for (const match of source.matchAll(form)) found.push(match[1])
  }
  return found
}

/**
 * The package a bare specifier names, or `null` if it names no package.
 *
 * ⭐ **Two segments for a scoped name, one for an unscoped one.** ⭐
 * `@milkdown/react` is one package ⭐ — ⭐ and so is `clsx/clsx.mjs` ⭐, ⭐ because
 * ⭐ a subpath import of an unscoped package is still that package. ⭐ A rule that
 * ⭐ took the first segment of everything would report `@milkdown/react` ⭐ and
 * ⭐ `clsx/clsx.mjs` ⭐ as two packages ⭐ that are not in `package.json` ⭐ - ⭐
 * ⭐ which would be a red test about a package that is declared.
 */
function packageOf(specifier: string): string | null {
  if (specifier.startsWith('.') || specifier.startsWith('/')) return null
  if (specifier.startsWith('node:')) return null
  const parts = specifier.split('/')
  if (specifier.startsWith('@')) return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : specifier
  return parts[0]
}

describe('V-16 · the dependency budget has two halves', () => {
  // ⭐⭐ **V-07 asks one question: 「is this package approved?」 ⭐ — ⭐ by reading
  // `package.json`. ⭐ It cannot see the other direction ⭐ and ⭐ it never could ⭐:
  // ⭐ nothing in that file says who imports what. ⭐ Two states are therefore
  // ⭐ entirely invisible to it, ⭐ and both of them were live in this repository:
  //
  // ⭐ **Declared but never imported.** ⭐ `@milkdown/core`, `@milkdown/react` and
  // ⭐ `@milkdown/preset-commonmark` have been in `dependencies` since 2026-09-28,
  // ⭐ they are in V-07's own allowlist ⭐ with the note 「Installed; **not yet
  // ⭐ wired into the vault page**」 ⭐, ⭐ and **no source file imports them**.
  // ⭐ The build ships 0 bytes of them ⭐ — ⭐ they cost a licence-scan row, an
  // ⭐ install, and a line of documentation that reads like a decision.
  //
  // ⭐ **Imported but not declared.** ⭐ Measured from the installed typings:
  // ⭐ getting Markdown back out of a Milkdown editor ⭐ - ⭐ the whole point of an
  // ⭐ editor ⭐ - ⭐ is `listenerCtx.markdownUpdated` ⭐ in `@milkdown/plugin-listener`,
  // ⭐ `getMarkdown()` ⭐ in `@milkdown/utils`, ⭐ or `Serializer` ⭐ in
  // ⭐ `@milkdown/transformer`. ⭐ **All three are transitive.** ⭐ So the next
  // ⭐ person to wire the editor reaches a package that resolves ⭐ - ⭐ npm hoists
  // ⭐ it ⭐ - ⭐ compiles ⭐, and V-07 says nothing ⭐ because the package is not
  // ⭐ in `package.json` ⭐ and V-07 only reads `package.json`.
  //
  // ⭐ **This is V-11's lesson applied to dependencies.** ⭐ The icon registry grew
  // ⭐ to thirteen entries and eight of them were dead ⭐, ⭐ and the answer then was
  // ⭐ 「dead entries have to be a gate rather than a habit」 ⭐ — ⭐ and a dependency
  // ⭐ list is a registry ⭐ and grows the same way ⭐ and for the same reason:
  // ⭐ 「the owner approved it」 is a statement about the past, not a caller.

  const pkg = JSON.parse(readFileSync(join(SRC_DIR, '..', 'package.json'), 'utf8')) as {
    dependencies: Record<string, string>
    devDependencies?: Record<string, string>
  }
  const declared = Object.keys(pkg.dependencies).sort()
  const dev = Object.keys(pkg.devDependencies ?? {}).sort()

  it('every runtime dependency is imported by a source file', () => {
    // ⭐ **`e2e` is included, `src` alone is not enough.** ⭐ A dependency used
    // ⭐ only by a test is a devDependency ⭐ - ⭐ shipping it in `dependencies`
    // ⭐ costs every reader of the page and helps nobody.
    //
    // ⭐ **`devDependencies` are exempt and deliberately not checked the other
    // ⭐ way.** ⭐ `@playwright/test` and `vitest` are installed ⭐ - ⭐ checking
    // ⭐ that a dev dependency is imported would be a second rule about a list
    // ⭐ nobody ships.
    const callers = new Map<string, string[]>()
    for (const file of [...FILES, ...E2E_FILES]) {
      for (const specifier of bareImports(file)) {
        const name = packageOf(specifier)
        if (name === null) continue
        const list = callers.get(name) ?? []
        list.push(RELATIVE(file))
        callers.set(name, list)
      }
    }

    // ⭐ **The exemptions are named, and each carries the number that made it
    // ⭐ necessary.** ⭐ This is not 「register it just in case」 ⭐ (F-149) ⭐ in
    // ⭐ reverse ⭐ - ⭐ here the entry exists precisely because it has **no**
    // ⭐ caller ⭐, ⭐ and the reason is a pending product decision ⭐ rather than an
    // ⭐ oversight. ⭐ Removing the exemption removes the package ⭐; ⭐ keeping
    // ⭐ the package without the exemption is a red test ⭐ - ⭐ and that is the
    // ⭐ intended state ⭐ until the owner rules.
    const APPROVED_BUT_UNWIRED: Record<string, string> = {
      '@milkdown/core':
        'Spec 026, approved by the owner 2026-09-28. ⭐ Measured cost of wiring ' +
        'it (Vite, 2026-09-30): **+362.82 kB raw / +110.59 kB gzip** ⭐ on a ' +
        '535.36 kB / 164.55 kB baseline ⭐ — ⭐ and the three approved packages ' +
        'cannot read Markdown back out of the editor, ⭐ so wiring it also needs ' +
        'a fourth package nobody approved. ⭐ Pending the owner. Record: ' +
        '.ai/decisions.md',
      '@milkdown/react': 'Same decision as @milkdown/core ⭐ - ⭐ one ruling covers all three.',
      '@milkdown/preset-commonmark': 'Same decision as @milkdown/core ⭐ - ⭐ one ruling covers all three.',
    }

    // ⭐⭐ **A name with a reason is exempt, and the first version was not.** ⭐ It
    // ⭐ built `APPROVED_BUT_UNWIRED` ⭐ - ⭐ a map of package to reason ⭐ - ⭐ and
    // ⭐ then reported all three Milkdown packages anyway ⭐, ⭐ with the reason
    // ⭐ only appended to the message for two of them ⭐. ⭐ **An exemption map
    // ⭐ that does not exempt is worse than no map** ⭐: ⭐ it reads as 「this was
    // ⭐ considered」 ⭐ and the suite is red ⭐, ⭐ so the next person deletes the
    // ⭐ map ⭐ and ships the problem.
    const uncalled = declared
      .filter((name) => !callers.has(name))
      .filter((name) => !(APPROVED_BUT_UNWIRED[name] ?? '').trim())

    // ⭐ **And a blank reason is not an exemption**, ⭐ for the reason
    // ⭐ `CHECK_EXEMPTION_UNREASONED` exists ⭐ in the Python checks ⭐: ⭐ an
    // ⭐ entry with an empty string would otherwise be the easiest way to make
    // ⭐ this test green ⭐ — ⭐ one character ⭐ — ⭐ and the whole value of the map
    // ⭐ is that its entries say something.
    const unreasoned = Object.entries(APPROVED_BUT_UNWIRED)
      .filter(([, reason]) => !reason.trim())
      .map(([name]) => name)
    expect(
      unreasoned,
      unreasoned.length === 0
        ? ''
        : `these exemptions state no reason, and an unreasoned one is not an exemption:\n${unreasoned.join('\n')}`,
    ).toEqual([])

    expect(
      uncalled,
      uncalled.length === 0
        ? ''
        : [
            'These are in `dependencies` and no source file imports them, so they',
            'ship 0 bytes ⭐ - ⭐ they cost an install, a licence-scan row, and a',
            'line of documentation that reads like a decision. Either wire one up',
            'or delete it ⭐ - ⭐ and if the answer is 「not yet」 ⭐, say why in',
            '`APPROVED_BUT_UNWIRED` above:',
            ...uncalled,
          ].join('\n'),
    ).toEqual([])

    // ⭐ **And the exemption is not a permanent silence.** ⭐ Deleting the package
    // ⭐ while leaving the entry is a red test ⭐ — ⭐ the entry names a package
    // ⭐ that is no longer installed ⭐, ⭐ which is a stale document ⭐ - ⭐ and a
    // ⭐ stale document in an exemption list is how the next reader decides the
    // ⭐ list is not maintained.
    const stale = Object.keys(APPROVED_BUT_UNWIRED).filter((name) => !declared.includes(name))
    expect(
      stale,
      stale.length === 0
        ? ''
        : `these exemptions name packages that are no longer in dependencies:\n${stale.join('\n')}`,
    ).toEqual([])
  })

  it('every bare import is a declared dependency', () => {
    // ⭐ The direction V-07 cannot see, and the one that bites later. ⭐ npm
    // ⭐ hoists transitive packages into the root `node_modules` ⭐, ⭐ so an import
    // ⭐ of one resolves ⭐, ⭐ type-checks ⭐, ⭐ and builds ⭐ - ⭐ and then a
    // ⭐ version bump of an unrelated package can remove it.
    //
    // ⭐ **`devDependencies` count as declared here.** ⭐ An E2E spec importing
    // ⭐ `@playwright/test` is correct ⭐, ⭐ and the point of the rule is that
    // ⭐ *something* declares it ⭐ - ⭐ not that it ships to the reader.
    const declaredOrDev = new Set([...declared, ...dev])
    const undeclared = new Map<string, string[]>()
    for (const file of [...FILES, ...E2E_FILES]) {
      for (const specifier of bareImports(file)) {
        const name = packageOf(specifier)
        if (name === null || declaredOrDev.has(name)) continue
        const list = undeclared.get(name) ?? []
        list.push(RELATIVE(file))
        undeclared.set(name, list)
      }
    }

    const report = [...undeclared.entries()]
      .map(([name, where]) => `${name}\n${where.map((f) => `      ${f}`).join('\n')}`)
      .join('\n')
    expect(
      report,
      [
        'These resolve ⭐ (npm hoists transitive packages) ⭐, compile ⭐, and are',
        'in nobody`s package.json ⭐ - ⭐ so a version bump can remove them without',
        'anything failing here first:',
        report,
      ].join('\n'),
    ).toBe('')
  })
})
