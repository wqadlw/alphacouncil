# Plan · Spec 009 v1 残留清理

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 动作序列（删除型变更，顺序即安全）

1. `config.py`：删 8 类字段 + 2 个校验器（URL 归一化、rerank≤recall）+ langfuse 生产分支
2. `app.py`：删 /health 的 retrieval 段 + /api/v1/research 存根 + ResearchRequest import
3. 删 `models/domain.py`；`models/__init__.py` 重写为包说明（暂无导出）
4. `conftest.py`：删 sample_quote / sample_docs / Quote·RecallRoute·RetrievedDoc import / LANGFUSE_* 清理项
5. 删 `tests/unit/test_domain.py`（纯 v1 模型测试，先确认无其他被测物）
6. `test_config.py`：删 4 用例（recall/rerank、rerank 校验、URL 归一化、langfuse 生产分支）+ 精简 credentials 用例 + 新增 `test_v1_fields_are_gone`
7. `test_api.py`：health 两用例改写（retrieval 键不存在断言 + llm_model 覆盖保留）、TestResearchEndpoint 删除、openapi 断言改 watchlist
8. `.env.example`：删 Embedding / Vector store / Langfuse / Retrieval tuning / Postgres DATABASE_URL 段，补 `ALPHACOUNCIL_DATABASE_PATH`

## 守卫

- `mypy --strict` + `ruff F821`：任何漏改的 import 即红
- 全仓 grep（AC-2 清单）零残留
- 新守卫测试：`Settings.model_fields` 不含 v1 字段名（变异：加回 → 红）

## 测试数变化（诚实账）

| 动作 | 数 |
|---|---|
| 删 test_domain.py（纯 v1） | −9（以实际为准） |
| 删 test_config 4 用例、test_api research 6 用例 | −10 |
| 增守卫 / 改写 | +2 |

预计总数下降 ~17，全部对应被删除的死物；变更日志逐条列。

## 风险

| 风险 | 对策 |
|---|---|
| `models/__init__` 被某处 `from alphacouncil.models import Quote` 依赖（v1 Quote） | 先 grep 全仓再删；market.Quote 是唯一合法来源 |
| 静态检查（S-XX）引用被删字段 | 已核实 test_static_checks 与 checks/rules 无引用 |
| dev.py 的前端门禁不受影响 | 本轮零前端改动 |
