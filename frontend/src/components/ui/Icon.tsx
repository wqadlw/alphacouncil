import { type ComponentProps } from 'react'
import {
  BookOpen,
  History,
  Layers,
  ListChecks,
  RotateCcw,
  Target,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '../../lib/cn'

/**

 * The one way an icon enters this product.
 *
 * Authority: `docs/FRONTEND_STYLE_GUIDE.md` §5 — 唯一主库 Lucide, `stroke-width`
 * 三档, 只用 `currentColor`, ⛔ 禁止 emoji 作功能图标.
 *
 * ## Why there is a registry instead of importing at each call site
 *
 * ⭐ **`lucide-react` has 4236 icons and the barrel has no `exports` map**, so
 * `import { Camera } from 'lucide-react'` pulls from a 4236-entry module that the
 * bundler must analyse to find the one name used. ⭐ A registry makes that analysis
 * trivial: **one module, N statically-named imports, and the N is visible in this
 * file.** It is also the difference between a grep that can answer 「which icons
 * does this product use?」 and one that cannot, which is what `V-11` needs in order
 * to assert that the registry has no dead entries — a registry nobody checks is a
 * slowly growing icon museum.
 *
 * ⭐ **Tree-shaking is why the barrel is still correct here.** `package.json` says
 * `sideEffects: false`, and the ecosystem advice for Lucide is to import each icon
 * from `lucide-react/icons/<kebab>` instead. ⭐ That advice exists to dodge
 * bundlers that cannot shake a barrel. ⭐ Here it would be *worse*: eleven separate
 * deep imports is eleven modules for one effect, and the community alias for it
 * (`resolve.alias` pointing into `node_modules/lucide-react/dist/esm/icons`) reaches
 * into package internals with no `exports` map to protect the path. **A single
 * barrel with named imports, in one file, is the shape a tree-shaker handles best.**
 *
 * ## Why icons carry no colour
 *
 * ⭐ 规则 7: 颜色只承载意义 (涨跌 / 警示 / 类型), 装饰一律中性. So `color` is never
 * set here — every icon inherits `currentColor` from its context, and an icon that
 * needs to mean something takes a `text-*` class from the caller like any other
 * text. ⭐ That is why there is no `tone` prop: a `tone` prop would put the choice
 * in the component library, and the choice belongs to the sentence it sits in.
 *
 * ## The three stroke widths, and why they are not a size in px
 *
 * §5 gives them by *rendered size*, not by px: `icon-sm` 1.5 (<14px) / `icon-md`
 * 1.25 (16–20px, default) / `icon-lg` 1 (≥24px). ⭐ So `size` here is the semantic
 * tier and the pixel size is **derived** from it, because a caller that could pass
 * `size={13}` would be able to ask for a stroke weight §5 does not define. ⭐ One
 * tier, one number, no way to be subtly wrong.
 */

/**
 * The registry. ⭐ **Semantic names, never Lucide's** — the product's vocabulary is
 * 「今天」/「复盘」/「知识库」 and Lucide's is `ListChecks` / `History` / `BookOpen`.
 * A call site reading `<Icon name="retrospective" />` states what it means; one
 * reading `<ListChecks size={16} />` states which glyph was to hand. ⭐ The second
 * is how a design system rots: the day someone prefers a different glyph, every
 * call site has to be found by hand.
 *
 * ⚠️ **This list is the whole audit surface, and `V-11` holds it to account.** Every
 * entry here must be referenced at least once in `src`. Adding an icon 「for later」
 * is therefore not possible without the gate going red, which is the intent.
 */
const REGISTRY = {
  // The five views. These are the only entries today, and that is the point:
  // V-11 makes every registered icon a used icon, so this table says what the
  // product draws rather than what lucide ships (4236 of them).
  today: ListChecks,
  pool: Target,
  review: RotateCcw,
  retrospective: History,
  vault: BookOpen,
  universe: Layers,
} as const satisfies Record<string, LucideIcon>

/**
 * The names a caller may use. ⭐ Derived from the registry rather than written out,
 * so adding an icon cannot leave a stale copy of this list — the same reasoning
 * `routing.ts` records for deriving its own union from `ROUTES`.
 */
export type IconName = keyof typeof REGISTRY

/** §5's three tiers, named for what §5 names them. */
export type IconSize = 'sm' | 'md' | 'lg'

/**
 * ⭐ The px behind each tier, and the reason §5's ranges become exact numbers here.
 *
 * §5 says the stroke width applies 「<14px」/「16–20px」/「≥24px」, which leaves gaps —
 * 14, 15, 21..23 — and an icon at 15px would have no weight assigned to it. ⭐ The
 * tiers land on 14 / 18 / 24 and the ranges are read as **「up to」/「at least」**
 * around them: `sm` covers everything under 16, `md` the 16–20 band, `lg` 24 and up.
 * ⭐ 24 rather than 26 because §4 caps radius and §2.2 caps type at 30: the largest
 * icon in this product should not be able to compete with a page title.
 */
const SIZE_PX: Record<IconSize, number> = { sm: 14, md: 18, lg: 24 }

/** §5's three stroke widths, verbatim. */
const STROKE_WIDTH: Record<IconSize, number> = { sm: 1.5, md: 1.25, lg: 1 }

export interface IconProps extends Omit<ComponentProps<LucideIcon>, 'size' | 'strokeWidth'> {
  name: IconName
  /** Which of §5's three tiers. Defaults to `md`. */
  size?: IconSize
}

/**
 * One icon, one home.
 *
 * ⭐ **`aria-hidden` by default, and the override is the point.** An icon next to
 * visible text is decoration, and announcing it makes a screen reader say 「链接」
 * twice. ⭐ But an icon that *is* the content — the ⌘K hint glyph, a status mark in a
 * queue row with no words beside it — has to be announced, so `aria-label` turns
 * `aria-hidden` off. ⭐ The rule is therefore: **label it if there is no text next
 * to it**, which is a judgement about the call site and not something this
 * component can infer.
 */
export function Icon({ name, size = 'md', className, ...rest }: IconProps) {
  const Glyph = REGISTRY[name]
  const labelled = typeof rest['aria-label'] === 'string'
  return (
    <Glyph
      width={SIZE_PX[size]}
      height={SIZE_PX[size]}
      strokeWidth={STROKE_WIDTH[size]}
      // ⭐ No `className` merging surprises: `cn` so a caller's width/height wins,
      // and `shrink-0` because these sit inside `flex items-baseline` rows all over
      // the product and an icon that shrinks is an icon that has become a smudge.
      className={cn('shrink-0', className)}
      aria-hidden={labelled ? undefined : true}
      focusable="false"
      {...rest}
    />
  )
}

/**
 * ⭐ Exported so `V-11` can read the registry's names without re-deriving them.
 * Exporting the **keys** rather than the table is deliberate: a caller that can
 * reach `REGISTRY` can also add to it at runtime, which would make the registry
 * no longer the single audited list.
 */
export const ICON_NAMES = Object.keys(REGISTRY) as IconName[]
