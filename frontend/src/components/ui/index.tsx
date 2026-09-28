/**
 * The base components. Every variant is `cva`; every override goes through `cn`,
 * so a caller passing `className` always wins.
 *
 * The specs these encode are in `docs/FRONTEND_STYLE_GUIDE.md` §4 and §8.1, and
 * three of them are the reason these are hand-written rather than pulled from a
 * component library:
 *
 * - **radius caps at 4px** (§4). A stock library's `rounded-lg` is 8px, and
 *   §4.4's judgement is that past 4px "一圆就变成 SaaS 后台，不是研报".
 * - **no shadows, ever** (§3.2). Handled globally in `globals.css`; nothing here
 *   emits one.
 * - **no capsules** (§4). There is deliberately no `pill` variant, because a
 *   rounded-full badge row is the exact thing §4.4 forbids and having the option
 *   available is how it comes back.
 */

import { cva, type VariantProps } from 'class-variance-authority'
import {
  forwardRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react'
import { cn } from '../../lib/cn'

/* ── Button ──────────────────────────────────────────────────────────────── */

const buttonVariants = cva(
  // `data-motion="l1"` is the only transition in the system: a hover/focus
  // change. There is no press-scale or slide, because there is no press animation.
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[2px] border text-[13px] leading-none disabled:pointer-events-none disabled:text-ink-faint data-[motion=l1]',
  {
    variants: {
      variant: {
        /** The default action. Navy because it is the one thing to press. */
        primary: 'border-navy bg-navy text-paper hover:bg-[#16304f]',
        /** Everything else. A hairline and the ink colour. */
        default: 'border-rule bg-surface text-ink hover:border-navy hover:text-navy',
        /** Inside a list or a table row: no chrome until you touch it. */
        ghost: 'border-transparent bg-transparent text-ink-soft hover:bg-paper-soft hover:text-ink',
        /** A destructive or irreversible action. */
        danger: 'border-[color:var(--color-up)] bg-transparent text-[color:var(--color-up)] hover:bg-[color:var(--color-up)] hover:text-paper',
      },
      size: {
        sm: 'h-7 px-2 text-[12px]',
        md: 'h-8 px-3',
        lg: 'h-9 px-4',
        icon: 'h-7 w-7 p-0',
      },
    },
    defaultVariants: { variant: 'default', size: 'md' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      data-motion="l1"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
)
Button.displayName = 'Button'

/* ── Input ───────────────────────────────────────────────────────────────── */

const inputVariants = cva(
  'w-full rounded-[2px] border border-rule bg-surface px-2 py-1.5 text-[13px] text-ink outline-none placeholder:text-ink-faint focus:border-navy data-[motion=l1]',
  { variants: { size: { sm: 'h-7', md: 'h-8' } }, defaultVariants: { size: 'md' } },
)

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'>,
    VariantProps<typeof inputVariants> {}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, size, ...props }, ref) => (
    <input ref={ref} data-motion="l1" className={cn(inputVariants({ size }), className)} {...props} />
  ),
)
Input.displayName = 'Input'

/* ── Textarea ────────────────────────────────────────────────────────────── */

/**
 * The same specs as `Input`, without the fixed height.
 *
 * Resize is left on. That is a deviation from the usual "lock the box" instinct
 * and it is deliberate: this box holds **the reader's own sentence about why they
 * care about a company**, and a two-line box that cannot be made taller invites
 * the reader to compress the most important thing on the page to fit the widget.
 */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    data-motion="l1"
    className={cn(
      'w-full resize-y rounded-[2px] border border-rule bg-surface px-2 py-1.5 text-[13px] leading-relaxed text-ink outline-none placeholder:text-ink-faint focus:border-navy',
      className,
    )}
    {...props}
  />
))
Textarea.displayName = 'Textarea'

/* ── Badge ───────────────────────────────────────────────────────────────── */

const badgeVariants = cva(
  // ⛔ No `rounded-full` variant exists. §4.4: a row of coloured pills reads as a
  // generic BI tool, and this product is not one.
  'inline-flex items-center gap-1 rounded-[2px] border px-1.5 py-px text-[11px] leading-[16px]',
  {
    variants: {
      tone: {
        neutral: 'border-rule text-ink-faint',
        /** Selection marks. Brass, per the command palette's "选中项左侧 2px 金线". */
        active: 'border-brass text-brass',
        /** A-share up. */
        up: 'border-[color:var(--color-up)] text-[color:var(--color-up)]',
        /** A-share down. */
        down: 'border-[color:var(--color-down)] text-[color:var(--color-down)]',
        warn: 'border-[color:var(--color-warn)] text-[color:var(--color-warn)]',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />
}

/* ── Card ────────────────────────────────────────────────────────────────── */

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  // Hairline, never a shadow (§3.2). 4px is the ceiling (§4).
  return (
    <div
      className={cn('rounded-[4px] border border-rule bg-surface', className)}
      {...props}
    />
  )
}

/* ── Rule ────────────────────────────────────────────────────────────────── */

/** A hairline. The most-used element in the product, which is the point. */
export function Rule({
  className,
  vertical,
  strong,
  ...props
}: HTMLAttributes<HTMLDivElement> & { vertical?: boolean; strong?: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        strong ? 'bg-rule' : 'bg-[color:var(--color-rule-soft)]',
        vertical ? 'w-px self-stretch' : 'h-px w-full',
        className,
      )}
      {...props}
    />
  )
}

/* ── Skeleton ────────────────────────────────────────────────────────────── */

const skeletonVariants = cva('rounded-[2px] bg-paper-soft', {
  variants: { size: { line: 'h-3', block: 'h-16', title: 'h-5' } },
  defaultVariants: { size: 'line' },
})

/**
 * A loading placeholder.
 *
 * ⚠️ **Static grey blocks, no shimmer** (§7.3). A shimmer sweep is decorative
 * motion, which rule 7 forbids, and it also implies progress that does not
 * exist — the page has no idea how much is coming.
 *
 * `width` is a prop rather than a class so callers stop hardcoding `w-40`; the
 * height variants exist so a skeleton's shape matches the content that replaces
 * it, which is what stops the layout jumping when the data lands (§7.3).
 */
export function Skeleton({
  className,
  size,
  width,
  ...props
}: HTMLAttributes<HTMLDivElement> &
  VariantProps<typeof skeletonVariants> & { width?: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="读取中"
      style={width ? { width } : undefined}
      className={cn(skeletonVariants({ size }), className)}
      {...props}
    />
  )
}

/* ── EmptyState ──────────────────────────────────────────────────────────── */

/**
 * Rule 8: an empty state is **a statement of fact plus one action**.
 *
 * No illustration, no emoji, no "还没有…" placeholder phrasing. The examples in
 * the spec are the standard: 「没有卡片。有出处的判断才值得记。」 — it says what
 * is true, and it says what to do, in one sentence each.
 */
export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: { href: string; label: string } | ReactNode
}) {
  return (
    <div className="px-4 py-10" data-testid="empty-state">
      <p className="text-[13px] text-ink">{title}</p>
      <p className="mt-1 text-[13px] text-ink-soft">{body}</p>
      {typeof action === 'object' && action !== null && 'href' in action ? (
        <p className="mt-3">
          <a href={action.href} className="text-[13px] text-navy hover:underline">
            {action.label}
          </a>
        </p>
      ) : (
        action
      )}
    </div>
  )
}

/* ── ErrorNote ───────────────────────────────────────────────────────────── */

/**
 * A failure, stated as a sentence the reader can act on.
 *
 * ⭐ **Rendered above the content, never instead of it.** `RequestRunner` keeps
 * the last good `data` on a failed refetch, so a page can show this line above a
 * table that is still true. That is the whole point of the four-state model
 * (constitution 4.6): "we could not reach the source" is its own state, not a
 * synonym for "there is no data".
 *
 * Tone is `up` (red) because a failed read is the one thing on this product that
 * genuinely is bad news — 规则 7, colour carries meaning.
 */
export function ErrorNote({ message, className }: { message: string; className?: string }) {
  return (
    <div
      className={cn('mark border-l-2 border-l-[color:var(--color-up)] py-1', className)}
      data-testid="error-note"
    >
      <p className="text-[13px] text-[color:var(--color-up)]">{message}</p>
    </div>
  )
}
