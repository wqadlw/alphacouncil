# Spec 009 · v1 残留清理（检索层死配置 + research 存根 + v1 模型）

- **状态**：Active
- **类型**：清理（chore/refactor）—— 非功能新增，规格从简但边界照写
- **依据**：ADR-0006（v1 检索方向废弃）· ADR-0022（research 层不在 v3）· 宪法 3.1（LlamaIndex/Qdrant 明确排除）· **红线 15**（ResearchReport = agent 判断生成的产物，红线禁止）· 上一轮变更日志「下一步 #3」
- **授权说明**：删除 ResearchReport/ResearchRequest 此前标注"待主人确认"；主人已四次明示「你决定，你规划，你落地，我给你所有的自主权力」，本轮据此拍板。决策依据记录于变更日志。

---

## 背景与目标

`/health` 现在汇报 `retrieval.recall_top_k / graph_retrieval / text2sql`——一个**已废弃的方向**（ADR-0006）里**从未存在过的层**。任何人（半年后的我们、面试官、排查故障的用户）读它都会得出错误结论。这比"少一个配置"更糟：**系统在对自己撒谎**（failure-modes：未运行却暗示已通过的同族）。

同一批 v1 残留：检索调优字段、Qdrant/embedding/reranker/langfuse 连接配置、`/api/v1/research` 501 存根、`models/domain.py` 的整套检索模型（含撞红线 15 的 ResearchReport）。

## 功能需求

| 编号 | 需求 |
|---|---|
| FR-1 | `config.py` 删除：embedding_*（2）· reranker_model · qdrant_*（3）· langfuse_*（4 字段+生产校验分支）· recall_top_k · rerank_top_k · enable_graph_retrieval · enable_text2sql · URL 归一化校验器（两个字段全没了）· rerank≤recall 校验器。**保留**：env/log/api、llm_*（agent 桥接是锁定栈）、database_path、agent runtime guards（max_agent_steps 等，LangGraph 桥接的既定护栏） |
| FR-2 | `app.py`：`/health` 删除 `retrieval` 段；删除 `/api/v1/research` 501 存根与 ResearchRequest import（v3 无此方向；它回应 501 本身就是对查询者的误导） |
| FR-3 | 删除 `models/domain.py` 全文件 + `models/__init__.py` 重写：RecallRoute / RetrievedDoc / Citation / ResearchRequest / ResearchReport / StatementType / FinancialItem / **v1 Quote**（与 `models.market.Quote` 重名的遗留）。D4 财务层落地时按 5.2 规则 17（period_end + announced_at）重新设计，不继承这些形状 |
| FR-4 | `conftest.py`：删除 sample_quote / sample_docs 夹具与对应 import；LANGFUSE_* 环境清理条目移除（字段已不存在） |
| FR-5 | `.env.example`：删除 Embedding / Vector store / Langfuse / Retrieval tuning 四段与 Postgres DATABASE_URL 段（v1 遗物），换上真实存在的 `ALPHACOUNCIL_DATABASE_PATH` |
| FR-6 | 测试同步：`test_domain.py` 删除（纯 v1 模型测试）· `test_config.py` 删 4 个 v1 用例 + **新增"v1 字段保持不存在"的回归守卫** · `test_api.py` 的 health 用例改为断言 **retrieval 键不存在**、research 用例删除、openapi 路径断言更新 |

## 验收标准

| 编号 | 标准 |
|---|---|
| AC-1 | `/health` 不含 `retrieval` 键；`/api/v1/research` 返回 404；openapi 不含 research 路径 |
| AC-2 | 全仓（src + tests + .env.example）grep 无 qdrant/langfuse/embedding/reranker/recall_top_k/rerank_top_k/graph_retrieval/text2sql/ResearchReport/RetrievedDoc/RecallRoute 残留 |
| AC-3 | 新守卫测试：v1 字段名不出现在 `Settings.model_fields`——**故意把字段加回去，测试必须红**（本 spec 的变异检查） |
| AC-4 | 门禁全绿（后端 mypy/ruff/pytest + 前端四道不受影响 + 静态检查 + dev.py check） |
| AC-5 | 测试总数下降是**诚实的**：减少的每个用例都对应被删除的死物，变更日志逐条列出 |

## 已知的失败（本 spec 防的事故）

| # | 事故 | 防线 |
|---|---|---|
| 1 | `/health` 汇报不存在的层 → 排查者/面试官被误导 | FR-2 + AC-1 |
| 2 | v1 字段被"顺手加回来"（复制旧代码时） | AC-3 字段不存在守卫 |
| 3 | conftest 夹具删除导致静默少测 | 删除的测试在变更日志逐条列出；现存测试数记录对比 |
| 4 | 误删 llm_* / agent guards（它们是锁定栈的既定配置） | FR-1 明确保留清单 |

## 边界（本 spec 不做）

- Langfuse **数据模型**仍是可观测层的选定借鉴（宪法第三条）；删的是它的**连接配置**——trace 写入器落地时按本地文件语义重新设计。
- `core/error_codes.py` 无检索时代残留（已核实），不动。
- `models/market.py` 是 v2 数据契约本体，不动。
