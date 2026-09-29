# spec 034 —— K线：把已经拿得到的数据露出来，再给它一块画布

> 状态：**已实现** · 2026-09-29
> 相关：spec 033（推送通道）· `references/research/2026-09-29-tsp-capability-matrix.md`
> 来源：主人明确要求「必须有市场的数据，借鉴这个项目怎么获取数据、怎么展示数据」

---

## 一、⭐ 数据早就在，只是 HTTP 层没有门

动手前先查了一遍，结论是**这不是一个取数问题，是一个暴露问题**：

| 层 | 状态 |
|---|---|
| `MarketDataProvider.get_daily()` | ✅ 三个源都实现了（东财/新浪/腾讯） |
| `MarketDataRouter.get_daily()` | ✅ 有缓存键、有 `allow_cached_answer`、有降级 |
| 领域测试 | ✅ **101 项 · 覆盖率 90.1%** |
| ⭐ **`GET /api/v1/instruments/{market}/{code}/daily`** | ⭐ **不存在** |
| ⭐ 前端图表依赖 | ⭐ **0 个** |

⭐ 所以「现在是什么样」这一页给出的是 `1235.68 −0.66%` 这样一行**文字**，
不是因为没有数据，而是因为**历史日线根本没有出口，而前端一个图表库都没有**。

对照 TSP：15 个图表组件（`EChartsCandlestick` 48KB · `StockDailyKChart` 11KB ·
`EChartsIntraday` 24KB · `LimitUpLadder` 79KB……）。⭐ **这是它「怎么展示数据」那一半，
也是本项目落后最多的那一半。**

---

## 二、端点：形状照抄 `/quote`，理由也照抄

```
GET /api/v1/instruments/{market}/{code}/daily?start=&end=
    → DataResult[list[Quote]]
```

⭐ **直接返回 `DataResult`，不做任何映射**，和 `/quote` 完全一致。`/quote` 的 docstring
已经把理由写好了，这里不重复发明：

> 把 `no_data` 映射成 `404` 看起来更整洁，却会毁掉 UI 需要的那个区别：
> 「这个代码不是数据源报价的东西」和「我们知道的所有源都拒绝了我们」，
> 是两句不同的话，而且只有一句值得重试。

**四态必须原样传出去**（`ok` / `stale` / `no_data` / `error`）。⭐ 尤其 `stale`：
缓存的价格当今天的价格端出去是一个安静的谎，`stale` 就是客户端能说「这个数是旧的」的办法。

---

## 三、⭐ 页面不许承诺它填不满的图表

`MarketDataRouter.usable_datasets()` 的 docstring 写着：

> 这是 UI 在渲染面板前要问的。**页面不得承诺它填不满的图表**（宪法：诚实的空状态）。

⭐ 这条已经是本项目的既有约定，所以图表的接法由它决定，而不是由「先画个骨架再说」决定：

1. 先问 `usable_datasets` 是否含 `DAILY`
2. 含 → 请求并画
3. 不含 → **不画**，写明「当前没有任何源能提供日线」

⚠️ **一个安静的空图表比没有图表更坏**：它看起来像「这只票没数据」，
而真实原因可能是「今天三个源都在熔断」—— ⭐ **两句话指向完全不同的下一步。**

---

## 四、图表库：`lightweight-charts`

| | `lightweight-charts` | `echarts` |
|---|---|---|
| 许可 | Apache-2.0（宽松，门禁判 `ok`） | Apache-2.0 |
| 体积 | ⭐ 只有蜡烛图这一个场景的几 KB | 全功能图表库，几十 KB+ |
| 适配 | ⭐ TradingView 的 K 线交互（缩放/拖拽/十字线） | 通用 |

⭐ 选它是因为**这是一个蜡烛图的问题**。TSP 两个都用（`echarts` 给通用图表、
`lightweight-charts` 给 K 线），而 AlphaCouncil 现在一个图表都没有 ——
⭐ 先引入**只有一个用途**的依赖，比引入一个什么都能画的库更便宜，也更容易删。

⚠️ 我先前口述它是 MIT，**说错了**：实测 `package.json` 的 `license` 是 **Apache-2.0**。
两者都宽松，门禁都判 `ok`，但**说错许可证是要改的**。

---

## 五、验收

1. `GET .../daily` 返回 `DataResult[list[Quote]]`，四态原样
2. `start` / `end` 可选；不传则取默认窗口
3. ⭐ **`usable_datasets` 不含 `DAILY` 时前端不画图，并说明原因**
4. CJK/日期正确渲染；`amount` 为 `None` 时不编造数字（`Quote.amount` 的 docstring
   明确说了「该源不提供时应渲染成一句话，而不是一个数」）
5. 体积与许可进门禁
6. E2E：图表渲染 / 空状态两条路都测

## 六、明确不做

- **不做**分钟 K、五档盘口 —— 那是新的数据集契约（要扩 `Dataset` 枚举与能力矩阵），
  ⭐ 那是**下一件**，不是这一件的顺手延伸
- **不做**指标列（MA/MACD/RSI）—— 数据在，逻辑要单独立口径
- **不做**概念/行业成分 —— 同上，需要新的数据集
