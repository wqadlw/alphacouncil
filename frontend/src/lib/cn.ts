import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Class-name joiner, and the reason two Tailwind classes can coexist.
 *
 * `clsx` handles conditionals; `tailwind-merge` resolves the conflict that
 * `clsx` cannot — without it, `cn('p-2', 'p-4')` produces both classes and the
 * winner depends on stylesheet order rather than on the argument order, which is
 * how a component ends up with padding nobody can change from the call site.
 *
 * The three packages it needs (`clsx`, `tailwind-merge`, `class-variance-authority`)
 * are the whole of shadcn/ui's runtime. `前端资源与打磨规格` §4.1 argues for shadcn
 * because its source is copied into the repo and carries **no runtime dependency**
 * — so this is that same arrangement, minus Radix, which the style guide's
 * components do not need.
 *
 * Every variant in `components/ui` is expressed through `cva` and composed with
 * this, so a caller can always override a variant's classes by passing `className`
 * last. That is the whole contract.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
