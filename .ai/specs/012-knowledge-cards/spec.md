# Spec 012 · K1 知识卡片（Knowledge Cards）

- **状态**：Active
- **目标阶段**：S1 / S2（知识层最小单元，标的页第二层核心）
- **依赖**：标的层（`instruments`）· 存储迁移基础设施（0001, 0002）· 错误码与静态检查子系统（S-01~S-12）
- **依据**：
  - 宪法 5.2 规则 9 / 10 / 13（服务端生成唯一标识与时间戳、未成熟结果留 NULL）
  - 宪法 5.4.3 / 5.5（CHECK 约束与表结构设计）
  - 红线 4（Provenance Rule：主张必须包含可追溯来源）
  - 红线 11 / 15（AI 输出只做抽取草稿与候选，绝不可直接视为已核实证据；判断由人下）
  - ADR-0021 / ADR-0022（卡片数据结构、三分类、`origin` / `priority` / `status` 三字段，及三种录入通道）
  - `AlphaCouncil-基础功能打磨与AI桥接.md`（K1 知识卡片完整字段与 8 条高级金融风格规则）

---

## 一、背景与设计理念

在 AlphaCouncil 中，知识卡片不是无源笔记，也不是信息搬运，而是：
> **一条你愿意为它署名的判断，附带它能被追溯到的来源（Provenance Rule）。**

卡片是知识层最小的原子单元，其设计遵循以下核心原则：
1. **强制溯源（Provenance Rule）**：没有来源 URL 或数据采集时刻的卡片绝不许入库（数据库级 CHECK 约束与领域模型拦截）。
2. **严防确认偏差与三分类**：卡片分为 `supporting`（支持论点）、`challenging`（质疑/挑战论点）、`neutral`（中性事实）。
3. **三种录入通道与 AI 隔离（红线 15）**：
   - `user_written`：用户亲手撰写或人工核实过的卡片。
   - `extracted`：从研报/公告等确定性文本通过规则或工具辅助抽取的卡片。
   - `ai_generated`：AI 生成/问财回填的卡片。**代码层强制约束**：`ai_generated` 必须显式标记未经核实，默认不计入论点支撑统计，用户必须点“核对来源”后方可升级为 `user_written`。
4. **简洁高密度**：主张（`content`）为精炼的核心判断（单条不超过 500 字符，超过建议拆卡）。

---

## 二、数据契约与字段规格

### 2.1 卡片主表 (`cards`)

| 字段 | 类型 | 必填 | 默认值 | 约束 / 规则 | 说明 |
|---|---|---|---|---|---|
| `id` | TEXT | ✅ | - | PRIMARY KEY, `GLOB 'card_[0-9]*'` | 服务端生成时间戳毫秒 ID |
| `content` | TEXT | ✅ | - | `length(trim(content)) BETWEEN 1 AND 1000` | 主张文本（建议不超过 3 行） |
| `claim_type` | TEXT | ✅ | - | `IN ('supporting', 'challenging', 'neutral')` | 主张类型 |
| `source_url` | TEXT | ✅ | - | `length(trim(source_url)) > 0 AND (source_url LIKE 'http://%' OR source_url LIKE 'https://%')` | 来源 URL，必须合法网络协议 |
| `source_title` | TEXT | ✅ | - | `length(trim(source_title)) BETWEEN 1 AND 255` | 来源标题/文献名称 |
| `captured_at` | TEXT | ✅ | - | `strftime('%Y-%m-%dT%H:%M:%fZ', captured_at) = captured_at` | 服务端 UTC 毫秒时间戳 |
| `as_of` | TEXT | ➖ | NULL | `as_of IS NULL OR strftime('%Y-%m-%d', as_of) = as_of` | PIT 数据截止日期（如财报报告期） |
| `origin` | TEXT | ✅ | `'user_written'` | `IN ('user_written', 'extracted', 'ai_generated')` | 录入通道 |
| `priority` | INTEGER | ✅ | 3 | `BETWEEN 1 AND 5` | 优先级（默认 3） |
| `status` | TEXT | ✅ | `'active'` | `IN ('active', 'converged')` | 状态（活跃 / 已收敛） |
| `created_at` | TEXT | ✅ | - | `strftime('%Y-%m-%dT%H:%M:%fZ', created_at) = created_at` | 服务端创建时间戳 |

### 2.2 卡片-标的关联表 (`card_symbols`)
卡片支持关联 0 到多个标的（多对多）：
| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `card_id` | TEXT | ✅ | FOREIGN KEY REFERENCES cards(id) ON DELETE CASCADE | 关联卡片 ID |
| `market` | TEXT | ✅ | `IN ('sh', 'sz', 'bj')` | 交易所市场 |
| `code` | TEXT | ✅ | `GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'` | 6 位数字代码 |
| `created_at` | TEXT | ✅ | UTC 毫秒时间戳 | 关联时间 |
| 复合主键 | - | ✅ | `PRIMARY KEY (card_id, market, code)` | 保证关联幂等 |

---

## 三、接口规范 (API Routes)

Prefix: `/api/v1/cards`

### 1. `POST /api/v1/cards`
录入新卡片。
- **请求体（禁止传入 `id`, `captured_at`, `created_at`，S-06 门禁拦截）**：
  ```json
  {
    "content": "渠道库存是白酒的先行指标，通常领先报表 1-2 个季度。",
    "claim_type": "supporting",
    "source_url": "https://example.com/reports/liquor-channel-survey.pdf",
    "source_title": "XX证券白酒渠道调研报告",
    "as_of": "2026-06-30",
    "origin": "user_written",
    "priority": 3,
    "symbols": ["sh:600519"]
  }
  ```
- **响应**：`201 Created`，返回包含完整服务端赋值与 `display` 标的信息的 `CardRead` 模型。

### 2. `GET /api/v1/cards`
检索与筛选卡片列表。
- **Query 参数**：
  - `market` / `code`：按指定标的筛选
  - `claim_type`：按主张分类筛选 (`supporting` / `challenging` / `neutral`)
  - `origin`：按录入渠道筛选
  - `status`：按状态筛选（默认查全部或 active）
  - `limit` (默认 50, 最大 200)

### 3. `GET /api/v1/cards/{id}`
获取单张卡片详情。

### 4. `PATCH /api/v1/cards/{id}/verify`
升级 `ai_generated` 卡片为 `user_written`（“核对来源”操作）：
- 只有当前为 `ai_generated` 的卡片允许被核对升级。核对后 `origin` 更新为 `user_written`。

### 5. `GET /api/v1/instruments/{market}/{code}` 扩展
在标的详情响应 `InstrumentDetailRead` 中增加 `cards: list[CardRead]` 字段，使得标的页可一屏展示关联卡片。

---

## 四、前端交互与金融风格规范

1. **左侧 2px 竖线分类指示器**：
   - `supporting`：哑光金/稳健（`border-l-brass`）
   - `challenging`：警示/对质（`border-l-up`）
   - `neutral`：中性深蓝（`border-l-navy`）
2. **排版质感**：
   - 主张 `content`：衬线体（`serif text-[16px]`），字句笃定，空行紧凑。
   - 来源与时间：等宽与无衬线小字（`tabular-nums text-[12px] text-ink-faint`），来源 URL 始终直接展示并附带外链跳转。
   - `origin === 'ai_generated'`：显式标记醒目的浅色提示“AI 生成 · 待核实”，并提供“核对来源”交互按钮。
3. **标的页集成**：
   - 标的页在“我对它做过什么”下方、“决策记录”上方嵌入“知识卡片”区块，支持筛选与快速录入抽屉/折叠表单。
   - 移除 `NotBuiltYet` 中关于“知识卡片未建表”的说明。

---

## 五、验收标准 (Acceptance Criteria)

- **AC-1 (Schema & Integrity)**：
  - 数据库迁移 `0003_knowledge_cards.up.sql` 正确创建 `cards` 与 `card_symbols` 表，具备完整的 CHECK 约束。
  - `constraints.json` 与 `manifest.json` 同步更新，`tests/unit/test_storage.py` 双向一致性检查通过。
  - 回滚脚本 `0003_knowledge_cards.down.sql` 执行无误。
- **AC-2 (Domain & Validation)**：
  - 缺少 `source_url`、非法 URL、空白 `content`、非法 `claim_type`、超长文本等均在领域层拦截并抛出对应的语义错误码（`CARD_SOURCE_URL_REQUIRED`, `CARD_CONTENT_REQUIRED` 等）。
- **AC-3 (Security & Static Checks)**：
  - S-06 规则通过：`CardCreateRequest` 绝不声明 `id`, `captured_at`, `created_at` 等服务端字段，传入额外字段时返回 `422`。
  - S-05 规则通过：所有卡片相关错误码在 `.ai/error-codes.md` 和 `ErrorCode` 枚举中完备登记。
- **AC-4 (API & Endpoints)**：
  - `POST /api/v1/cards` 成功写入卡片与关联标的。
  - `GET /api/v1/cards` 支持多维度过滤。
  - `PATCH /api/v1/cards/{id}/verify` 正确将 `ai_generated` 升级为 `user_written`。
  - `GET /api/v1/instruments/{market}/{code}` 顺带返回该标的的所有卡片。
- **AC-5 (Frontend UI)**：
  - 标的详情页渲染卡片列表，严格遵守 8 条金融设计规范。
  - 提供创建卡片表单，来源必填。
- **AC-6 (Gates & Quality)**：
  - 后端 `ruff check`, `mypy`, `pytest` 全绿。
  - 前端 `typecheck`, `lint`, `vitest` 全绿。
