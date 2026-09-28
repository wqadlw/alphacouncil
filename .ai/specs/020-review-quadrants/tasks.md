# Spec 020 · 任务清单

> 勾选 = 做过并**验证过**。没跑的格子留空并写"未验证"，不许预先打勾。
> 状态：2026-09-28

---

## 一、读原文（先做，不许跳）

- [x] 读 `AlphaCouncil-项目总纲.md` P0-3（§2.1 第 ④ 个时刻 + 落地表）—— 四象限判语、结果分硬门禁、"不显示盈利数字"
- [x] 读 ADR-0014 —— 三表分离、"是否已复盘"不可推断、`outcome` 允许 `failed`
- [x] 读宪法红线 5 / 10 原文
- [x] 读 `0001_initial.up.sql` 的 `decisions` —— 确认 **id 即时间戳**，无 `created_at`
- [x] ⭐ **回原文核对 ADR-0014 第 3 条**（乱码读成了相反的意思）

## 二、迁移 0006

- [x] `decision_review_state`（`due_at` / `reviewed_at` 可空且永不为 0 / 两个 CHECK）
- [x] `reviews`（`process_score` 1..5 / `outcome` 三值枚举 / `due_at_snapshot`）
- [x] ⭐ `reviews_not_scored_early_check` —— **硬门禁下沉到数据库**
- [x] append-only 两触发器
- [x] 索引（`due_at` / `decision_id` / `reviewed_at`）
- [x] down.sql + 迁移文件头的"为什么不加盈利数字列"
- [x] `manifest.json` / `constraints.json` / `APPEND_ONLY_TABLES` 三处同步

## 三、领域层 `domain/review.py`

- [x] `Outcome`（good / bad / failed）+ `is_good`
- [x] `ProcessBand` / `process_band()`（**3 分算坏**，并注明是判断不是笔误）
- [x] `Quadrant`（REPEAT / ACCEPTABLE / DANGEROUS / FIX / **UNKNOWN**）
- [x] `judge()` —— 六种组合 + 空白结果分 → `UNKNOWN`
- [x] `QuadrantJudgement.guidance()` —— 五句话，**测试钉住不含数字**
- [x] `Review` 域对象 + `is_due` / `outcome_still_blank`（时间注入）
- [x] 错误码 ×4

## 四、仓储 `repositories/reviews.py`

- [x] `schedule` / `get_review_state` / `has_been_reviewed` / `count_reviews` / `due_reviews`
- [x] `record()` —— **两表同事务**，调 `require_open_transaction`
- [x] ⭐ `reviewed_at` **只在写入结果分时盖章**（"已完成"，不是"有人写过东西"）
- [x] 门禁在仓储层**独立再挡一次**
- [x] `due_at` 由调用方给定，**不猜**（判据未定义）

## 五、测试 `tests/unit/test_reviews.py`（42 条）

- [x] 四象限六组合（含 `failed` 归坏结果）
- [x] 3 分算坏 —— 钉住，并注明对称化是"显然的清理"所以要钉
- [x] 空白结果分 → `UNKNOWN` 而非猜测
- [x] 五句文案都存在且**不含数字**
- [x] ⭐ `TestTheGateSurvivesBypassingTheDomain` —— 裸 SQL 也过不去
- [x] `TestTheModelHoldsNoFigure` —— 枚举**真实列名**（从迁移后的库读，不解析 SQL 文件）
- [x] 删 review 不会让"已复盘"变回未复盘
- [x] append-only UPDATE / DELETE 被拒
- [x] 半复盘不盖章 + 之后完成才盖一次
- [x] `reviewed_at` 可空且永不为 0

## 六、静态检查

- [x] ⭐ `S-05` 的 `CODE_PATTERN` 补 `REVIEW` 前缀（**第一次运行就抓到**）
- [x] `.ai/error-codes.md` 新增 `REVIEW_*` 表
- [x] 顺带修：该文件原有的**重复编号**（两个 2.6）与**漏登记的 S-13**
- [x] `pyproject.toml` —— `domain/review.py` 的 `RUF001` 窄豁免（**新先例，写了理由**）

## 七、变异（6 个，全中）

- [x] M1 3 分算好过程 → `TestProcessBand` 红
- [x] M2 把 `bad` 当好结果 → 四象限红（3 条）
- [x] M3 删掉数据库那一次拦截 → 裸 SQL 红
- [x] M4 加回 `profit` 列 → `TestTheModelHoldsNoFigure` 红
- [x] M5 去掉 append-only 触发器 → 红
- [x] M6 半复盘提前盖章 → 红（2 条）
- [x] 六次恢复**哈希全部一致**
- [x] ⭐ 变异 harness 自身出过两个 bug 并**记进 changelog**（解析器把 `"1 failed,"` 当成 0 个测试；M6 指错文件）

## 八、红线评测集

- [x] 红线 5 `none` → **`full`**（`test` 档，实跑）
- [x] 红线 10 `none` → **`partial`**（刻意不算通过 —— 没有界面）
- [x] `eval.py` 新增 `test` 档（**实跑**，与 `gate` 档的"只查声明未腐"区分开）
- [x] ⭐ 「跑了一个测试」= 退出码 0 **且** 实测跑了 ≥1 个
- [x] 基线 5/15 → **6/15**，并**记下两处自己算错的账**
- [x] 补上账本测试漏掉的 `full/partial/none` 断言（那个漂移一直没人看得见）

## 九、门禁

- [x] `dev.py check` **10/10 + 退出码 0**

---

## 十、明确未做

| 项 | 原因 |
|---|---|
| API 与复盘页 | 切片 2 |
| 金额 / 收益率列 | **红线 10 由数据模型保证**，不需要那一列 |
| 系统代打过程分 | 红线 15：判断必须由用户下 |
| "失败但…"措辞检查 | 需要 NLP；字段不判断，人负责 |
| 到期日自动算法 | 判据未定义，**不猜** |
| 复盘次数"够不够" | 会变成打卡 |
