# Plan · Spec 010 Playwright

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 动作序列

1. `npm install --save-dev @playwright/test --userconfig=<空>`（绕过全局死代理；不动用户 npmrc）
2. `playwright.config.ts`：
   - `testDir: './e2e'` · `use: { baseURL: 'http://127.0.0.1:4173' }`
   - 本机 `channel: 'msedge'`（`process.env.CI` → 默认 chromium）
   - `webServer`: `npm run build && npm run preview -- --port 4173 --strictPort`
   - `retries: process.env.CI ? 1 : 0` · `fullyParallel: true`
3. `frontend/e2e/`：
   - `fixtures.ts`：`routeApi(page, handlers)` —— `page.route('**/api/v1/**')` 按路径回放 JSON 夹具；未匹配路径 → 404 显式失败（新端点出现时必须显式接线，防止 mock 静默兜底）
   - `today.spec.ts`（FR-6 + 红线 9）
   - `pool.spec.ts`（FR-7 + 红线 9）
   - `instrument.spec.ts`（红线 12 止损 + 决策表单禁用态）
   - `routing.spec.ts`（FR-8）
4. `package.json` scripts：`"test:e2e": "playwright test"` · `"e2e": build+preview 已由 config webServer 承担`
5. `backend/scripts/dev.py`：Gate 增 `e2e`（cwd=frontend，`npm run test:e2e`）
6. `.github/workflows/ci.yml`：`e2e` job + gate needs
7. 台账 + 提交

## 夹具契约（与 pytest API 测试同源）

| 端点 | 夹具要点 |
|---|---|
| `GET /api/v1/today` | attention 1 条（600519 buy，criterion as_of 昨天）+ market_status 可参数化（non_trading_day / unknown）+ 空态变体 |
| `GET /api/v1/watchlist` | 2 条（sh ok / sz error 用两个不同标的） |
| `GET /api/v1/watchlist/quotes` | 逐行四态：600519 ok(stale)、000002 sz error、000036 no_data |
| `GET /api/v1/instruments/sh/600519` | detail + 1 条决策（含谓词） |
| `POST /api/v1/watchlist` / `remove` | 201 receipt 形状 |

## 风险

| 风险 | 对策 |
|---|---|
| npm 安装被全局死代理挡 | `--userconfig` 指向空文件（已验证 PONG）；不动用户全局配置 |
| CI 无 Edge | CI 安装 chromium，config 按 CI 环境变量切换 |
| 未拦截的新 API 请求打穿到 preview 代理 → 假数据/挂起 | fixtures 未匹配路径 → fulfill 404 并在测试输出可见 |
| dev.py 的 e2e 门禁拖慢 check | 全套 < 2 分钟；check-lite 不含它 |
