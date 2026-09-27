# Plan · Spec 008 能力矩阵

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 技术方案

### `providers/router.py`（模型 + 方法都在这，矩阵描述的是路由器自己的状态）

```python
class CapabilityState(StrEnum):     # usable / candidates / pending
class CapabilitySource(_FrozenModel):
    name: str
    healthy: bool
    cooldown_remaining_s: float | None
class CapabilityCell(_FrozenModel):
    dataset: Dataset
    market: Market
    state: CapabilityState
    sources: list[CapabilitySource]
    reason: str | None

class MarketDataRouter:
    def capability_matrix(self) -> list[CapabilityCell]:
        # Dataset × Market 全叉积；声明 = dataset ∈ p.capabilities.datasets
        #                    and market ∈ p.capabilities.markets
        # 无声明方 → pending("no provider declares ...")
        # 有声明方且任一清醒 → usable
        # 有声明方全冷却 → candidates("all declaring sources are cooling")
```

冷却剩余秒 = `_cooling(name)` 的数值版：`health.cooling_until - clock()`（≤0 视为清醒）。复用 `_clock`（可测）。

### API（`api/routes/capabilities.py` 新文件）

`GET /api/v1/capabilities` → `CapabilitiesRead{generated_at, capabilities: list[CapabilityCell]}`（排序 dataset.value → market.value）。只依赖 `MarketData`，无 DB。`app.py` 注册。

## 测试

- `tests/unit/test_capability_matrix.py`（新）：
  - **真实生产矩阵钉死**（AC-1）：`default_router()` 直接构造，15 格、6 usable、9 pending、0 candidates，逐格断言 state（期望值写死字面量，不从被测代码读）。
  - candidates 路径：一个返回 `DATA_SOURCE_FORBIDDEN` 的 stub provider → 一次调用即入 300s 冷却 → 该格 candidates + healthy=false + remaining > 0。
  - 排序稳定性。
- `tests/unit/test_capabilities_api.py`：API 形状（200 / 15 格 / 枚举合法 / generated_at Z）。

## 风险

| 风险 | 对策 |
|---|---|
| 生产声明漂移使 AC-1 红 | 这是特性：矩阵的意义就是让漂移可见（改声明必须改测试并写理由） |
| Dataset 未来扩充 → pending 格自动增多 | 正确行为；AC-1 的字面量期望随之更新并注明 |
