# AlphaCouncil

> 一个基于 LangGraph 的多 Agent 投研系统 —— 四路混合检索、引用可溯源、全链路可观测。

[![CI](https://github.com/OWNER/alphacouncil/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/alphacouncil/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) | **简体中文**

---

## 为什么做这个项目

大多数 RAG 示例都是"给向量库套一个聊天框"。投研是更难的问题：

- **它需要多种检索策略。** 语义型问题（"市场在担心什么"）和精确型问题（"Q3 毛利率"）无法用同一个索引解决；关系型问题（"上游供应商是谁"）需要图，而不是向量。
- **它需要多个视角。** 估值、技术面、情绪、风险是真正不同的分析框架，而且它们会互相矛盾。
- **它需要可验证。** 投研结论如果没有出处，等于没有价值。每个论断都必须能追溯到文档。

AlphaCouncil 把这三件事当作**工程问题**来处理，而不是提示词问题。

## 架构

```
                        ┌──────────────────┐
                        │  Orchestrator    │  LangGraph 状态图
                        └────────┬─────────┘
        ┌────────────┬───────────┼───────────┬────────────┐
        ▼            ▼           ▼           ▼            ▼
   ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ 数据     │ │ 检索      │ │ 技术分析 │ │ 基本面   │ │ 舆情      │
   │ Agent   │ │ Agent    │ │ Agent   │ │ Agent   │ │ Agent    │
   └────┬────┘ └────┬─────┘ └────┬────┘ └────┬────┘ └────┬─────┘
        └───────────┴────────────┼───────────┴───────────┘
                                  ▼
                        ┌──────────────────┐
                        │ Research Agent   │  综合多方观点
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │  Risk Agent      │  风险审查
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │  Critic Agent    │  对抗式质疑
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │  Human Review    │  人工确认
                        └────────┬─────────┘
                                 ▼
                        带引用溯源的研报
```

### 检索层

单一向量检索在四类问题中的三类上都会失败，因此检索层并行运行四路召回后融合：

| 召回路径 | 后端 | 适用问题 |
|---|---|---|
| 稠密向量 | Qdrant + BGE-M3 | 语义、主题类问题 |
| 稀疏词法 | BM25 / SPLADE | 精确词、股票代码、数字 |
| 图检索 | LightRAG | 实体与关系类问题 |
| 结构化 | Text-to-SQL | 财务数据的聚合与计算 |

结果经 **RRF（Reciprocal Rank Fusion）** 融合，交叉编码器重排，压缩后注入 Agent。

## 核心特性

- **图编排的多 Agent 工作流**，支持条件路由与失败重试（LangGraph）
- **四路混合检索**，RRF 融合 + 交叉编码器重排
- **RAG 评测体系** —— 基于 RAGAS 的评测集，接入 CI
- **全链路可观测** —— 每个 Agent 步骤、工具调用、检索过程都在 Langfuse 中留痕
- **引用可溯源** —— 每个论断携带 `doc_id`、页码与原文片段
- **对抗式 Critic Agent** —— 专职质疑研究结论
- **Human-in-the-loop** —— 结论产出前需人工确认

## 技术栈

| 层 | 选型 |
|---|---|
| Agent 编排 | [LangGraph](https://github.com/langchain-ai/langgraph) |
| 检索框架 | [LlamaIndex](https://github.com/run-llama/llama_index) |
| 向量库 | [Qdrant](https://github.com/qdrant/qdrant) |
| 图检索 | [LightRAG](https://github.com/HKUDS/LightRAG) |
| 可观测性 | [Langfuse](https://github.com/langfuse/langfuse) |
| 后端 | FastAPI + Pydantic v2 |
| 前端 | Next.js + shadcn/ui + Vercel AI SDK |
| 数据 | [AKShare](https://github.com/akfamily/akshare) |
| 质量 | Ruff · mypy · pytest · pre-commit · GitHub Actions |

## 快速开始

```bash
git clone https://github.com/OWNER/alphacouncil.git
cd alphacouncil
cp .env.example .env          # 填入你的 API Key
make install                  # 创建虚拟环境并安装依赖
make test                     # 跑测试
make dev                      # 启动后端 + 基础设施
```

需要 Python 3.12+ 与 Node 20+。

## 项目结构

```
alphacouncil/
├── .ai/                  # Agent 开发框架
│   ├── constitution.md   # 项目宪法（最高约束）
│   ├── agents/           # 角色定义（架构师/开发/测试/审查）
│   ├── specs/            # 规格驱动开发的规格文档
│   └── logs/             # Append-Only 台账
├── backend/
│   ├── src/alphacouncil/
│   │   ├── agents/       # 各 Agent 实现
│   │   ├── retrieval/    # 四路召回、融合、重排
│   │   ├── graph/        # LangGraph 状态图
│   │   ├── tools/        # 工具注册表
│   │   ├── models/       # 领域模型
│   │   ├── api/          # FastAPI 路由
│   │   └── core/         # 配置、日志、可观测性
│   └── tests/            # unit / integration / eval
├── frontend/             # Next.js 应用
├── docs/                 # 架构文档与 ADR
└── deploy/               # Docker Compose
```

## 开发

本仓库由 AI Agent 在**规格驱动的工作流**下开发。无论你是人还是 Agent，动手前请先读
[`.ai/constitution.md`](.ai/constitution.md) —— 它定义了不可违反的规则：技术栈锁定、
类型注解要求、测试覆盖率门禁、禁止事项。

完整流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 路线图

- [x] **P0** 脚手架、Agent 开发框架、CI
- [ ] **P1** 数据层 —— AKShare 数据接入本地库
- [ ] **P2** 检索层 —— 四路召回 + 融合 + 重排 + 评测
- [ ] **P3** Agent 层 —— LangGraph 编排
- [ ] **P4** 可观测性 —— Langfuse 全链路追踪
- [ ] **P5** 前端 —— 带实时 Agent 轨迹的研究界面
- [ ] **P6** 开源打磨 —— 文档、截图、首个 Release

## 免责声明

AlphaCouncil 是研究工具，产出的是**带引用的分析师式研究笔记**，不是交易信号。
它不接入任何券商、不下单，其输出不构成投资建议。

## 许可证

[MIT](LICENSE)
