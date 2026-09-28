# 接手交接（HANDOFF）· 2026-09-28（OpenCode 修订）

> **写给下一个接手的 AI：从这里开始，读完本文再按 `.ai/agent-guide.md` 的顺序读其余治理文件。**
> 交接人：ZCode（GLM），2026-09-27 接手当日完成 8 轮开发（spec 004–011）。
> **2026-09-28 由 OpenCode 更新**：合并了当日第二批（spec 012/013 + 缺陷 0004 修复），
> 修掉了本文里已经失效的 3 处陈述，并在文末逐条列出。

---

## 一、项目一句话

**AlphaCouncil**：面向实战的**股市知识管理系统**（不是量化工作台、不荐股）。Windows 桌面程序（最终交付 `AlphaCouncil-Setup.exe`）。技术栈：Python(FastAPI) + SQLite + React(Vite/TS) + pywebview + PyInstaller。**由 agent 全程开发**，治理文件在 `.ai/`，是交付物的一部分。

主人三条硬约束：**① 写进简历**（agent 岗，面试官看编排/可观测/评测/工具协议/上下文/可靠性）· **② 主人自己日常会用**（数据准、断网能用、打开就有东西看）· **③ agent 全程开发**。
主人已**四次明示**「你决定，你规划，你落地，我给你所有的自主权力」——按路线图自主推进，不必反复请示；但**宪法红线不可交易**（不做预测/荐股、append-only、决策必须用户亲手写等，见宪法第一条）。

## 二、当前进度快照（详见 `.ai/status.md`，每行以"还差什么"结尾）

| 阶段 | 状态 |
|---|---|
| **S1 数据层** | ✅ 完成（D1 关注池 · D3 行情三源互备/磁盘缓存/交易日探针/能力矩阵） |
| **S2 标的页 I1** | ✅ 完成 |
| **S3 今日页 T1** | ⚠️ 最小切片完成（休市徽标、到期条件、关注池+行情；数据变化/重复检测两块明说"还没有"） |
| **S4 决策登记 J1** | ✅ 完成（J3 止损对质已做） |
| **S0 治理** | ⚠️ 宪法 v3.0 在、静态检查 12 条进 CI、trace 写入器已落地；**还差：specs 001/003 按 v3 修订、make eval** |
| **S5 打包 exe** | ⚠️ 仅最小程序冒烟过；前端构建产物还没进 PyInstaller |

**17 项功能：已完成 7 项 + 2 项部分**。未做的大头：**K3 FSRS 队列 / K4 检索 / 双向链接**（知识层剩余——产品本体、简历差异化的核心）、**J2–J5**（论点版本、四象限、重复检测、教训转卡）、D2 持仓、D4 财务 PIT、D5 事件、D6 市场温度。

**P0 已闭环**：加票带理由 → 每天打开看到动态 → 想买时被拦住。主人已在浏览器里看过效果（http://127.0.0.1:5173/）。

> ⭐ **知识层已不再是"完全没做"**：K1 卡片（spec 012）与 K2 卡片生命周期（spec 013）已落地，
> 标的页已有第五块"我对它说过什么"。**下一个 spec 编号是 014**（已占用：控制台编码）。

## 三、2026-09-27 的 8 轮 + 2026-09-28 的 2 项

| spec | 内容 | commit |
|---|---|---|
| 004 | 关注池接上行情（逐只四态定价 + 池页涨跌列） | `49c06e3` |
| 005 | 今日页最小切片（默认首页）—— **P0 收官** | `268c50f` |
| 006 | 磁盘缓存 SqliteCache + **首个真实 0002 迁移** + 修复 RealtimeQuote 往返缺陷 | `2516c99` |
| 007 | 交易日探针（指数日线最后一根 bar 判定，零节假日硬编码）+ 腾讯指数日线 `day` 键支持 | `6388591` |
| 008 | 能力矩阵 `GET /api/v1/capabilities`（usable/candidates/pending 三态 15 格）—— **S1 完成** | `47bf839` |
| 009 | v1 残留清理（/health 谎言段、research 501 存根、models/domain.py 全删） | `bd12822` |
| 010 | Playwright 入仓：13 条 E2E 跑构建产物，**第 10 道门禁 + CI job** | `323daa2`* |
| 011 | trace 写入器：每请求一条可回放 JSONL（Trace→Observation→Score），provider 取数自动成观察 | `cbfe46b` |
| 012 | **K1 知识卡片**：`cards` + `card_symbols`（0003 迁移，出处必填）+ 四动词 API + 标的页第五块 | `2a783b1` |
| 013 | **K2 卡片生命周期**：append-only `card_events`（0004 迁移）+ 带理由的 `converge` 出口 | `08d6a3c` |
| **014** | **门禁工具的控制台编码**（回归 0004）—— 见 `.ai/specs/014-console-encoding/` | 未提交 |

\* 注：远程历史里 010/011 前有一处**两提交被 API 推送合并为一**（`323daa2`，内容与本地逐字节一致）——推历史时若 `git pull --rebase` 会自动收敛，不影响任何内容。

**还没落库的欠账**（前任们积攒的批次决定，**接手后应尽早找机会落进宪法/specs**）：T-01~T-20（TSP）、S-01~S-11（SuperMemo）、F/L/V 三批（同类调研/可复用库/前端打磨）。详见 `.workbuddy-ai/memory/` 与 `references/deep-dives/`。

## 四、⭐ 本机环境（**不读这节会浪费一小时**）

| 工具 | 位置 / 用法 |
|---|---|
| ⭐ **Node / npm** | **2026-09-28 更正：已在 PATH 上** —— `C:\Users\23507\tools\node-v24.21.0-win-x64\`（v24.21.0）。**上一版本文写的"22.22.2 不在 PATH、需手动 export"已失效**，不必再 export。仍建议开工前 `node -v` 确认一次 |
| **Python** | 无全局 python。一律 `backend/.venv/Scripts/python.exe`（3.13） |
| **make** | 未安装。真实现是 `backend/scripts/dev.py`（`check` 10 道门禁 / `check-lite`） |
| **pytest 等** | `cd backend && .venv/Scripts/python.exe -m pytest -q` |
| **jq** | 未安装。**heredoc 有 MSYS 改写坑**——写脚本/改文件用编辑工具，别用 heredoc 管道 |

> ⭐ **2026-09-28 新增：控制台是 cp936（GBK）** —— 中文 Windows 的默认码页。
> 这不是"注意打印中文"的小事：它曾让 `dev.py check` **十道全过却退出 1**
> （回归 0004，已修）。**凡是要在这一行之后继续写工具输出，先确认目标流是 UTF-8** ——
> `scripts/_console.py::use_utf8()` 就是干这个的，细节与实测数据见
> `.ai/regressions/0004-console-encoding.md`。

**换行（2026-09-28 新增）**：仓库**没有 `.gitattributes`**，工作区实际是 **LF**，
`git` 每次都告警 "LF will be replaced by CRLF"。
**别用 `Path.write_text()` 做"恢复原文件"这类事** —— 它在 Windows 上会把 LF 写成 CRLF，
字节全变，SHA-256 校验会误报成"恢复失败"。要传 `newline=""`。
（已因此踩过一次，见 `regressions/0004` §变异检查。）

**网络（关键坑）**：
- `github.com:443` 直连被墙；用户 Clash 代理（git 全局配置 `127.0.0.1:7897`）**通常没开** → `git push` 会挂。**解法：用 `gh` 走 GitHub Git Data API 推送**（blob→tree→commit→ref，SHA 可与本地字节级一致；脚本按 `backend/_push_via_api.py` 惯例临时写、用完删，需支持删除文件=`sha:null`、多提交深度探测）。推完 `git update-ref refs/remotes/origin/main <远程SHA>` 校正跟踪 ref。
- `registry.npmjs.org` 直连可达；npm 全局配置里也有死代理 → 安装包加 `--userconfig=<空文件>` 绕过（别动用户全局 npmrc）。
- curl 本地端口必须 `--noproxy '*'`（环境可能残留代理变量，会产生 502 假故障）。
- 东财源**间歇性不可达**（降级链会自动切腾讯，属正常）；腾讯指数日线已支持。

## 五、跑起来与验收命令

```bash
# 后端（8000）
cd backend && .venv/Scripts/python.exe -m uvicorn alphacouncil.api.app:app --host 127.0.0.1 --port 8000
# 前端（5173，代理 /api → 8000）
cd frontend && npm run dev        # node 已在 PATH（见 §四）
# 全套门禁（10 道：后端 lint/typecheck/licenses/static-checks/test + 前端四道 + E2E）
cd backend && .venv/Scripts/python.exe scripts/dev.py check
# ⚠️ 结论看退出码，不要只看"ran 10 · passed 10"那一行 —— 曾经它绿着却退出 1（0004）
```

- 交接时 8000/5173 **两个服务正在跑**（不想沿用就 taskkill，重启命令如上）。
- 用户真实数据库在 `%LOCALAPPDATA%\AlphaCouncil\alphacouncil.db`（已迁移到 v2，含少量演示数据）；traces 落在旁边的 `traces/`。
- E2E 本机跑系统 **Edge**（`channel: "msedge"`，无需下载浏览器）；CI 装 chromium。

## 六、开发纪律（宪法摘要，动手前必读全文）

1. **非平凡功能先写 spec**（`.ai/specs/<编号>-*/`，**下一个编号 015**），门禁全绿才算完成。
2. **变异检查**：缺陷修复必须回答"故意改坏，测试会不会红？"——**并先确认变异真的生效**（有过假绿教训）。
3. **台账 append-only**：变更日志用四段式（想做什么/做了什么/结果/留下了什么）。
4. **宪法 2.2 新增机制三问**：具体故障 / 既有机制为何不行 / 必需还是可选——答不出就退回。
5. **审计脱敏**：trace/日志禁止写用户原文（trace 中间件根本不读 body）。
6. **UI 红线**：无收益率指标、止损必示恢复年数、理由必填禁用提交——已有 13 条 E2E 钉着（`frontend/e2e/`），改动别弄断。

## 七、建议的下一步（**2026-09-28 重排**；以 `.ai/status.md` 为准）

> 上一版的第 1 条（"K1 知识卡片建表 + 界面"）**已经做完了**（spec 012/013）——
> 这份文档自己落后了一个提交。所以下面每一条都标了依据，且**动手前请回到 `status.md` 复核**。

1. ⭐ **specs 001/003 按 v3 修订** + 把积压的批次决定（T/S/F/L/V）落进宪法 —— **S0 收尾**。
   理由：知识层已连做两块，spec 目录却还有 3 个 v1 方向的旧 spec（`002` 已标废弃），
   规格与实现已经对不上。**规格不可信时，"规格驱动"就是一句口号。**
2. ⭐ **`make eval` 评测集骨架** —— 简历验收①第二块。trace 写入器已就位（spec 011），
   现在缺的是**消费它的东西**。注意前提：`core/config.py` 有 `llm_provider` 配置项，
   但**运行期没有任何 LLM 调用**，所以"token/成本记录"要等真有 agent 之后才成立。
3. **K3 FSRS 队列** —— 知识层剩下的最大一块。`fsrs` 依赖**已预装但从未 import**。
   前任探针问过的五个问题（是否就地改传入对象 / 关 fuzz 是否确定 / 字典往返 /
   朴素 datetime / learning→review 毕业）记在 `.ai/logs/changes/2026-09-28-console-encoding.md` §②，
   按自己的 spec 重做一遍探针。注意 `fsrs.State` 只有三态，**"已推迟"必须自建表**。
4. **把 `scripts/` 纳入 mypy strict** —— 门禁工具本身无类型约束（`status.md` §五已登记）。
   优先级不高但很便宜，且它是"这个项目有没有被验证"的那一层。
5. **清理 `sqlalchemy` / `aiosqlite`** —— 声明了但全仓零 import（`status.md` §五已登记）。
   删除需走 ADR（`pyproject.toml` 明写 "Do not re-add without an ADR"）。
6. **S5 预研**：前端构建产物接入 PyInstaller（"打开即用"最后一公里）。
   顺带能验掉两条"未验证"：交互式控制台渲染、`pythonw.exe` 无控制台启动。
7. 交易日早晨核实 spec 007 的**盘中当日 bar 假设**（`status.md` §五 已登记；若证伪改常量即可）。
8. 全栈 E2E 冒烟（Playwright 打真实 uvicorn，作为第二个 project）——可选项。

---

## 九、2026-09-28：本文被自己推翻过的三处

记在这里而不是悄悄改掉，因为**"这份交接文档曾经说过什么"本身就是信息**。

| # | 原文写的 | 实际 | 为什么会错 |
|---|---|---|---|
| 1 | 「下一步 1：K1 知识卡片建表 + 界面」 | **已完成**（spec 012/013，`2a783b1` / `08d6a3c`） | 写完这份文档的同一个 agent 接着又做了两轮，文档没回头改。**交接文档的"下一步"天然会过期** |
| 2 | 「Node 22.22.2 **不在系统 PATH**，需手动 export」 | **已在 PATH**（`C:\Users\23507\tools\node-v24.21.0-win-x64`） | 环境变了没人记。按它去 export 会白折腾 |
| 3 | 「`make check` ✅ 已全绿，**退出码 0**」 | 本机上它**十道全过却退出 1** | 那句"退出码 0"只在 UTF-8 环境为真，而本机是 cp936。见回归 0004 |

> 三个都是同一类错误：**照抄上一份文档，没有回到代码里核实。**
> `.ai/status.md` 顶部写着"只改代码不改这里，视为未完成"——
> **本文（以及任何交接文档）都该受同一条约束**，只是当时没写进去。

## 八、联系方式与心理准备

- 主人在线时用中文、直接、报数据必须硬（file:line、可复现）；主人会在浏览器里实际点开看效果。
- **最有价值的审查发现是"漏了什么"**——本项目所有轮次的变更日志都在 `.ai/logs/changes/`，别重复踩：接手先读 `.ai/failure-modes.md`（8 类 65 条）。
- 诚实是最高纪律：**未运行的验证必须标"未验证"**，没做到的事不假装做到（宪法 §2.4）。
