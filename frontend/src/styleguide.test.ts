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
      // licence-checked (MIT). Installed; **not yet wired into the vault page** —
      // the page currently uses a plain textarea, which is stated in its header.
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
      for (const decl of css.matchAll(/transition(?:-duration)?\s*:\s*([^;]+);/gi)) {
        const head = (decl[0].split('\n')[0] ?? '').trim()
        for (const match of decl[1].matchAll(/(\d*\.?\d+)ms/g)) {
          out.push({ where: `${RELATIVE(file)}  ${head}`, value: Number(match[1]) })
        }
      }
    }
    return out
  }

  /** §7.1's two ranges, plus the reduced-motion off switch. */
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
