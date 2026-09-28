# 2026-09-28 · 文档与残留清理（spec 015）

> 四段式台账（宪法 10.5）。**append-only：只追加，不改写。**
> 执行者：OpenCode（Codex · Space Bunny Free）

---

## ① 想做什么

把接核查到的另外三处缺陷做掉（第一批是 spec 014 / 回归 0004）：

| # | 缺陷 | 级别 |
|---|---|---|
| ② | `docs/ARCHITECTURE.md` 描述的技术栈已被宪法 v2.0 **全部移除** | P1 |
| ④ | `status.md` 违反了自己定的规则 · `HANDOFF.md` 落后一个提交 | P2 |
| ③ | 残留草稿 `backend/_fsrs_probe.py` 打断 lint 门禁 | P2 |

**为什么②最严重**：一份"缺失"的文档只是没用；一份**自信地写错了**的架构文档，
会让每个新接手的人和每个面试官建立完全错误的认知。**它比没有文档更贵。**

## ② 做了什么

### `docs/ARCHITECTURE.md` —— 重写

按**实际仓库**重写，不是按意图。写了：真实分层（`checks/` `scripts/` 明确在图外，
因为它们不是产品的一部分）· 真实请求流（每请求连接不共享 · 能力路由 ·
降级序 `ok > no_data > stale > error` · 冷却）· 存储（双 PRAGMA 剖面 · 显式 manifest ·
DDL 与版本同事务 · 快照 + SHA-256 · append-only 触发器）· 四态数据与 provenance ·
可观测（Trace→Observation→Score）· 测试策略 · 扩展点。

**关键决定：把 v1 那套技术栈移进 `Deliberate non-goals`，而不是删掉。**
照 `regressions/0003` 的先例（"保留原文并追加更正，因为'曾经把风险说反了'本身值得留在文件里"），
文件顶部写明上一版写了什么、为什么在 2026-09-26 被移除、并附宪法的原话。

> 一份从不说自己错过的文档，读者无法判断它哪些话可信。

### `status.md` —— 更正 + 新登记

| 位置 | 原 | 改 |
|---|---|---|
| §一 S0 | 还差 trace 写入器 | 去掉（已落地） |
| §三 traces | **❌ 未实现** | ⚠️ 写入器已实现、**验收未达成**（条数不足 50，且没有 `make eval` 消费它） |
| §四 验收① | 三项全未达成 | **1 / 3 达成** |
| §三 make check | 已全绿 · 退出码 0 | 加更正：那**只在 UTF-8 环境成立**（0004） |
| §五 | — | **新登记 5 条** |
| 顶部 | — | 加注记：本文件曾违反自己"只改代码不改这里"的规则 |

§五 新登记的 5 条（每条都写明"还差什么"）：

1. ⭐ **`scripts/` 完全没有被 mypy 检查** —— `files = ["src","tests","checks"]`。
   问题在于：这三个文件是"决定这个项目有没有被验证"的那一层。
2. ⭐ **三个运行期依赖已声明但从未被 import** —— `sqlalchemy` / `aiosqlite` / `fsrs` 零引用
3. ⚠️ **仓库没有 `.gitattributes`** —— 换行靠 `core.autocrlf` 兜
4. ⚠️ 未验证：门禁工具在**真实交互式控制台**下的渲染
5. ⚠️ 未验证：**`pythonw.exe`（无控制台）启动**

### `HANDOFF.md` —— 更正 + 新增第九节

- 进度：功能数 5 → **7**；知识层不再是"完全没做"；下一个编号 → 015
- node：**已在 PATH**（v24.21.0），原文的 export 说明标失效
- 新增：控制台是 cp936 · 换行是 LF 且无 `.gitattributes`
- 下一步**重排**（原第 1 条"K1 知识卡片"已完成）
- **新增第九节「本文被自己推翻过的三处」**：原话保留 + 为什么会错 + 一句总结
  （三个都是"照抄上一份文档，没有回到代码里核实"）

### 残留

- 删 `backend/_fsrs_probe.py`（**它的五个探针问题已抄进本文档 §② 之后**，
  知识不能跟着文件一起消失）
- 删工作区根目录 `_k2_append_rule.py`（一次性补丁脚本，仓库外）
  —— 顺带说明：它的 docstring 写着 "CRLF preserved" 并显式设 `NL = "\r\n"`，
  **前任也踩过换行这一类**

## ③ 得到了什么样的结果

| 验收 | 结果 |
|---|---|
| AC-1 `ARCHITECTURE.md` 不再出现已移除技术栈（除 non-goals） | ✅ **机械复核**：全文 8 处命中，**L9-10 在顶部更正说明、L204-208 在 non-goals 表**，无其他位置 |
| AC-2 描述的每个层/模块都能指到具体文件 | ✅ 逐条指认过（`src/alphacouncil/` 实际目录 · `storage/migrations/` 实际 4 个迁移 · `constraints.json`） |
| AC-3 traces 三处与 `core/trace.py` 一致 | ✅ 文件与测试都在仓库里 |
| AC-4 §五 5 条齐全 | ✅ |
| AC-5 `HANDOFF.md` 无已完成项、编号 = 015 | ✅ |
| AC-6 无未跟踪文件、lint 转绿 | ✅ |
| AC-7 被删文件的知识落进台账 | ✅ |

### 门禁（实机）

- `dev.py check` **10 道全过 + 退出码 0**（lint 从红转绿是本次唯一门禁变化）
- 后端测试 **528 passed**
- `ruff` / `mypy --strict` 全绿

### 顺手发现的一个**交接阻塞项**（不在三处缺陷里，但比其中两处更急）

`git commit` 报了一条错：

```
error: refs/remotes/origin/main does not point to a valid object!
```

查证：

| 检查 | 结果 |
|---|---|
| `.git/refs/remotes/origin/main` 内容 | `fe9750b97c4b7bd697670457cf8f03ec6d19ffba` |
| `git cat-file -t fe9750b9` | **`fatal: Not a valid object name`** —— 该对象**不在本仓库** |
| `git show-ref` | `fatal: bad ref refs/remotes/origin/HEAD` |
| 本地 `main` | `ef38fab`（本次提交，正常） |

**成因**：上一位 agent 用 Git Data API 推送后执行了
`git update-ref refs/remotes/origin/main <远程SHA>`（HANDOFF §四 记着这个惯例），
但那个 SHA **从没被 fetch 回来**。于是跟踪 ref 指向一个不存在的对象。

**影响**：任何带 upstream 的 `git status` 直接报错，`git pull` 会失败。

**没有直接修**，理由：**我无法知道 GitHub 上真正的 main 在哪** ——
`github.com:443` 直连被墙，查不到。**凭空把 `origin/main` 指到某个本地提交是危险的猜测**：
若 GitHub 上其实有更多提交，猜错会让后续 `push` 静默漏掉它们。
这正是本项目"不假装做过"的纪律在 git 层面的应用 ——
**不知道就说不知道，并且把"怎么才能知道"写下来。**

已写进 `HANDOFF.md` §四，并在原有的 API 推送惯例上加了一句警告。

### 本次**顺手发现**的（不属于三处缺陷，但同一类）

`sqlalchemy` / `aiosqlite` / `fsrs` 三个运行期依赖**全仓零 import**。
逐个搜 `^\s*(import|from)\s+<name>\b` 确认，不是靠印象。
其中 `fsrs` 是**有意预置**给 K3 的；`sqlalchemy` + `aiosqlite` 是
**迁移到裸 `sqlite3` 之后忘删的残留**——`config.py:89` 甚至写着
"这个连接串已被替换"。白白增加 PyInstaller 体积（S5）与许可扫描面。

**没有直接删**：`pyproject.toml` 明写 "Do not re-add without an ADR" ——
**删除也要走 ADR**。已登记为下一步。

## ④ 留下了什么

### 文档的更正方式（可复用的做法）

| 做法 | 理由 |
|---|---|
| 保留失效原话 + 追加更正 | 照 `0003` 先例。"曾经说反过"本身是信息 |
| 已移除的技术进 **non-goals** 而不是删除 | 让下一个人**不会顺手加回来** |
| 每个数字都来自一次实际运行 | 写"528"而不跑，就是把 0004 换个地方重犯 |
| 顶部标注"本文件曾违反自己的规则" | 否则"曾经从未做过"会从历史里消失 —— `regressions/README.md` 的原话 |

### 新登记的 5 条缺口（已进 `status.md` §五）

见 ②。其中 1、2 两条我给了具体下一步，且都**很便宜**：
把 `scripts` 加进 mypy `files`；走一条 ADR 删两个依赖。

### 本条**没有**做的事

| 不做 | 为什么 |
|---|---|
| 删 `sqlalchemy` / `aiosqlite` | 需 ADR（见上） |
| 顺手重写整篇 `HANDOFF.md` | 最小改动：改失效的 3 处 + 加一节 |
| 修 §五 新登记的 5 条缺口 | 那是 spec 016+ 的事。本 spec 只负责**让缺口被看见** |
| 动根目录产品文档（`产品定义-v3.md` 等） | 那是**产品意图**，不是现状描述，不存在"过期" |
| 动 `references/`（18 个借鉴项目 · 13 篇深度解读） | 外部档案，本就允许滞后 |
| 修工作区根目录 `README.md` | 它也有陈旧处（写"深度解读 2/11"、实际 13 篇），但**不在 git 仓库内**，且不是本轮三处缺陷之一。已向主人单独提出 |
