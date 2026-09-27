# Plan · Spec 012 K1 知识卡片

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 一、方案全景

K1 知识卡片贯穿数据库存储、领域模型、FastAPI 路由及 React 前端页面，涉及的具体模块如下：

```
[ Frontend: InstrumentPage.tsx / CardSection.tsx / CardForm.tsx ]
                          │ (REST API)
                          ▼
[ API Routes: api/routes/cards.py · api/routes/instruments.py ]
                          │
                          ▼
[ Domain: domain/card.py (Card, ClaimType, CardOrigin, CardStatus) ]
                          │
                          ▼
[ Repositories: storage/repositories/cards.py ]
                          │ (SQLite Transactions)
                          ▼
[ Storage: 0003_knowledge_cards.up.sql (cards + card_symbols tables) ]
```

---

## 二、详细分层设计

### 1. 存储层 (Storage)
- **迁移文件**：
  - `backend/src/alphacouncil/storage/migrations/0003_knowledge_cards.up.sql`
  - `backend/src/alphacouncil/storage/migrations/0003_knowledge_cards.down.sql`
- **表结构设计**：
  - `cards`:
    - `id TEXT NOT NULL PRIMARY KEY`: 格式如 `card_1790503858200`
    - `content TEXT NOT NULL`: 主张内容
    - `claim_type TEXT NOT NULL`: `supporting` / `challenging` / `neutral`
    - `source_url TEXT NOT NULL`: 必须以 `http://` 或 `https://` 开头
    - `source_title TEXT NOT NULL`: 来源名称
    - `captured_at TEXT NOT NULL`: ISO 8601 UTC 毫秒时间戳
    - `as_of TEXT NULL`: YYYY-MM-DD
    - `origin TEXT NOT NULL`: `user_written` / `extracted` / `ai_generated`
    - `priority INTEGER NOT NULL`: 1..5
    - `status TEXT NOT NULL`: `active` / `converged`
    - `created_at TEXT NOT NULL`: ISO 8601 UTC 毫秒时间戳
  - `card_symbols`:
    - `card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE`
    - `market TEXT NOT NULL`
    - `code TEXT NOT NULL`
    - `created_at TEXT NOT NULL`
    - `PRIMARY KEY (card_id, market, code)`
    - 外键关联至 `instruments(market, code)`
- **约束注册**：
  - 更新 `backend/src/alphacouncil/storage/constraints.json`，将每条 CHECK 约束登记在 6 种标准类别中。
  - 更新 `backend/src/alphacouncil/storage/migrations/manifest.json`，添加版本 3。
  - 调整 `backend/tests/unit/test_storage.py` 中的预期约束总数断言（原 28 递增为新数）。

### 2. 核心与错误码 (Core & Error Codes)
- **新增错误码**（登记至 `.ai/error-codes.md` 与 `backend/src/alphacouncil/core/error_codes.py`）：
  - `CARD_CONTENT_REQUIRED`: 主张内容为空
  - `CARD_SOURCE_URL_REQUIRED`: 来源 URL 为空或格式不合法
  - `CARD_SOURCE_TITLE_REQUIRED`: 来源标题为空
  - `CARD_NOT_FOUND`: 指定卡片不存在
  - `CARD_ALREADY_VERIFIED`: 卡片非 `ai_generated`，无法执行核对升级
  - `CARD_TEXT_TOO_LONG`: 主张内容超过长度限制

### 3. 领域层 (Domain)
- **文件**：`backend/src/alphacouncil/domain/card.py`
  - 枚举：`ClaimType` (`SUPPORTING`, `CHALLENGING`, `NEUTRAL`)、`CardOrigin` (`USER_WRITTEN`, `EXTRACTED`, `AI_GENERATED`)、`CardStatus` (`ACTIVE`, `CONVERGED`)
  - 数据模型：`Card`, `CardDraft`
  - 工厂/校验函数：`build_card(...)`，校验 content 长度（1..1000）、URL 协议合规（http/https）、as_of 格式、priority 范围（1..5）。

### 4. 仓储层 (Repository)
- **文件**：`backend/src/alphacouncil/storage/repositories/cards.py`
  - `insert(connection, card, symbols, now=None) -> CardRow`
  - `get_by_id(connection, card_id) -> CardRow | None`
  - `list_for_symbol(connection, symbol) -> tuple[CardRow, ...]`
  - `query_cards(connection, ...) -> tuple[CardRow, ...]`
  - `verify_origin(connection, card_id, now=None) -> CardRow`

### 5. API 路由层 (API Routes)
- **文件**：`backend/src/alphacouncil/api/routes/cards.py`
  - `CardCreateRequest`: `content`, `claim_type`, `source_url`, `source_title`, `as_of`, `origin`, `priority`, `symbols`
    - 配置 `model_config = ConfigDict(extra="forbid")`，严格不暴露 `id` / `captured_at` / `created_at`，满足 S-06。
  - `CardRead`: 输出模型。
  - `POST /api/v1/cards` -> 创建卡片并建立标的映射。
  - `GET /api/v1/cards` -> 综合条件筛选。
  - `GET /api/v1/cards/{id}` -> 单卡详情。
  - `PATCH /api/v1/cards/{id}/verify` -> 核对升级。
- **扩展**：`backend/src/alphacouncil/api/routes/instruments.py`
  - `get_instrument` 增加返回 `cards` 列表（通过 `cards.list_for_symbol` 读取）。

### 6. 前端展示与交互 (Frontend)
- **文件**：
  - `frontend/src/api.ts`：扩展 `Card`, `CardInput` 类型与调用函数 `createCard`, `listCards`, `verifyCard`，在 `InstrumentDetail` 中增加 `cards: Card[]`。
  - `frontend/src/CardSection.tsx`：标的页上的卡片列表视图与录入表单组件。
  - `frontend/src/InstrumentPage.tsx`：挂载 `CardSection`，更新“还没有的部分”说明。
  - 样式遵循 8 条金融规则：
    - 2px 左竖线按 `claim_type` 显示不同基调色。
    - 主张衬线排版，URL 始终直接可见。
    - `origin === 'ai_generated'` 显示待核实徽章与核实升级操作。

---

## 三、测试规划

1. **存储与迁移测试** (`backend/tests/unit/test_storage.py`, `backend/tests/integration/test_migrations.py`):
   - 验证 0003 迁移与回滚正确，约束双向登记严格一致。
2. **领域单元测试** (`backend/tests/unit/test_card.py`):
   - 测试必填项校验（来源 URL、内容非空、长度截断、合法枚举值）。
3. **API 单元测试** (`backend/tests/unit/test_cards_api.py`):
   - 测试创建卡片成功返回与标的绑定；
   - 测试 S-06 规则（客户端试图传 id / captured_at 被拒 422）；
   - 测试核验接口与标的关联查询；
   - 测试标的页整合接口 `GET /api/v1/instruments/{market}/{code}` 附带卡片列表。
4. **前端测试** (`frontend/src/CardSection.test.tsx` 或等价测试):
   - 验证卡片列表渲染、样式语义、表单提交状态。
