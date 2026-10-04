# 0026 · 把六个并列三元换成 `Record`，换来了重复挂载

> ⭐⭐ **一个修好了一个静默失败面的改动，先制造了一个门禁看得见但症状在三个文件之外的缺陷。**
> 而这个缺陷的形状与它要修的那个**是同一个家族**，所以值得单独记。

## 现象

`App.tsx` 原本为六个枚举视图各写一个并列三元：

```tsx
{route.name === 'pool' ? <PoolPage /> : null}
{route.name === 'review' ? <ReviewPage /> : null}
…
```

⭐ **加一个视图而忘了加这一行，什么都不会红。** 导航行、`⌘K` 条目、`document.title`
全部正常——**因为它们都从 `ROUTES` 派生**——⭐ 而 `#/universe` 画一个空 frame。
`routing.ts:12` 那句「adding a view is one entry」就是这个静默失败面。

⇒ 按 `F-211` / `regressions/0005` 的结论，改成穷举结构：

```tsx
const VIEWS: Record<RouteName, ReactNode> = {
  pool: <PoolPage />,
  …
}
// 渲染
{route.name === 'instrument' ? <InstrumentPage … /> : VIEWS[route.name]}
```

## 根因

⭐ **穷举性与元素新鲜度是两件事，而它们互相牵制。**

- ⭐ **三元 `{c ? <X /> : null}` 每次 render 产生一个全新的元素对象。** React 的
  reconciler 靠这个在类型变化时卸载旧子树。
- ⭐ **模块级 `Record<ViewName, ReactNode>` 里的元素是常量对象，永远复用同一个。**
  ⇒ 类型变了，但那个对象的身份没变，**旧子树从未被拆掉，新的一棵挂在它旁边。**

⇒ 于是复习页挂了两份，而失败是：

```
Error: strict mode violation: getByTestId('card-schedule-out') resolved to 2 elements
```

⭐ **`tsc` 通过、`vitest` 通过、E2E 失败**——而失败点在 `CardSection.tsx`，
**离原因（`App.tsx` 的一个类型标注）三个文件。**

## 修复

```tsx
const VIEWS: Record<ViewName, () => ReactNode> = {
  pool: () => <PoolPage />,
  …
}
// 渲染：调用它
{route.name === 'instrument' ? <InstrumentPage … /> : VIEWS[route.name]()}
```

⭐ **thunk 而不是元素**：每次 render 得到一个新元素对象，**穷举性由 `Record` 的键提供，
新鲜度由箭头函数提供** ⭐ 而两者的提供者不同，所以签名写成 `() => ReactNode` 而不是
`ReactNode` ⭐ **让类型自己说出这件事。**

⚠️ `ViewName` 也从 `RouteName` 改成了 `Exclude<Route['name'], 'instrument'>` ⭐
**因为 `unknown` 是 `Route` 的成员而不是 `RouteName` 的** ⭐ 而这一条是 `tsc` 报的
（`src/App.tsx(45,3): error TS2353: … 'unknown' does not exist in type 'Record<RouteName, ReactNode>'`）
⭐ **第一版把 `unknown` 放进了 `VIEWS`，而类型立刻说了不行。**

## 回归测试

`frontend/e2e/universe.spec.ts` 的 `it offers no way to sort, rank or shortlist` ⭐
断言 `[data-testid^="sort-"]` **一个都没有**。

⭐⭐ **而这一条不只是「页面正常」**：它是 `constitution.md:802-803` 的边界在 UI 上
**唯一**的技术杠杆（`DataTable` 内建排序，不给 `sortValue` 的列不出现排序控件），
⭐ 后端与 vitest 都看不见一个排序控件是否存在。

## 变异检查（⚠️ 必填）

| 改坏哪里 | 哪个测试变红 | 结果 |
|---|---|---|
| 给 `UniversePage` 的代码列加上 `sortValue` | `it offers no way to sort, rank or shortlist` | ✅ **已确认变红** |
| 去掉新鲜度那一行的 `data-testid` | `it says how old the roster is…` + 另一条 | ✅ **已确认变红**（2 红） |
| 还原 | 6 条全绿 | ✅ 按 SHA-256 校验还原 |

⚠️⭐ **六条测试第一次跑就全绿**，而 `.ai/logs/changes/2026-09-26-storage-and-domain.md:76-85`
写着「一个从未失败过的检查，很可能从未运行过」⇒ 所以变异不是形式，是**唯一**能说明
「它们在守东西」的证据。

⭐ 而**第一条变异是刻意挑的**：删一行也会红，⭐ **而给一列加上 `sortValue` 才是那条
边界的真检验** ⭐ —— 因为带 ▲▼ 的表格**每一行仍然渲染正确、这一页其他五条断言仍然全过**，
⭐ **它的失败方式是不可见的。**

## 是否可被测试固化？

⭐⭐ **一半可以，一半不能，而不能的那一半正是这次要记的原因。**

- ✅ **「加了视图而忘了页面」从零红变成编译错** ⭐ `Record<ViewName, () => ReactNode>`
  使 `RouteName` 的新成员没有对应条目时 `tsc` 失败。**这是可固化的。**
- ⚠️ **「重复挂载」本身没有测试** ⭐ 它是被 `palette`/`nav` 那两条既有 e2e 撞出来的，
  ⭐ 而**它们撞出来的方式是「strict mode violation」** ⭐ —— 靠 Playwright 的
  strict 模式 ⭐ **不是靠任何一条针对这个缺陷的断言。**
  ⇒ ⭐ **一个「只用三元就会静默失败」的形状，被换成「用 Record 就会重复挂载」的形状，
  而第二个缺陷没有任何测试守着。** ⚠️ **它是 `CardSection` 的测试在守着的，而且是顺带的。**

⇒ ⚠️ **残留**：`instrument` 页面上那个 `key` 的理由（切换标的要重挂载）仍然只写在
**注释**里 ⭐ **而它现在与 `VIEWS` 的新鲜度是同一个机制的两种用法** ⭐ **一次注释里的
理由被一次重构改掉了，而没有任何门禁发现。**

## 遗留

⭐⭐ **`Record<RouteName, ReactElement>` 这个写法应当被本仓禁止，除非写成一个
`() => ReactNode` 的映射。** ⭐ 而**它不是一条 lint 能表达的** ⭐ —— 一个元素类型的映射
是完全合法的 TypeScript ⭐ **所以这条只能靠一条测试或一条 review 纪律，而 `.ai/README.md`
的纪律 7（写脚本之前先读那一段）恰好就是为这类事存在的：⭐ `App.tsx` 里已经有一次教训
（`regressions/0005`），而这个文件里还留着那个形状。**