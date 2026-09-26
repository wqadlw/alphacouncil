# 变更记录：P0 脚手架与开发框架

- 日期：2026-09-25
- 范围：仓库初始化、Agent 开发框架、质量门禁
- 阶段：P0
- 状态：已完成

---

## 交付内容

### 1. 仓库骨架

```
alphacouncil/
├── .ai/           Agent 开发框架
├── backend/       Python 包（分层架构）
├── frontend/      Next.js 应用（P5 实现）
├── docs/          架构文档与 ADR
├── deploy/        Docker Compose
└── .github/       CI 与模板
```

后端分层遵循「依赖只向下」原则：`core` → `models` → `retrieval` → `agents` → `graph` → `api`。
`core` 不依赖任何上层模块，因此配置与日志可在无网络、无 LLM 的条件下测试。

### 2. Agent 开发框架（本阶段核心）

| 组件 | 文件 | 作用 |
|---|---|---|
| 项目宪法 | `.ai/constitution.md` | 最高约束：技术栈锁定、编码规范、测试门禁、红线、审查纪律 |
| 角色定义 | `.ai/agents/*.md` | architect / developer / tester / reviewer 四角色，含边界与自检清单 |
| 规格 | `.ai/specs/00{1,2,3}-*/spec.md` | 数据层、检索层、Agent 层的需求规格 |
| 架构决策 | `.ai/memory/decisions.md` | ADR-0001 ~ 0005 |
| 台账规范 | `.ai/logs/README.md` | Append-Only 纪律与记录模板 |

### 3. 质量门禁

**pre-commit**：通用钩子（大文件 / 密钥 / 行尾 / 合并冲突）+ ruff lint + ruff format + mypy + gitleaks。

**GitHub Actions**（`.github/workflows/ci.yml`）：

| Job | 内容 |
|---|---|
| `lint` | ruff check + ruff format --check |
| `typecheck` | mypy --strict |
| `test` | pytest，Python 3.12 与 3.13 矩阵，上传覆盖率到 Codecov |
| `secret-scan` | gitleaks（全历史） |
| `docs-check` | 校验治理文件存在（README / LICENSE / CONTRIBUTING / SECURITY / constitution / 4 个角色文件） |
| `ci` | 汇总门禁，任一必需 job 失败则整体失败 |

`docs-check` 是刻意设计的：它把「治理文件必须存在」从约定变成**强制**，防止框架随时间腐化。

---

## 缺陷修复记录

### D-1 · structlog 与 stdlib 集成错误（P1，已修复）

- **位置**：`backend/src/alphacouncil/core/logging.py`
- **现象**：每次 `logger.info()` 抛 `AttributeError: 'PrintLogger' object has no attribute 'name'`
- **根因**：`PrintLoggerFactory` 创建的 logger 无 `name` 属性，而处理器链包含 `structlog.stdlib.add_logger_name`
- **影响**：日志系统完全不可用；且该错误发生在每次日志调用，会污染所有上层逻辑
- **发现方式**：单元测试（`tests/unit/test_logging.py`）——**未进入运行时**
- **修复**：改用 structlog 官方推荐的标准库桥接方案
  - `logger_factory=structlog.stdlib.LoggerFactory()`
  - 处理器链末尾追加 `ProcessorFormatter.wrap_for_formatter`
  - 由 `logging.StreamHandler` 的 `ProcessorFormatter` 完成最终渲染
  - `cache_logger_on_first_use=False`，使 `configure_logging(force=True)` 对已获取的 logger 生效
- **附带收益**：第三方库（uvicorn / sqlalchemy / httpx）日志与业务日志走同一渲染器，格式统一
- **验证**：`tests/unit/test_logging.py` 9 个用例覆盖 JSON 输出、级别过滤、重复配置、stdlib 桥接

### D-2 · mypy 无法识别 pydantic-settings 构造参数（P2，已修复）

- **位置**：`backend/pyproject.toml`
- **现象**：`Settings(_env_file=None, **overrides)` 报多个 `arg-type` 错误
- **修复**：启用 `plugins = ["pydantic.mypy"]` 并配置 `[tool.pydantic-mypy]`
- **附带清理**：启用插件后部分 `# type: ignore` 变为多余，被 `warn_unused_ignores` 捕获并删除

### D-3 · starlette 1.7 要求 httpx2（P2，已修复）

- **现象**：`filterwarnings = ["error"]` 使 starlette 的弃用警告变成测试收集错误
- **修复**：dev 依赖加入 `httpx2>=2.0`

---

## 验证结果

```
ruff check .              → All checks passed!
ruff format --check .     → 14 files already formatted
mypy --strict src tests   → Success: no issues found in 14 source files
pytest tests/unit -m unit → 54 passed
coverage                  → 98.77% (gate: 80%)
```

模块覆盖率：

| 模块 | 覆盖率 |
|---|---|
| `core/config.py` | 100% |
| `core/logging.py` | 100% |
| `models/domain.py` | 96% |
| `api/app.py` | 100% |

---

## 待确认（阻塞 P1）

1. 关系型数据库选型：开发期 SQLite / 生产 PostgreSQL，还是统一 PostgreSQL？
2. 财务报表科目存储粒度：全量科目 vs 常用指标子集？
3. 评测语料来源与版权合规性（影响 P2 的 `tests/eval/`）。
