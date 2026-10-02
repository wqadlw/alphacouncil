# 0022 · 一个静态对拍报「几乎全坏」，那是在说它自己

- **发现日期**：2026-10-02
- **严重级别**：P3（*工具的失败形状*，不是产品缺陷）
- **状态**：已修复 + 已加门禁（`S-17`，变异 M1–M5b 均已确认）

## 现象

`S-17` 的第一版跑出来：

```
backend routes   1
frontend calls   46
drift            46        <- 46 / 46
```

⚠️ **每一个调用点都是漂移。** 而前端完全正确 —— 46 个调用点全部命中真实路由。

## 为什么这值得一条回归记录

因为**它是这条规则唯一一次真正的缺陷，而且不是逻辑错**。

⭐ **一个说「几乎全坏」的静态扫描，在描述的是它自己。** 四次手搓的版本里，
每一次的错误都长得像这个 —— 26 个孤儿、0 / 36 可达、12、11 ——
**而没有一次有人问「这个失败比例可信吗」**。

## 根因：`app.routes` 上有 12 项 `path` 为空

```
app.routes has 16 entries
  Route            /openapi.json
  Route            /docs
  ...
  _IncludedRouter   []          <- 12 个，path 是空串
  APIRoute         /health
```

一个 `if not path: continue` 的遍历把那 12 项全丢掉，**后端一侧只剩 1 条路由**。

⚠️ **这就是 `regressions/0012` 的形状**：一个静默找到零条的扫描，
和一个正确找到零条的扫描看起来一模一样。

而要够到那 12 项就得用私有属性（`original_router`、
`include_context.included_router`）—— **那是 FastAPI 内部实现，升级就会动。**

## 修复：读 `openapi.json`，因为那里是 FastAPI 自己算的路径

```
openapi.json paths -> 49 (method, path) pairs
flat routes on app.routes: 5; not in the schema: 4   <- 全是 docs 端点
```

⭐ **这让「我忘了前缀」这一整类错误无法发生** —— 不是把前缀处理得更好，
而是**根本看不到前缀**（每个 `include_router`、每个 `APIRouter(prefix=...)` 都算进去了）。

⚠️ **代价**：schema 里没有的是 `/health` 那类 `include_in_schema=False` 的路由。
**这只在「孤儿是 INFO」的前提下成立** —— 看不见的路由本来就到不了界面。

## 五次迭代，六个真缺陷，全部是被「打印出来」抓到的

| # | 症状 | 真因 | 量级 |
|---|---|---|---|
| 1 | 46 / 46 全部漂移 | 后端一侧只有 1 条路由 | 全部 |
| 2 | 6 个 GET 报成 POST | `method:` 往后搜 400 字，搜进了下一个调用 | 6 |
| 3 | 路径尾部带引号 | 括号闭合时把它算进了参数 | 20 / 46 |
| 4 | 路径里留着 `${query` | `break` 之后界没有跟着走 | 4 |
| 5 | `/recent*` 多一个通配段 | 截断了 body 却没截 span 列表 | 3 |
| 6 | 15 / 46 「无法判定」 | 参数（`cardId`）被当成「不认识」 | 15 |

⚠️ **第 3、4、5 条的性质值得记下来**：它们产出的东西**仍然长得像一条路径**，
所以一个只断言「红/绿」的测试不可能发现它们。
⭐ **只有把 46 条路径全打出来看，才知道其中 20 条尾部多了一个引号。**

## ⭐ 规则会检查自己

```python
PLAUSIBILITY_FLOOR = 0.34
...
if drift and len(drift) / len(calls) > PLAUSIBILITY_FLOOR:
    result.skipped = "... That is a fact about the scanner, not about the frontend ..."
```

⚠️ **跳过的规则不是通过**（`--strict` 下退出码 1）——
所以它既**拒绝指控**，也**拒绝放行**。

⇒ **这一条会让前面四次手搓全都活下来**，成本是一个比较。

## 变异

```
M1  路径改成不存在的              exit=1  RED   drift findings=1
M2  动词改成路由没有的（DELETE）  exit=1  RED   drift findings=1
M3  模板少一段                    exit=1  RED   drift findings=1
M4  多一段                        exit=1  RED   drift findings=1
M5a 5 处坏（11%），阈值 34%       exit=1  RED   <- 这个比例可信，要报
M5b 同样 5 处，阈值降到 5%        exit=1  SKIP  <- 自检触发
--- 恢复                         exit=0  GREEN
```

⭐ **M5 是一个数对而 M5b 是一个数不对**，因为**阈值需要一个上限之下的输入和一个之上的输入**。
只测自检无法区分「机制работает」与「阈值太低」，而后者正是这个仓反复遇到的那种绿。

## ⭐ 两次「测试错了而代码是对的」

⚠️ 这一轮我写坏了自己的变异脚手架两次，两次都是同一个原因：**用了记得的字符串而不是读过的字符串**。

1. **M4** 把调用从 `/api/v1/notes/due` 改到 `/api/v1/notes/tags` 并期望红 ——
   而 **`GET /api/v1/notes/tags` 真的存在**，这个变异只是把一个调用变成重复调用。**规则绿是对的。**
2. **M5b** 的自检判据找的是 docstring 里的措辞（「that is a fact about the scanner」），
   而**跳过消息里那句首字母大写**。⇒ 自检其实**触发了**，脚手架说 MISMATCH。

⚠️ 而处理方式不是改规则：**先打印规则到底判了什么**（`5 of 46`，`[SKIP ] S-17`），
再修脚手架。⭐ **「测试错了」是最诱人的结论，所以要先证明它。**

## 交付时的状态

```
backend routes   49
frontend calls   46
drift            0       <- 前端是诚实的
unverifiable     0
orphan           3       GET /api/v1/capabilities · GET /api/v1/decision-reviews/schema/quadrants · GET /health
```

⚠️ **两个未登记的孤儿是真实发现，不是噪音**：

- **`/api/v1/capabilities`** —— 有端点、没有任何界面（台账里的 B4）
- **`GET /api/v1/decision-reviews/schema/quadrants`** —— ⭐ **服务端发布着一份
  `Quadrant` 而前端手抄了一份**，而这条端点**零调用者**。
  即 plan §2.2 里那条「`api.ts` 手写了一份而后端也有一份且无调用者」，**现在被机器看见了**。