# 0019 · fixture 的第二次调用悄悄扔掉了第一次，而失败信息说的是产品

- **发现日期**：2026-10-01
- **严重级别**：P1（**测试基础设施缺陷**，它让四条失败读起来像产品坏了）
- **状态**：已修复（`routeApi` 改为累加）

## 现象

spec 047 的 e2e 需要在一个 `beforeEach` 已经铺好整套 stub 的测试里，
**只替换一个端点**（把 resolver 换成「歧义」那一种）。写法是再调一次 `routeApi`：

```ts
await routeApi(page, { 'GET /api/v1/instruments/resolve': ambiguousTicker() })
```

四条失败：

```
A2  「已记录（事件 #99）」 element(s) not found
A6  expected "is not a six-digit code"
       received 「请求被拒绝（HTTP 400）」
     expected "'zzz' is not a six-digit code"
       received 「请求被拒绝（HTTP 404）」
pool.spec.ts  同款失败
```

## 根因

**Playwright 的路由处理器是「后注册的赢」。** `routeApi` 每调一次就
`page.route('**/api/v1/**', …)` 一次，**第二次调用把第一次整套替换掉了** ——
于是 `beforeEach` 铺的 watchlist / quotes / POST 全部失效。

⚠️ **400 与 404 都是 `routeApi` 自己的诊断：**

- **400** = 「你给了一个裸的状态码」
- **404** = `e2e fixture missing for /api/v1/instruments/resolve`

**fixture 的内部诊断，以产品的句子形状出现在失败输出里。** 这是最坏的位置 ——
读失败的人（我当时是我自己）会去看产品，而不是看 fixture。

## ⭐ 这条机制本仓已经量过两次，在另外两个地方

| 位置 | 规则 | 我踩过吗 |
|---|---|---|
| `addInitScript`（`launch.spec.ts` 的注释） | 后注册的赢 | ✅ 踩过，代价 101 条测试失败 |
| `page.route` | 后注册的赢 | ✅ **这次** |
| `mergeHosts` / `addInitScript` 的注册顺序 | 同上 | — |

⚠️ **同一个规则、同一个方向，在第三个地方又踩了一次 —— 因为三处的注释互相看不见。**
这是本条记录最值得留下的部分：**「已知规则」不等于「会在所有地方想起规则」。**

## 修复

`routeApi` 改为**每页一份、累加**，且**路由只注册一次**：

```ts
const HANDLERS = new WeakMap<Page, Record<string, Body | number>>()
const ROUTED = new WeakSet<Page>()
```

于是测试可以**只覆盖它关心的那一个端点**，不必重述整个世界，而 `beforeEach`
也不再是「第二次调用就能扔掉的东西」。

顺带补了 `{ status, body }` 这种**带真信封的拒绝** ——
因为一个 stub 最容易被写成「200 装着一个错误」，那和真服务端不是一回事。

## 回归测试

**⚠️ 这里没有为 fixture 本身写测试，而这是一个已知的欠账。**
`fixtures.ts` 没有自己的测试文件。现在的保护是间接的：任何用到它的 spec 失败时
会看到 404 的诊断。

⇒ 欠账：`fixtures.ts` 应该有一条「两次调用是并集不是替换」的测试。
**这一条不在本次提交里做，写在这里是为了不被忘记。**

## 变异检查

⚠️ **未做。** 理由：修复本身没有对应的产品断言可挂 —— fixture 的正确性只能由
「用它的测试是否测到了它们声称在测的东西」来体现，而本次的 `A1`–`A7` 就是那份证据。

**而这个理由本身就是欠账的一部分**：按 `regressions/README.md` §五，
「未做变异检查」必须写明原因，这里写的是原因，**不是理由充分**。

## 是否可被测试固化？

✅ 可以，而且很容易（一条断言：两次 `routeApi` 之后两个键都能命中）。
⇒ 上面那条欠账就是这个断言，本轮没做。

## 顺带修的：我的 A6 用例本身就是错的

第一版 A6 传的是**裸 `400`**，于是断言收到「请求被拒绝（HTTP 400）」。

⚠️ **那是 `request()` 的正确行为** —— 空的 400 没有 `message` 可显示。
**是我的 fixture 在冒充服务端，不是产品错了。**

⇒ 已改为 `{ status: 400, body: UNUSABLE_TICKER }`（真信封），
并断言**服务端那句英文原样透传**（spec 047 §3.4 决定不翻译它）。

⚠️ 顺带说明为什么那条 spec 坚持不翻译：翻译它就要在前端维护一张错误码→中文的表，
**而那张表会和 `api/errors.py` 漂移** —— `S-05` 保证的是文档↔枚举↔代码那三方，
**前端那一份不在这个保证里**。这条推理写进了 `F-198`。