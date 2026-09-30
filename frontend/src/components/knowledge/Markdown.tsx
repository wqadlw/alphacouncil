/**
 * Inline Markdown, and the component that puts a note on screen.
 *
 * ⭐ **This is the surface a knowledge base is judged on.** Every other page in this
 * product shows rows and numbers; ⭐ a note shows **prose**, ⭐ and prose is the one
 * thing the browser's defaults get most wrong. ⭐ So the blocks below are styled
 * with the same type scale as the decision that cites them — a heading in a note is
 * `.type-claim` in `.serif`, ⭐ the same as a card's claim, ⭐ because a reader
 * comparing the two has no way to know they came from different components.
 *
 * ⭐ **No `dangerouslySetInnerHTML` anywhere, and no HTML string is built.** Inline
 * emphasis is split into React nodes, ⭐ so `<script>` in a note is text. See
 * `markdown.ts` for why that is the whole design and not an omission.
 */

import { type ReactNode } from 'react'

import { cn } from '../../lib/cn'

// ── the parser, which was its own file until this commit ──────────────────
/** One block-level element. The parser's whole output type. */
export type Block =
  | { kind: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'bullet'; items: { text: string; depth: 0 | 1 }[] }
  | { kind: 'ordered'; items: string[] }
  | { kind: 'quote'; text: string }
  | { kind: 'code'; text: string; lang: string | null }
  | { kind: 'break' }

/**
 * ⭐ **Split on blank lines, then classify each chunk.**
 *
 * A line-by-line state machine is the obvious implementation and it is worse: a
 * list that continues across a blank line, a fence that contains the string
 * `---`, and a paragraph that happens to start with `>` all have to be tracked as
 * state, ⭐ and every one of those is a place the state machine gets it wrong.
 * ⭐ Block-then-classify puts the awkward cases in exactly one function (`parseList`)
 * where they can be read.
 */
function toBlocks(source: string): string[] {
  const lines = source.replace(/\r\n?/g, '\n').split('\n')
  const blocks: string[] = []
  let current: string[] = []

  let fence: string | null = null
  const flush = () => {
    if (current.length > 0) {
      blocks.push(current.join('\n'))
      current = []
    }
  }

  for (const line of lines) {
    // ⭐ **The fence is checked first, before anything else.** A code block
    // containing `---` or `# heading` or `- item` is *data*, ⭐ and a classifier
    // that looks at the fence second has already decided what those lines are.
    const fenceMatch = /^\s{0,3}(`{3,}|~{3,})\s*(\S*)\s*$/.exec(line)
    if (fence !== null) {
      current.push(line)
      if (fenceMatch && fenceMatch[1][0] === fence[0] && fenceMatch[1].length >= fence.length) {
        fence = null
      }
      continue
    }
    if (fenceMatch) {
      flush()
      current.push(line)
      fence = fenceMatch[1]
      continue
    }
    if (line.trim() === '') {
      flush()
      continue
    }
    current.push(line)
  }
  flush()
  return blocks
}

const HEADING = /^(\#{1,6})\s+(.*)$/
const BULLET = /^(\s*)[-*+]\s+(.*)$/
const ORDERED = /^(\s*)\d+[.)]\s+(.*)$/
const QUOTE = /^\s*>\s?(.*)$/
const BREAK = /^\s{0,3}([-*_])\s*(\1\s*){2,}$/
const FENCE = /^\s{0,3}(`{3,}|~{3,})\s*(\S*)\s*$/

function isBreak(chunk: string): boolean {
  return BREAK.test(chunk.trim()) && !chunk.includes('\n')
}

function parseList(chunk: string): Block[] {
  const lines = chunk.split('\n')
  const bullets: { text: string; depth: 0 | 1 }[] = []
  const ordered: string[] = []

  // ⭐ **One pass, and the first line decides which list this is.** A chunk can
  // legally start with `1.` and continue with `- `, ⭐ and deciding once ⭐ is what
  // keeps the two from interleaving into one malformed node.
  const startsOrdered = ORDERED.test(lines[0])
  for (const line of lines) {
    if (startsOrdered) {
      const match = ORDERED.exec(line)
      if (match) {
        ordered.push(match[2])
        continue
      }
    } else {
      const match = BULLET.exec(line)
      if (match) {
        // ⭐ **Indent is the depth, and only 0 or 1.** Four spaces is a code block
        // in CommonMark; ⭐ treating it as a third level would be a claim this file
        // cannot keep, ⭐ so it is clamped and the extra indent is dropped.
        const indent = (match[1] ?? '').replace(/\t/g, '    ').length
        bullets.push({ text: match[2], depth: indent >= 2 ? 1 : 0 })
        continue
      }
    }
    // ⭐ **A continuation line joins the previous item.** CommonMark's lazy
    // continuation, ⭐ and the case that makes 「one line per item」 wrong: a note
    // that wraps a bullet across two lines is one bullet, not two.
    //
    // ⭐ **Mutated through a small closure rather than through a copy.** The first
    // draft wrote `const target = startsOrdered ? ordered : bullets.map((b) => b.text)`
    // ⭐ and then wrote into `target` — ⭐ and `map` had already made a **new array**,
    // so the second half of every wrapped bullet was **silently dropped**. ⭐ A
    // renderer that loses text is the worst failure this file can have, ⭐ and it
    // looked like a parser bug for a day. ⭐ `.at(-1)` on the real array is the fix,
    // and the test that catches it is the one written before the code.
    const target = startsOrdered
      ? () => ordered
      : () => bullets
    const list = target()
    const last = list.length - 1
    if (last >= 0) {
      const item = startsOrdered
        ? (ordered[last] as string)
        : (bullets[last] as { text: string }).text
      const joined = `${item} ${line.trim()}`
      if (startsOrdered) ordered[last] = joined
      else bullets[last] = { text: joined, depth: bullets[last].depth }
    }
  }

  return startsOrdered
    ? ordered.length > 0
      ? [{ kind: 'ordered', items: ordered }]
      : []
    : bullets.length > 0
      ? [{ kind: 'bullet', items: bullets }]
      : []
}

/** Turn source text into blocks. ⭐ Exported because the tests want the shape. */
export function parseMarkdown(source: string): Block[] {
  const out: Block[] = []
  for (const chunk of toBlocks(source)) {
    if (isBreak(chunk)) {
      out.push({ kind: 'break' })
      continue
    }
    const fence = FENCE.exec(chunk.split('\n')[0])
    if (fence && chunk.includes('\n')) {
      const lines = chunk.split('\n')
      // ⭐ **Strip the opening fence and the closing one — and the closing one is
      // recognised by `closesFence`, not by 「is the last line blank」.** The first
      // draft asked whether the last line was empty, ⭐ which is a different question,
      // ⭐ so the closing ``` stayed inside the code block and **all four** fence tests
      // failed. ⭐ The rule is now a named function ⭐ so it has a name in a test.
      const closesHere = closesFence(fence[1], lines[lines.length - 1] ?? '')
      out.push({
        kind: 'code',
        lang: fence[2] || null,
        // ⭐ Nothing else is trimmed. A code block is the one place where the bytes
        // are the point, ⭐ so `.trim()` on the inside would be a small lie about
        // what the reader typed.
        text: lines.slice(1, closesHere ? -1 : undefined).join('\n'),
      })
      continue
    }
    const lines = chunk.split('\n')
    if (lines.every((line) => QUOTE.test(line))) {
      out.push({ kind: 'quote', text: lines.map((line) => QUOTE.exec(line)![1]).join(' ') })
      continue
    }
    const list = parseList(chunk)
    if (list.length > 0) {
      out.push(...list)
      continue
    }
    const heading = HEADING.exec(lines[0])
    if (heading && lines.length === 1) {
      out.push({
        kind: 'heading',
        level: heading[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        text: heading[2].trim(),
      })
      continue
    }
    out.push({ kind: 'paragraph', text: lines.join(' ') })
  }
  return out
}


/**
 * ⭐ **Links: `http(s)` and `#` only.**
 *
 * A note can contain `[click](javascript:...)`, ⭐ and rendering that as an `href`
 * would execute it. ⭐ `javascript:`/`data:`/`vbscript:` are refused rather than
 * escaped, ⭐ because the honest answer to 「this link is not safe to follow」 is to
 * print the link's text without the link, ⭐ not to print a URL that looks right and
 * does nothing.
 */
/**
 * ⭐ **A link, decided — and decided in a pure function, which is the whole shape of
 * this file.**
 *
 * ⭐ **Every decision is a function that returns a value, and the component only
 * renders what it is told.** That is not a style preference: ⭐ this repository has no
 * `jsdom` and no `@testing-library/react` (V-15 records it), ⭐ so a decision written
 * as `href === null ? <span/> : <a/>` **inside JSX is untestable** ⭐ — and the
 * mutation check proved it, ⭐ leaving four survivors:
 *
 * - 「a refused link is dropped instead of printed」 — ⭐ green, because the *test*
 *   still saw the label; ⭐ only the element tree differed, ⭐ and nothing can read an
 *   element tree here.
 * - 「`safeHref` becomes a `startsWith('https://')` prefix test」 — ⭐ green, ⭐ because
 *   the component kept calling it and the returned value happened to be right for the
 *   three test URLs.
 *
 * ⭐ So both are now values: `linkTarget` returns a **discriminated union** and
 * `safeHref` is exported. ⭐ A test can assert the decision ⭐ and the component is a
 * `switch` over a union ⭐ with no judgement left in it.
 */
export type LinkTarget =
  /** Followable. `internal` distinguishes `#…`, which must not open a new tab. */
  | { kind: 'link'; href: string; internal: boolean }
  /** ⭐ Refused. The label is still printed — the reader's words are not the problem. */
  | { kind: 'text' }

export function safeHref(raw: string): string | null {
  const trimmed = raw.trim()
  if (trimmed.startsWith('#')) return trimmed
  // ⭐ `new URL` rather than a prefix test, ⭐ because the constructor is the
  // browser's own parser and it has been right for a decade. ⭐ It buys **case
  // insensitivity** (`HTTPS://…` is a fine link ⭐ and `startsWith('https://')`
  // refuses it) ⭐ and it normalises (`https:/x` becomes `https://x`, ⭐ so that
  // near-miss is *not* a reason to prefer the prefix test — ⭐ I claimed it was, ⭐
  // and the test said otherwise).
  try {
    const url = new URL(trimmed)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    // ⭐⭐ **An empty host, and `new URL` accepts it.** `new URL('https://')` does
    // **not** throw — ⭐ it resolves to `https://` with an empty host, ⭐ so a
    // protocol-only check waves it through. ⭐ The test caught this, ⭐ and the
    // conclusion is that 「use the platform parser」 ⭐ — the advice that was right
    // about `javascript:` ⭐ — **inherits the parser's definition of valid** ⭐ and
    // has to be completed by hand. ⭐ A link with no host is a typo, not an intent.
    if (url.hostname === '') return null
    return url.href
  } catch {
    return null
  }
}

export function linkTarget(raw: string): LinkTarget {
  const href = safeHref(raw)
  if (href === null) return { kind: 'text' }
  return { kind: 'link', href, internal: href.startsWith('#') }
}

/**
 * ⭐ **Whether a line closes an open fence.**
 *
 * ⭐ Exported because the same mistake appears twice otherwise: a **length** check
 * (`>= fence.length`) and a **character** check (``` ` ``` vs `~` ```), ⭐ and a
 * fence opened with ````` ```` ````` is not closed by ``` ``` ```. ⭐ As an inline
 * expression inside `toBlocks` that rule had no name, ⭐ and the mutation check left
 * 「a shorter fence closes the block」 **green** ⭐ — the first draft had the same bug
 * and the test passed, ⭐ which is worse than having no test because it said so.
 */
export function closesFence(open: string, line: string): boolean {
  const match = /^\s{0,3}(`{3,}|~{3,})\s*$/.exec(line)
  if (match === null) return false
  return match[1][0] === open[0] && match[1].length >= open.length
}

/**
 * ⭐ **The URL alternative allows one level of parentheses, and parentheses are why.**
 *
 * The first draft wrote `\([^)\s]+\)` — ⭐ no `)` allowed inside the target — ⭐ so
 * `[点我](javascript:alert(1))` matched only up to the first `)` and the reader saw
 * a stray `)` after the label. ⭐ The test caught it while checking *link safety*,
 * ⭐ which is the useful place for a test to catch a rendering bug: ⭐ the assertion
 * was 「the label survives」, ⭐ and a stray bracket is exactly that failing. ⭐ Real
 * URLs carry parentheses too (Wikipedia is full of them), ⭐ so this was never only
 * a hostile-input case.
 *
 * ⭐ One level of nesting, because that is what CommonMark allows. ⭐ Deeper nesting
 * is not handled, ⭐ and an unclosed `(` simply does not match ⭐ — which degrades to
 * printing the text, ⭐ and printing the text is the safe direction.
 *
 * ⭐ Built from parts rather than written as one literal, ⭐ because a template
 * literal cannot contain an unescaped backtick — ⭐ the code-span alternative needs
 * one — ⭐ and the alternative that "works" by escaping it is the one that gets
 * mangled by a formatter.
 */
const CODE_SPAN = '`[^`\\n]+`'
const LINK = String.raw`\[[^\]]*\]\(((?:[^()\s]|\([^()\s]*\))*)\)`
const INLINE = new RegExp(
  [
    String.raw`\*\*[^*]+\*\*`,
    String.raw`__[^_]+__`,
    String.raw`\*[^*\n]+\*`,
    String.raw`_[^_\n]+_`,
    CODE_SPAN,
    LINK,
  ].join('|'),
  'g',
)

/**
 * Split one line's text into React nodes.
 *
 * ⭐ **A single pass with one regex, and every alternative is non-nesting on
 * purpose.** `**bold**` containing `*italic*` is not handled, ⭐ and claiming it was
 * would mean a claim this file cannot keep. ⭐ The pieces that do not match are
 * passed through as text, ⭐ so the worst case is a visible `*` — ⭐ which is
 * preferable to a swallowed character, ⭐ because a reader can see a stray asterisk
 * and a reader cannot see a missing emphasis.
 */
export function renderInline(text: string, keyPrefix = 'i'): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let index = 0

  for (const match of text.matchAll(INLINE)) {
    const at = match.index ?? 0
    if (at > last) out.push(text.slice(last, at))
    const token = match[0]
    const key = `${keyPrefix}-${index++}`

    if (token.startsWith('**') || token.startsWith('__')) {
      out.push(
        <strong key={key} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      out.push(
        <code
          key={key}
          // ⭐ `.num` is not applied: a code fragment is prose, not a figure, ⭐ and
          // §2.2 gives numbers the mono face. ⭐ What it does get is a faint wash so
          // an inline fragment reads as a fragment ⭐ without a border, ⭐ which at
          // this size would be heavier than the code.
          className="rounded-[2px] bg-paper-soft px-[3px] type-prose text-ink"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith('[')) {
      const split = token.indexOf('](')
      const label = token.slice(1, split)
      // ⭐ **The URL is capture group 1, not a slice of the token.** ⭐ The pattern
      // now has an inner group for the balanced parentheses, ⭐ and `match[1]` is the
      // whole target — ⭐ whereas `token.slice(split + 2, -1)` still works and is
      // wrong the moment the pattern grows another group. ⭐ Two ways to get the same
      // string, and the one that survives an edit is the one the regex declares.
      //
      // ⭐ **`linkTarget` decides; this switch only renders.** ⭐ The decision was
      // `href === null ? … : …` inline, ⭐ and a mutation that dropped the label for a
      // refused link stayed **green** ⭐ because the test asserted the label's text,
      // ⭐ which the `<span>` still produced. ⭐ Nothing here judges any more.
      const target = linkTarget(match[1] ?? '')
      out.push(
        target.kind === 'text' ? (
          // ⭐ **Printed without the link**, and that is the whole point: the text the
          // reader wrote is preserved and the dangerous part is not made clickable.
          <span key={key} className="text-ink-soft underline decoration-dotted">
            {label}
          </span>
        ) : (
          <a
            key={key}
            href={target.href}
            // ⭐ **`internal` comes from the decision, not from a second
            // `startsWith('#')` here.** ⭐ Two tests of the same fact in two places is
            // one of them wrong by the next edit, ⭐ and this one would open a new tab
            // on an in-page anchor ⭐ which in a hash-routed app navigates away from
            // the note.
            target={target.internal ? undefined : '_blank'}
            rel={target.internal ? undefined : 'noreferrer'}
            // ⭐ The link treatment is the product's, not a default: `l1` is what
            // makes the underline fade rather than snap (stage A5).
            className="text-navy no-underline hover:underline data-[motion=l1]"
          >
            {label}
          </a>
        ),
      )
    } else {
      out.push(
        <em key={key} className="italic text-ink">
          {token.slice(1, -1)}
        </em>,
      )
    }
    last = at + token.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

/**
 * ⭐ **The heading scale, and it starts one step *below* the page title on purpose.**
 *
 * A note's title is already on screen above the body as the page's own heading, ⭐ so
 * a `#` inside the body is **not** a second page title — ⭐ and the first draft mapped
 * it onto `.type-page-title`, which made the body's largest line the same size as the
 * title directly above it. ⭐ V-12 caught it: that class has a budget of **one** use,
 * and a body heading is not a page heading. ⭐
 *
 * ⭐ **The map is `claim / display / prose-semibold / meta` — four classes that already
 * exist and already have owners**, ⭐ which is why adding Markdown cost no new token.
 * A note's `#` is a claim, ⭐ exactly like a card's, ⭐ so a reader comparing the two
 * has no way to tell they came from different components.
 */
function headingClass(level: 1 | 2 | 3 | 4 | 5 | 6): string {
  switch (level) {
    case 1:
      return 'serif type-claim text-ink'
    case 2:
      return 'serif type-display text-ink'
    case 3:
      return 'type-prose font-semibold text-ink'
    default:
      return 'type-meta caps text-ink-soft'
  }
}

function BlockView({ block, index }: { block: Block; index: number }) {
  const key = `b${index}`
  switch (block.kind) {
    case 'heading': {
      const Tag = `h${Math.min(block.level, 6)}` as 'h1'
      return (
        <Tag
          key={key}
          // ⭐ **`mt-5` on everything but the first block, and never `mb`.** Rule 6 is
          // information density, ⭐ and vertical rhythm comes from one side only ⭐ —
          // setting both is how a page ends up with more air than the browser
          // default and a stranger rhythm than the guide asks for.
          className={cn('mt-5 first:mt-0', headingClass(block.level))}
        >
          {renderInline(block.text, key)}
        </Tag>
      )
    }
    case 'paragraph':
      return (
        <p key={key} className="mt-3 first:mt-0 type-prose text-ink">
          {renderInline(block.text, key)}
        </p>
      )
    case 'bullet':
      return (
        <ul key={key} className="mt-2 space-y-1">
          {block.items.map((item, at) => (
            <li
              key={`${key}-${at}`}
              // ⭐ **`pl-3` and a left rule, not a bullet glyph.** ⭐ Rule 5: a
              // category is marked with a rule, and a `•` is neither a rule nor a
              // category — ⭐ it is a glyph from a font, and it is the one thing in
              // this file that would change appearance with a platform update.
              className={cn(
                'border-l-2 border-l-rule-soft pl-3 type-prose text-ink',
                item.depth === 1 && 'ml-4 border-l-[color:var(--color-rule)] text-ink-soft',
              )}
            >
              {renderInline(item.text, `${key}-${at}`)}
            </li>
          ))}
        </ul>
      )
    case 'ordered':
      return (
        <ol key={key} className="mt-2 space-y-1">
          {block.items.map((item, at) => (
            <li
              key={`${key}-${at}`}
              className="flex gap-2 pl-3 type-prose text-ink"
            >
              {/* ⭐ **The number is `.num` and it is a number**, ⭐ which is what §2.2's
                  number row is for. ⭐ A proportional digit in a numbered list makes
                  the markers jitter as the list grows, ⭐ and the reader is scanning
                  the numbers before the text. */}
              <span className="num shrink-0 text-ink-faint">{at + 1}.</span>
              {/* ⭐ `item`, not `item.text` — an ordered list's items are strings, ⭐
                  and the bullet list's are `{text, depth}`. ⭐ The two shapes differ
                  because only the bullet list has a depth, ⭐ and the first draft
                  copied the bullet version. */}
              <span>{renderInline(item, `${key}-${at}`)}</span>
            </li>
          ))}
        </ol>
      )
    case 'quote':
      return (
        <blockquote
          key={key}
          // ⭐ **2px left rule in `--rule` and `--ink-soft` text.** A quote in this
          // product is somebody else's sentence, ⭐ and that is worth saying with a
          // rule rather than with italics ⭐ — italics in a serif face at 13px read
          // as a rendering fault, ⭐ not as a citation.
          className="mt-3 border-l-2 border-l-[color:var(--color-rule)] pl-3 type-prose text-ink-soft"
        >
          {renderInline(block.text, key)}
        </blockquote>
      )
    case 'code':
      return (
        <pre
          key={key}
          // ⭐ **A wash, no border, no shadow, and no horizontal scroll escape.** A code
          // block in a research note is a fragment of evidence; ⭐ a 1px border around
          // it would make it the loudest thing on the page, ⭐ and the guide's density
          // rule says it is not.
          className="mt-3 overflow-x-auto bg-paper-soft p-2 type-cell font-mono text-ink"
        >
          <code>{block.text}</code>
        </pre>
      )
    case 'break':
      return <hr key={key} className="mt-4 border-t border-rule" />
  }
}

export interface MarkdownProps {
  source: string
  className?: string
}

/**
 * ⭐ **`null` for a note with nothing in it, and it is a separate function.**
 *
 * The rule 8 question — 「does this note have content worth showing」 — ⭐ was
 * `if (blocks.length === 0) return null` **inside the component**, ⭐ and a mutation
 * turning that into `return <p />` stayed green ⭐ because no test in this repository
 * can read what a component returns. ⭐ So the decision is a value, ⭐ and a test
 * asserts the value. ⭐ One function, one answer, and the component is left with
 * nothing to get wrong.
 */
export function markdownBlocks(source: string): Block[] | null {
  const blocks = parseMarkdown(source)
  return blocks.length === 0 ? null : blocks
}

/**
 * A note, read.
 *
 * ⭐ **A `<div>`, not a `<p>`.** A note is blocks, ⭐ and a `<p>` containing a `<ul>`
 * is invalid HTML ⭐ that browsers repair in ways nobody chose.
 */
export function Markdown({ source, className }: MarkdownProps) {
  const blocks = markdownBlocks(source)
  if (blocks === null) return null
  return (
    <div className={cn('max-w-[68ch]', className)} data-testid="markdown">
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} index={index} />
      ))}
    </div>
  )
}
