# 0016 · 画与署名落在首屏之外且**无法滚动**，而 Playwright 的可见性是几何的

- **发现日期**：2026-10-01
- **严重级别**：P0（**产品缺陷**：一整类窗口尺寸下读者拿不到画）
- **状态**：已修复 + 已加门禁（变异已确认）

## 现象

开屏重做后在 900×800 量布局：

```
document.scrollHeight  1026
document.clientHeight   800
.startup-copy   top  48   height 226
.startup-frame  top 318   height 630      ← 630px 的框，下半截在首屏外
.startup-credit top 962                   ← 超出底边 162px
```

而 shell 给 `body` 设了 `overflow: hidden`。

⇒ **没有任何东西能滚动。** 一个窗口窄、屏幕不高的读者看到的是日期行、那句话、
「进入今天」—— **没有画，也没有署名**，而且无法到达。

## 根因

```css
.startup {
  min-height: 100%;   /* ← 一个「地板」 */
}
```

`min-height` 设的是**地板**：块可以比视口更高，于是它的溢出被一个**被禁止滚动**的
祖先裁掉了（`body { overflow: hidden }`，是 shell 为了三个视图各管各的滚动区而设的，
对开屏没有例外）。

对比 `.pane-scroll` —— 它是**自己**的滚动容器。开屏当时没有。

## ⭐ 为什么所有其他测试都是绿的

**Playwright 的 `toBeVisible()` 是几何的**：元素在渲染树里、有非零盒子、没被
`visibility` 关掉 —— 就通过。**它在屏幕内吗？它问不到。**

所以：

| 测试 | 结果 |
|---|---|
| `is in the way on a first launch` | ✅ 绿 |
| `shows a real painting, and the one the day calls for` | ✅ 绿 |
| **`hangs the painting whole, at its own proportions`** | ✅ **绿 —— 量的是一幅没人看得见的画的宽高比** |
| `credits the painting, though CC0 does not require it` | ✅ 绿 |
| 静态检查 11 项 | ✅ 全绿 |
| 前端 216 条 | ✅ 全绿 |

**这个缺陷穿过了本仓除一条以外的全部机制。** 而那条不是靠聪明发现的 —— 是靠
**在一个 900×800 的窗口里手动量**发现的。

⚠️ 这一条是本仓已记录的最重要形态（见 `regressions/0012-css-scan-iterated-nothing.md`、
`0013`）：**门禁全绿不等于产品是对的**。但这次多了一层 ——
**门禁全绿的同时，我引入了缺陷**。

## 修复

开屏必须是自己滚动的那一层：

```css
.startup {
  height: 100%;
  overflow-y: auto;
}
```

实测 900×800：`scrollTop` 0 → 226，署名完整进入视口（736..752，容器 800）。

⚠️ 用 `overflow-y` 而不是 `overflow`：横向滚动条会**掩盖一个布局缺陷**，而栅格轨道
已经是 `minmax(0, …)`，横向本来就该被压住而不是滚出去。

⚠️ 用 `100%` 而不是 `100vh`：`100vh` 在被缩放过的桌面上是**含 webview 并不存在的
窗口装饰**的高度 —— 与 `.pane-scroll` 存在的原因是同一条。

## 回归测试

`frontend/e2e/launch.spec.ts` · `keeps everything reachable at a size where the columns stack`

⭐ **两条断言，第二条才是重点：**

1. `overflow-y` 是 `auto`，且 `scrollHeight > clientHeight`
   （**第二条防止这条测试在「本来就放得下」的尺寸上空转**）
2. **滚到底之后，最后一行必须完整落在容器盒子里** —— `inside` 是相对**容器**算的，
   不是相对视口，所以任何中间环节的裁剪都会让它失败

⚠️ **尺寸选 900×800，不是更小的整数**：900 是**仍然堆叠的最大宽度**（双栏从 1180
起），800 是笔记本的可用高度。缺陷就在这个角上 —— 414×896 的手机上放得下，
1440×900 是两个方向各一栏。

## 变异检查（⚠️ 必填）

| 改坏哪里 | 哪个测试变红 | 结果 |
|---|---|---|
| `height: 100%; overflow-y: auto` 换回 `min-height: 100%` | `keeps everything reachable at a size where the columns stack` | ✅ **已确认变红**（exit 1，失败在 `overflowY` 断言） |

## 是否可被测试固化？

✅ 可以 —— 但**只能测「能到达」，不能测「看得见」**。这正是缺陷能藏住的那道缝。

⇒ 已做：测试里显式写了「Playwright 的可见性是几何的，所以其余断言当时全绿，包括
那条量画宽高比的」—— 记录这句话，是为了让下一个写 e2e 的人知道
`toBeVisible()` 不等于「用户在屏幕上」。

## 遗留

⚠️ **这个缺陷是我在重做开屏时引入的。** 第一版没有它，因为第一版的画框更小
（`62vh`），在 900×800 下刚好放得下。⇒ 教训已写进 `failure-modes.md`：**改了尺寸
上限就要重测那个尺寸之外的地方**，而「布局测试跑在几个视口上」这件事本仓仍然没有
硬性规定（E2E 全部跑在 `playwright.config.ts` 的默认视口）。

⇒ 建议（未做）：在 `playwright.config.ts` 里为 `launch.spec.ts` 之外再定一个
窄视口项目，或者在 `dev.py check` 里加一步「在 900×800 下渲染全部页面并断言无
横向滚动」。这条已登记在 `.ai/logs/changes/2026-10-01-plan.md`。