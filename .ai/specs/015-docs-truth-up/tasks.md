# Tasks 015 · 文档与残留清理

## T1 · `docs/ARCHITECTURE.md`（P1）
- [x] 按真实分层重写：`api/` `domain/` `storage/` `providers/` `models/` `core/`
- [x] `checks/` `scripts/` **明确放在图外**（不是产品的一部分）
- [x] 真实请求流（含每请求连接、provider 能力路由、降级序 `ok > no_data > stale > error`、冷却）
- [x] 存储：双 PRAGMA 剖面 · 显式 manifest · DDL 与版本同事务 · 快照 + SHA-256 · append-only 触发器
- [x] 四态数据 + provenance
- [x] 可观测：Trace→Observation→Score · append-only · 不写用户原文
- [x] 测试策略 + 两条难守的纪律（变异检查 · 测试不得自己应用修复）
- [x] **`Deliberate non-goals`：把 v1 那套技术栈作为"已移除、勿加回"列出**
- [x] 顶部保留"上一版写了什么、为什么错"（照 `0003` 先例，不删改）
- [x] AC-1 复核：13 处旧技术栈命中，只允许出现在 non-goals 一节

## T2 · `status.md`（P2）
- [x] §一 S0 行：还差项去掉 trace 写入器
- [x] §三 `.ai/traces/`：❌ 未实现 → ⚠️ 写入器已实现、**验收未达成**（条数不足 50）
- [x] §四 验收①：三项全未达成 → **1 / 3 达成**
- [x] §三 `make check`：补 2026-09-28 更正（退出码 0 只在 UTF-8 成立）
- [x] §五 新登记 5 条：scripts 未纳入 mypy · 三依赖零 import · 无 `.gitattributes` · 控制台渲染未验证 · `pythonw.exe` 未验证
- [x] 顶部加注记：本文件曾违反自己"只改代码不改这里"的规则
- [x] 末行日期 2026-09-27 → 2026-09-28

## T3 · `HANDOFF.md`（P2）
- [x] 头部：交接人 + 2026-09-28 修订声明；去掉"工作树干净"（已不成立）
- [x] §二 进度：功能数 5 → **7**；知识层不再是"完全没做"；下一编号 → 014
- [x] §三 补 012 / 013 两行
- [x] §四 node：**已在 PATH**（v24.21.0），原文的 export 说明标失效
- [x] §四 新增：控制台是 cp936；换行是 LF 且无 `.gitattributes`
- [x] §五 命令：去掉 export；加"结论看退出码"
- [x] §六 下一个编号 012 → **015**
- [x] §七 下一步**重排**（原第 1 条已完成，标出依据）
- [x] **新增第九节：本文被自己推翻过的三处**（原话保留 + 为什么会错）

## T4 · 残留清理
- [x] 删 `backend/_fsrs_probe.py`（未跟踪，lint 红源）
- [x] **把它的五个探针问题写进变更日志**（删文件可以，知识不能跟着消失）
- [x] 删工作区根目录 `_k2_append_rule.py`（一次性补丁脚本，仓库外）

## T5 · 验收
- [x] `dev.py check` lint 由红转绿
- [x] `dev.py check` 10 道全过 + **退出码 0**
- [x] 后端测试 528 全绿
- [x] 工作树无意外文件
