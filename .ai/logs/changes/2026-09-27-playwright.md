# 变更记录 · 2026-09-27 · Playwright 入仓（spec 010）

- 日期：2026-09-27
- 类型：工程基建（测试栈）—— 浏览器层验证从"一次性人工探针"变为 CI 自动跑的断言
- 范围：
  - `frontend/package.json`（+`@playwright/test` devDep 1.63.0、`test:e2e` script）· 新增 `playwright.config.ts` · `vitest.config.ts`（vitest 排除 e2e）
  - 新增 `frontend/e2e/`：`fixtures.ts`（API 路由拦截契约）+ 4 个 spec 文件 13 条用例
  - 修改 `backend/scripts/dev.py`（+`e2e` 门禁，`check` 升至 10 门禁）· `.github/workflows/ci.yml`（+`e2e` job 并进 gate）
  - 新增 `.ai/specs/010-playwright/` · 修改 `.ai/status.md`
- 依据：宪法 12.1（红线 UI 层断言）/ 3.2（依赖审批，见 spec）/ 11.4 · 上一棒 #30/#31 的"浏览器层无自动化"缺口

---

## ① 想做什么

宪法 12.1 说"一条红线如果无法被 CI 拦住，它就只是意图"，并给了五条可直接落地的 E2E 断言；上一棒两次人工浏览器验证的成果（含抓到 regression 0003 的那次）**下次不会再自动跑**。本轮把 Playwright 入仓：五条断言里两条现在可落（红线 9/12），其余三条等对应页面存在，一并把今日页/关注池/标的页/路由的关键行为变成 CI 断言。

## ② 做了什么

**依赖审批**（宪法 3.2 四问全答，见 spec）：`@playwright/test` 为 devDependency，**不进 exe**。本机不下载浏览器，跑系统 **Edge**（`channel: "msedge"`）；CI 装 chromium。npm 安装用 `--userconfig=<空文件>` 绕过全局死代理（实测 PONG），未动用户全局配置。

**架构决定（最重要的一个）**：E2E 跑 **vite preview 构建产物**，`/api/v1/**` 用 Playwright `page.route` **拦截并回放契约夹具**——确定性、无真实行情依赖、四态可以随叫随到；pytest API 测试在线的另一侧钉着同一批响应形状。未匹配路径 404 显式失败——新端点必须显式接线，mock 不做静默兜底。

**13 条断言**（红线加粗）：
- 今日页：**休市徽标含最后交易日**（spec 007）· 到期条目说「观察期已到」且**不含「已触发」** · unknown 不显示徽标 · 空待办诚实文案 · **红线 9**（页面无"收益率+数字"形态，规则文字本身允许）
- 关注池：**理由为空 → 提交禁用 + 规则文案**（红线 13）· 四态单元格（ok 价格 + stale「旧」/ error「取数失败」）· 写入回执 · 移除文案「记录没有被删除」· **红线 9**
- 标的页：**红线 12**（止损面板输入 32%/15% → 「恢复所需年数：约 … 年」+「亏损是不对称的」+「这里没有『要不要卖』」）· 决策表单空态禁用 + 「还差：…」
- 路由：未知地址 → 「这个地址看不懂」

## ③ 得到了什么样的结果

| 项 | 命令 | 结果 |
|---|---|---|
| E2E 本机 | `npm run test:e2e`（Edge，构建产物） | **13 passed / 19.7s** |
| 全套门禁 | `scripts/dev.py check` | **`ran 10 · passed 10 · failed 0`**（e2e 成为第 10 道门禁） |
| 既有门禁 | vitest / oxlint / tsc / build | 全绿；**vitest 62 passed**（`vitest.config.ts` 排除 e2e 后不再误收 Playwright 套件） |

### 3.1 变异检查（2 条，全部变红）

| # | 改坏哪里 | 变红的用例 |
|---|---|---|
| M1 | 止损面板删掉「恢复所需年数：约」字样（红线 12 的载体） | `the stop-loss panel must state the years needed to recover（红线 12）` |
| M2 | 今日页渲染「你的收益率 +12.3%」（红线 9 的载体） | `no returns metric is rendered anywhere on the page（红线 9）` |

M2 的第一版变异（只塞"收益率"三个字）**没有变红**——暴露初版断言只查免责句存在、不查指标形态。断言据此重写为**意图**："收益率"后跟数字 = 成绩单 = 禁止；规则文字本身（"没有收益率、没有排行"）允许存在。

### 3.2 过程发现

- vitest 默认 include 会把 `e2e/*.spec.ts` 收进单测（Playwright 的 `test.beforeEach` 在 vitest 里直接报错）→ `vitest.config.ts` 显式排除，两套 runner 各用各的 `*.spec.ts` 命名。
- fixtures 键设计为一遍写对的经验教训：`page.route` 的 glob `**/api/v1/**` 匹配的是 URL，handler 键才是自己的事——首轮把 method 前缀写进键却按裸路径查找，12 条用例全 404，由 error-context 页面快照立即定位。

## ④ 留下了什么

- **新增能力**：E2E 成为第 10 道门禁（本地 + CI 同套）；红线 9/12 的 UI 层断言进 CI；浏览器层"用完即删"的缺口消除
- **未做（不假装做过）**：打真实 uvicorn 的全栈 E2E 冒烟（regression 0003 的方式，后续独立决策）· 红线 6/10 的两条断言（等持仓/结果展示页面存在）· trace 写入器（简历验收①）
- **下一步候选**：trace 写入器 · specs 001/003 按 v3 修订（S0 剩余）· 非交易日跳过取数的决策
