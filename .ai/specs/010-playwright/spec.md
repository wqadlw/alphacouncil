# Spec 010 · Playwright 入仓（浏览器层自动化，红线 12.1 的载体）

- **状态**：Active
- **目标阶段**：S0/S2 工程债（上一棒标注"当前最值得补的缺口"）· 宪法第十二条 12.1（红线三层落地之 UI 层）
- **依赖**：前端构建链（已完成）·宪法 12.1 五条 E2E 断言
- **授权说明**：引入 `@playwright/test` 为新依赖——宪法 3.2 要求变更记录说明，见下

---

## 宪法 3.2 依赖审批

1. **为什么现有依赖做不到**：vitest 只跑纯逻辑（node 环境）；React 渲染、DOM 断言、路由跳转、表单交互此前**零自动化**（上次人工验证的探针脚本"用完即删"，同类回归下次不会再被抓）。手写 puppeteer 式脚本 = 自造劣质轮子。
2. **替代方案对比**：Playwright（微软官方、多引擎、内置路由拦截/webServer/trace）vs Cypress（重、架构绑定）vs 手写 playwright-core 探针（无断言框架、无 CI 形态）。
3. **维护活跃度**：@playwright/test 持续周更，MIT。**许可 MIT 无传染**。
4. **exe 体积**：**零**——它是 devDependency，只存在于开发/CI 环境，不进 PyInstaller 打包物。

**运行时约束**：本机不下载 Playwright 浏览器，直接用已装的 **Edge（`channel: "msedge"`）**；CI（ubuntu）安装 chromium。

## 关键架构决定：API 层用 Playwright 路由拦截 mock

E2E 测试跑 **vite preview（真实构建产物）**，但 `/api/v1/**` 用 Playwright 内置 `page.route` 拦截并回放**文档化的契约夹具**：

- **为什么 mock**：行情四态、探针失败、冷却中……这些是"无网络就测不到"的路径；打真实源 = 测试 flaky + 违反测试纪律的精神。pytest API 层已把同一批响应形状钉死，两处同源（.ai 契约）。
- **为什么不连真后端**：连真后端的冒烟（regression 0003 的方式）有价值但 flaky 风险高（真实行情依赖外网）；本轮先落确定性层，全栈冒烟作为后续独立决策。
- **为什么跑 preview 而不是 dev**：测的是构建产物本身，顺带守构建；vite preview 继承 `server.proxy` 配置（被拦截的不走代理，未拦截的才会——测试里全部拦截）。

## 功能需求

| 编号 | 需求 |
|---|---|
| FR-1 | `@playwright/test` 入 devDependencies；`playwright.config.ts`：本地 `channel: "msedge"`、CI 安装 chromium；`webServer` = `vite preview`（构建后端口 4173） |
| FR-2 | `npm run test:e2e`；dev.py 增 `e2e` 门禁（`check` 全套包含它） |
| FR-3 | CI 增 `e2e` job（npm ci → playwright install chromium → build → test:e2e）并进 gate |
| FR-4 | **红线 9 断言**：今日页与关注池页全文不含「收益率」 |
| FR-5 | **红线 12 断言**：标的页止损面板输入亏损比例 → 页面出现「恢复所需年数」及年数文本 |
| FR-6 | 今日页断言：休市徽标（verdict=non_trading_day）显示「休市 · 最后交易日」；unknown 时**不**显示；到期条目文案含「观察期已到」且**不含**「触发」；空待办的诚实文案 |
| FR-7 | 关注池断言：理由为空 → 提交按钮 disabled + 提示文案；四态行情单元格（ok 带价格、error「取数失败」）；删除确认文案「记录没有被删除」 |
| FR-8 | 路由断言：未知 hash → 「这个地址看不懂」 |

## 验收标准

| 编号 | 标准 |
|---|---|
| AC-1 | `npm run test:e2e` 本机全绿（msedge，无需真实网络） |
| AC-2 | CI `e2e` job 全绿并进 gate |
| AC-3 | dev.py `check` 10 门禁全绿 |
| AC-4 | 变异：把「恢复所需年数」从止损组件删掉 / 把「收益率」塞进今日页 → 对应用例红 |
| AC-5 | 台账更新（status.md §五 浏览器层缺口行消除）+ 变更记录 |

## 已知的失败（本 spec 防的事故）

| # | 事故 | 防线 |
|---|---|---|
| 1 | 红线断言只存在于宪法文档（12.1：一条红线无法被 CI 拦住就只是意图） | FR-4/FR-5 进 CI |
| 2 | E2E 依赖真实行情 → flaky → 大家学会无视红灯 | 路由拦截 mock，确定性 |
| 3 | 测试环境与本机构建产物脱节（只测 dev server） | 跑 `vite preview` 构建产物 |
| 4 | Playwright 下载浏览器被墙/超时 | 本机用系统 Edge；CI 在 GitHub runner 下载 |
