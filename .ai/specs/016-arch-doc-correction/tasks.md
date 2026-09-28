# Tasks 016 · 架构文档更正与 ADR 双真源消除

## T1 · 核实（先证实，不凭印象）
- [x] 读宪法第三条原文（`:176-194`）—— LangGraph / Langfuse / fastmcp **都在锁定表里**
- [x] 读 ADR-0001 在 `.ai/memory/decisions.md` 的真身 —— ✅ 已采纳，**理由已修订，结论不变**
- [x] 扫 `pyproject.toml` —— **无 langgraph**
- [x] 扫全仓 import —— langgraph / langfuse / fastmcp **零引用**（trace.py 只是注释里提到数据模型来源）
- [x] 搜谁引用 `docs/adr` —— **零引用**
- [x] 确认 v1→v2 移除清单**不含** LangGraph

## T2 · `docs/ARCHITECTURE.md`
- [x] 顶部保留两次更正（旧的错 + **我的错** + 为什么错）
- [x] LangGraph 移出 `Deliberate non-goals`
- [x] non-goals 补齐 LlamaIndex / Next.js（确实被移除的）
- [x] 新增「Adopted but not implemented」：六项逐行写状态
- [x] 扩展点加一行：**技术决策只写 `.ai/memory/decisions.md`**
- [x] 清掉与新章节重复的 `fsrs` 段落

## T3 · 消除 ADR 双真源
- [x] `git rm docs/adr/0001-agent-orchestration-langgraph.md`
- [x] `docs/adr/README.md`：说明为什么删、指向真源、禁止再往这里写

## T4 · 宪法 + ADR
- [x] 宪法第三条加 §3.0（**纯追加**），五行差异 + 「待人工确认」
- [x] 新增 **ADR-0027**（含启用条件）
- [x] 决策索引 加 ADR-0027 一行

## T5 · 留痕
- [x] `regressions/0005-arch-doc-and-adr-divergence.md`
- [x] `regressions/index.md` 登记 + 第 5 轮说明
- [x] `regressions/README.md` §五 状态表（5 条回归）
- [x] `agent-guide.md` §3.1 加第 3 条纪律
- [x] `status.md` §五 新登记 3 条
- [x] 四段式变更日志

## T6 · 验收
- [x] `dev.py check` 10 道全过 + 退出码 0
