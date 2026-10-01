# 0012 · 门禁的样式表扫描一直在迭代一个空列表

- **发现日期**：2026-09-30
- **严重级别**：P0（规则失效，且**失效形态是绿灯**）
- **状态**：已修复

## 现象

`frontend/src/styleguide.test.ts` 里有十一条规则写成

```ts
for (const file of CSS) { ... }
```

而 `CSS = FILES.filter((f) => f.endsWith('.css'))`。**往 `globals.css` 里塞一个
`@keyframes`，三十七条测试全绿。**

十一条管 CSS 的规则 —— 包括 V-01（无阴影）、V-02（圆角上限）、
V-09（时长只能是 L1/L2）—— **一次都没有执行过。**

## 根因

```ts
const SRC = new URL('.', import.meta.url).pathname.replace(/^\//, '').replace(/\/$/, '')
const SRC_DIR = SRC === '' ? '.' : SRC
```

`URL.pathname` 是**百分号编码**的，且**总以 `/` 开头**。在 Windows 上它产出：

```
/D:/AAA/A-kew/alphacouncil/frontend/src
```

剥掉前导斜杠得到 `D:/AAA/.../frontend/src` ——
**一个当作相对路径用的绝对 Windows 路径**。它不抛错，它只是不存在，
于是 `SRC_DIR` 回退到 `.`，扫描从 `frontend/` 根目录开始。

而唯一的样式表在 `src/styles/globals.css`，
`frontend/` 根目录**一个 `.css` 都没有** → `CSS` 是空数组。

⚠️ **同一次改动里还带出两个真 bug，都是新守卫第一次运行就看见的**：

1. `RELATIVE` 写的是 `file.slice(SRC_DIR.length + 1)`，而旧的 `SRC`
   恰好被 `.replace(/\/$/, '')` 剥过尾斜杠，`SRC_DIR` 没有 ——
   **`+ 1` 多吃了一个字符，于是每一条失败信息里的路径都是 `tyles/globals.css`**。
2. `CSS` 定义在 V-06 块**内部**，模块级另有一个同名声明被它遮蔽。

## 修复

- `SRC_DIR` 改用 `fileURLToPath(new URL('.', import.meta.url))`（跨平台的正解），
  并加注释说明旧写法为什么在 Windows 上静默失效
- **新增一条断言**：`CSS` 非空，且必须含 `styles/globals.css`
- `RELATIVE` 的 `slice` 改为精确切片
- `CSS` 从块内提到模块级，与它的断言放在一起

⭐ **守卫的位置是被这次事故决定的**：原来那条「扫描不要空转」的说明写在
时长检查下面，而**所有覆盖 CSS 的规则都没有守卫**。守卫写在 240 行之后，
就没人写 —— 它被提到列表构建处，与它守的东西相邻。

## 回归测试

`frontend/src/styleguide.test.ts` 的 `describe('the file list is not empty')`
里的两条：`actually found the source tree` 与
`found the stylesheet, so the rules that read it are not vacuous`

**期望值写死**：`styles/globals.css` 这个字符串是字面量，
不从前端的任何导出推导。

## 变异检查（⚠️ 必填）

| 改坏哪里 | 哪个测试变红 | 结果 |
|---|---|---|
| 把 `SRC_DIR` 改回 `'.'` | `found the stylesheet, so the rules that read it are not vacuous` | ✅ **已确认变红** |
| 把断言里的 `styles/globals.css` 改成 `index.css` | 同上 | ✅ **已确认变红** |

## 是否可被测试固化？

✅ 可以 —— 这是「一个列表必须非空」，正是测试能断言的形状。
（对照规则 5：「某段代码不该存在」进 `checks/static/`；
「某个列表空了导致规则空转」是运行时可观察的，进本目录。）

## 遗留

⚠️ 同一个文件里还有 `FILES` 与 `E2E_FILES` 两个列表，
**它们各自也有非空断言吗？** 需要单独确认 ——
本条记录的教训是「断言要放在它守的东西旁边」，而不是「加一条断言就完了」。

## 同形的一次重演

⭐ 2026-10-01 又撞了一次同一形状：**`declaredDurations()` 只扫 `transition`，
不扫 `animation`** —— 在样式表没有 `@keyframes` 的年代那是完整的，
而 ADR-0033 把 keyframes 放回来之后，`animation` 的时长**完全没有任何上限**。
已补：**L3 带（600–1600 ms）+ 两条守卫**
（`confines the L3 entrance band to the launch screen` 与
`has at least one L3 duration, so the band above is not an empty permission`）。

⇒ **教训的形状是：「一个扫描在某段时间里是完整的，而完整性不在它的断言里」。**
