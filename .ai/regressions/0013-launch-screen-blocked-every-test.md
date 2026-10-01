# 0013 · 开屏把整个 e2e 套件挡在外面，10 过 101 挂

- **发现日期**：2026-10-01
- **严重级别**：P0（不是测试缺陷，是**产品缺陷**）
- **状态**：已修复

## 现象

开屏（ADR-0033）第一版放在**所有路由**前面，只在「今天没看过」时显示。

第一次跑完整 e2e：

```
10 passed
101 failed
```

每一条失败都是 `expect(locator).toBeVisible() failed`，
指向「shell 不在屏幕上」。

## 根因

**两件事叠在一起，而它们的性质完全不同。**

1. **测试机制**：`localStorage` 是**按 origin 共享**的。
   Playwright 给每个测试一个新 context，但 `vite preview` 把所有 spec
   服务在同一个地址 → **先看开屏的那个 spec 写下的键，对后面所有 spec 可见**。

2. **产品行为**：`#/i/sh/600519` 从书签打开的读者**问了一个具体问题**，
   而应用用一幅全屏画回答他 ——
   **这是应用把自己的引导排在读者意图之上**。

⭐ **第 2 条才是重点。** 修好第 1 条（让 storage 隔离）而不管第 2 条，
得到的是一个「测试绿了但产品坏着」的仓库 —— 而那种仓库比红的更难发现。

## 三种修法，两种是错的

| 修法 | 后果 |
|---|---|
| 给十二个 spec 各加一次 `localStorage.clear()` | 套件绿、产品照旧坏；且下一个写 spec 的人不会知道要加，**失败会再回来** |
| **只在空 hash 上显示** | `#` / `#/` / `''` **三种拼法都表示 today**（`parseHash` 归一化），这是在**选一个拼法而不是选一个含义** |
| ✅ **深链绕过开屏** | `#/` 是**唯一**表示「我没有特定目的地」的地址 |

## 修复

`frontend/src/launchLogic.ts` 新增：

```ts
export function isHomeAddress(hash: string): boolean {
  return hash === '' || hash === '#' || hash === '#/'
}
```

`App.tsx` 在 `useState` 初始化时先问它 —— 深链直接 `true`（不进开屏）。

`frontend/e2e/fixtures.ts` 的 `routeApi()` 统一为**所有 spec**
acknowledge 开屏（一个编辑，而不是十二个），
并提供 `clearLaunchAcknowledgement()` 让 `launch.spec.ts` 单独退出。

## 回归测试

- `frontend/src/launch.test.ts`：`describe('which addresses show the launch screen')`
  三条，其中一条**把 `isHomeAddress` 与 `parseHash` 逐个哈希对拍** ——
  两个「什么算 home」的实现不该各说各话
- `frontend/e2e/launch.spec.ts`：`is in the way on a first launch` 里
  断言 `app-shell` 计数为 0 —— **证明开屏渲染在 shell 之外而不是里面**

## 变异检查（⚠️ 必填）

| 改坏哪里 | 哪个测试变红 | 结果 |
|---|---|---|
| `isHomeAddress` 加进 `#/pool` | `skips it for every address that names a destination` | ✅ **已确认变红** |
| `isHomeAddress` 去掉 `'#'` | `shows it for the three spellings of 「start here」` | ✅ **已确认变红** |
| 对拍那一条里 `parseHash` 换成硬编码 | `agrees with the route table about which hashes are today` | ✅ **已确认变红** |

## 是否可被测试固化？

✅ 可以 —— 「哪些地址进开屏」是一个纯函数，测它不需要浏览器。

## 遗留

⚠️ **`routeApi()` 现在有一个副作用**：它会 acknowledge 开屏。
这意味着**任何新写的 e2e spec 默认看不到开屏**，而想测开屏必须显式 opt out。
这是有意的（否则每个 spec 都要写一遍），但它是一个**隐式契约** ——
写在新 spec 里的第一个人不会知道它存在。

⇒ 已做：`clearLaunchAcknowledgement` 与它的注释写清了「为什么 `launch.spec.ts`
要额外调一次」，且注释说明了注册顺序（后注册的赢，实测而非推测）。
⚠️ **更好的做法是让 `routeApi` 接受一个显式选项**，而不是靠另一个函数反向抵消 ——
留作后续。
