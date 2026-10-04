# 2026-10-04 · spec 053 · 响应字段漂移门禁

## 1. 做了什么

- 新增 `S-18 no-response-drift`（`backend/checks/rules/no_response_drift.py`）：
  把 `openapi.json` 发布的字段与 `frontend/src` 的具名类型对账。
- 新增 `CHECK_RESPONSE_DRIFT`（`error_codes.py` + `.ai/error-codes.md`）。
- 补齐 `api.ts`：`DailyBar` +3 字段、`Quote` +1、`DailySeries` +5。
- 新增 `tests/unit/test_response_drift.py`：**34 条**，含 5 条调 `run()` 的负例。
- 补齐两个 fixture（`quoteSummary.test.ts`、`indicatorOverlay.test.ts`）：
  新增字段后 `tsc` 报错，门禁正确地拦下了它们。
- 修三处实测出来的不实际述（`dev.py:157-158`、`status.md` B4、`no_enum_drift.py:185-187`）。

## 2. 为什么做它

实测：`DailySeriesRead` 的 5 个字段与 `Quote` 的 3 个字段到了线上而 `api.ts` 未声明，
而 **17 道静态检查 / 1432 条后端测试 / 137 条 e2e 全绿**。

根因：十七道检查比的全是「枚举值」与「(动词, 路径)」，
字段这一层从来没有人对过账。

外部调研的两条结论：

- ★ API Evangelist FAQ：「diff 那一步是最多团队跳过的一步，也是唯一真正抓到漂移的一步，
  因为它把文档和现实对照，而不是和它自己对照」。
- `contractsentry` 的检查表：「**Missing response field | error**」。

⚠️ 全部现成方案（`openapi-typescript` / Pact / oasdiff）都要加依赖或过重 ⇒ `V-07` 已否。

## 3. 门禁

`dev.py check` **11/11 · 退出码 0**
后端 1468 · 集成 43 · 前端 226 · 静态 **18 条 33 findings 0 error 0 warning** · e2e **137 ok / 0 not ok**。

## 4. ⚠️ 未做（不假装做过）

- 不比类型，只比字段名 —— 需要一个真正的 TS 解析器，而 `constitution.md:3.2.1` 不许加依赖。
- 不覆盖嵌套 schema 与请求体 —— 两者都在豁免表里，而不是被它检出来。
- 不改 `api.ts:486` 的 `as T` 无检查断言 —— 改它要动 1074 行，且不在本规格范围内。
- 不修 `notesContract.test.ts` 声称虚假的那句话。
- 不把 12 张豁免表重写成新客户端类型 —— 它改的是页面读的字段，需要主人点头。
- 变异脚本不入仓（`F-140`），结果在 `.ai/regressions/0027`。
- 三段提交均**未 push** —— `github.com:443` 经 `127.0.0.1` 代理连不上。
