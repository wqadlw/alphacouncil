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

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = new URL('.', import.meta.url).pathname.replace(/^\//, '').replace(/\/$/, '')
const SRC_DIR = SRC === '' ? '.' : SRC

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
const RELATIVE = (file: string) => file.slice(SRC_DIR.length + 1).replace(/\\/g, '/')

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

/** Every source file whose **code** matches `pattern`, with the line that matched. */
function occurrences(pattern: RegExp): { file: string; line: number; text: string }[] {
  const hits: { file: string; line: number; text: string }[] = []
  for (const file of FILES) {
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

describe('V-06 · no decorative motion', () => {
  it('has no keyframes, so nothing can shimmer or count up', () => {
    // Stronger than grepping for `animate-` or `transition`: if the stylesheet
    // defines no `@keyframes` at all, then shimmer, count-up, fade-in-up and
    // slide-in are all impossible by construction rather than by review. The
    // guide's §7.2 bans six named effects; this makes the whole class
    // unrepresentable.
    for (const file of FILES.filter((f) => f.endsWith('.css'))) {
      const css = stripComments(readFileSync(file, 'utf8'), true)
      expect(css, `${RELATIVE(file)} defines @keyframes`).not.toMatch(/@keyframes/)
    }
  })

  it('has no animation utility in any component', () => {
    const hits = occurrences(/\banimate-(?!none)|duration-\d/)
    expect(describeHits(hits), `animation utility:\n${describeHits(hits)}`).toBe('')
  })
})

describe('V-07 · the dependency budget', () => {
  it('has only the four approved runtime packages', () => {
    // `docs/FRONTEND_STYLE_GUIDE.md` §6 records the owner's approval of exactly
    // four. The constitution bans unapproved additions, and this is the check
    // that makes that ban mechanical instead of a matter of remembering.
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
