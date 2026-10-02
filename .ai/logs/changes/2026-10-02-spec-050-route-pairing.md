# 2026-10-02 · spec 050：路由对拍 —— 前端调用点 × 后端路由声明

> 规格：`.ai/specs/050-route-pairing/spec.md` · 回归：`.ai/regressions/0022-…`
> 门禁：`S-17 no-route-drift`（`backend/checks/rules/no_route_drift.py`）
> 前作：spec 049 / `S-16`（枚举漂移）· 计划任务 3

## 交付

| # | 东西 | 去处 |
|---|---|---|
| 1 | **`S-17` 路由对拍门禁**，四个桶（drift / unverifiable / orphan / ok） | `backend/checks/rules/no_route_drift.py` |
| 2 | **`PLAUSIBILITY_FLOOR` —— 规则会检查自己** | 同上 |
| 3 | `checks/frontend.py::has_sources`（真正的谓词） | `backend/checks/frontend.py` |
| 4 | 18 条单测，逐条钉住扫描器的每一个已知错误 | `backend/tests/unit/test_route_drift.py` |
| 5 | 回归 `0022` · 失败模式 `F-212..F-218` · 索引第 16 轮 | 台账 |

## 交付时的实测状态

```
backend routes   49
frontend calls   46
drift            0        <- 前端是诚实的
unverifiable     0
orphan           3        GET /api/v1/capabilities
                          GET /api/v1/decision-reviews/schema/quadrants
                          GET /health（已登记理由）
```

⚠️ **两个未登记的孤儿是真实发现**：

- **`/api/v1/capabilities`** —— 有端点、无任何界面（台账 B4）
- **`GET /api/v1/decision-reviews/schema/quadrants`** —— ⭐ **服务端发布着一份 `Quadrant`
  而前端手抄了一份，而这条端点零调用者**。计划 §2.2 里那条观察**现在被机器看见了**。

## ⭐ 三条最值得带走的设计

### 一、后端一侧读 `openapi.json`，不是 `app.routes`

实测 `app.routes` 16 项里 **12 项是 `_IncludedRouter`、`path` 为空串**，
一个 `if not path: continue` 会把它们全丢掉 —— 于是第一次跑出 **46 / 46 全部漂移**，
而**前端完全正确**。

⇒ 读 FastAPI 自己算的路径，**「我忘了前缀」这一整类错误不是被处理掉，而是无法发生。**
⚠️ 代价：`include_in_schema=False` 的路由不在 schema 里 ——
**这只在「孤儿是 INFO」的前提下成立。**

### 二、四个桶，而第四个是这套设计能用的原因

`tieline`（研究时对拍的参照实现）也有 `⚠️ unverifiable`。
⭐ **「我判断不了」必须是一个规则能报告的状态**，否则它就变成一句指控。

⚠️ 而第一版把它用错了：15 / 46 落进去，全是 `cardId` / `id` / `limit` ——
**参数就是路径段**。⇒ 没有本地声明的裸名字不算「不认识」。

### 三、规则会检查自己

```python
PLAUSIBILITY_FLOOR = 0.34
```

⭐ **一个把前端大部分报成坏掉的静态扫描，不是在报漂移，是在报它自己丢了代码库的形状。**

⚠️ 而**跳过的规则不是通过**（`--strict` 下退出码 1）——
**它既拒绝指控，也拒绝放行。**

⇒ **这一条会让前两段手搓的四次全部活下来**，成本是一个比较。

## 变异

```
M1  路径改成不存在的              RED   drift findings=1
M2  动词改成路由没有的（DELETE）  RED   drift findings=1
M3  模板少一段                    RED   drift findings=1
M4  多一段                        RED   drift findings=1
M5a 5 处坏（11%），阈值 34%       RED   这个比例可信，要报
M5b 同样 5 处，阈值降到 5%        SKIP  自检触发
--- 恢复                         GREEN
```

## ⭐ 两次「脚手架错了而代码是对的」

⚠️ **这一轮最可迁移的不是规则，是这两次。**

1. **M4** 把调用改到 `/api/v1/notes/tags` 并期望红 —— **而那条路由真的存在**，
   变异只是把一个调用变成重复调用。**规则绿是对的。**
2. **M5b** 的自检判据找的是 docstring 的措辞，**而跳过消息里那句首字母大写** ——
   自检其实触发了，脚手架说 MISMATCH。

⇒ 处理方式都是**先打印规则到底判了什么，再改脚手架**。
⭐ **「测试错了」是最诱人的结论，所以要先证明它。**

## 明确没做

- **不做运行时探针**（逐端点打一遍）—— 那是契约测试的成本，且要维护一份端点清单
- **不改 `api.ts` 任何一行** —— 本规则交付时前端是**零漂移**的
- **不要求前端统一加前导斜杠** —— 规则**补**它而不是禁止；
  ⚠️ 清理 `lessons.ts` 那 5 处是另一件事，混在同一次改动里会让两者的回归无法归因
- **不把孤儿变成错误** —— `/health` 永远够不着，而那条规则活不过一周