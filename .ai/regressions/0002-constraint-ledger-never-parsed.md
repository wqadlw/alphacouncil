# 0002 · `constraints.json` 不是合法 JSON，声明的交叉校验从未运行

- **发现日期**：2026-09-26
- **严重级别**：P1
- **状态**：已修复
- **发现方式**：写 `tests/unit/test_storage.py` 的台账校验时，测试在**收集阶段**就崩了

## 现象

```
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 8 column 17 (char 273)
```

`constraints.json` 的第 8、12 行含**未转义的 ASCII 双引号**：

```json
"都会让测试失败。这样"迁移里漏掉一条约束"就不再是静默的。",
"（每个类别至少一个"必须被拒绝"的用例），这比比对字符串强。",
```

也就是说，**这个文件从未被任何程序读过**。

## 影响

比"格式错"严重得多。`constraints.json` 与 `manifest.json` 的 `$comment` 里都写着同一句话：

> 「本文件与 `.sql` 文件由 `tests/unit/test_storage.py` 交叉校验」

而**那个文件不存在**（全仓 `find . -name "test_storage*.py"` 返回空）。

于是两个文件互相声明对方会被校验，而两边都没有校验者。文件中所有"会被校验"的承诺，在被写下的那一刻就是空的 —— 这正是本项目一直在防的那类缺陷：

> **一个从未失败过的检查，很可能从未运行过。**

具体后果：台账里"库里有约束但台账没登记"这一类事故**不会有任何报错**（因为没人读台账）。这次修复过程中就真的发生了 —— 见下方"顺带发现"。

## 根因

手写 JSON 时把中文引号写成了 ASCII `"`。没有 linter 覆盖 JSON，而**唯一会读它的测试不存在**，所以错误一直不可见。

## 修复

1. `backend/src/alphacouncil/storage/constraints.json` —— 内层引号改 `「」`，并把文件历史写进 `$comment`。
2. 新建 `backend/tests/unit/test_storage.py` —— 兑现那句承诺，做**双向**比对：
   - 台账列了但 schema 没有 → 声明是空头支票
   - **schema 有但台账没登记** → "顺手加一条约束、忘了更新台账"的经典事故

   比对方式：用真实迁移 SQL 在**内存数据库**里建出 schema，再读 `sqlite_master`（它原样保留 `CREATE TABLE` 文本）。所以约束名来自一个**真的被创建过**的 schema —— 顺带证明迁移 SQL 能解析。

## 顺带发现（同一根因的两个后果）

| # | 问题 | 处理 |
|---|---|---|
| 1 | **3 条约束记错类别** —— `decisions_rationale_required_check` 等 3 条的形状是 `length(trim(x)) > 0`，属于宪法 **5.4.3** 的必填规则；而 5.4.2 第 5 类被明确限定为 `A OR B IS NOT NULL` 写法 | 新增第 6 类 `required`（标注来源 5.4.3），3 条归位。**记错类别此前不可见，因为全仓没有代码读它** |
| 2 | `0001_initial.up.sql:21` 说清单在"**同目录**" | 实际 `.sql` 在 `storage/migrations/`，清单在 `storage/`。改为"上级目录" |

## 回归测试

`backend/tests/unit/test_storage.py`（33 项），核心四条：

| 用例 | 挡什么 |
|---|---|
| `TestTheLedgerMatchesTheSchema::test_every_ledger_constraint_exists_in_the_schema` | 台账列了库里没有的 |
| `TestTheLedgerMatchesTheSchema::test_every_schema_constraint_is_registered` | **库里有台账没登记的** |
| `TestTheLedgerMatchesTheSchema::test_the_schema_really_has_the_constraints_it_claims` | **守卫的守卫** —— 若提取器什么都没找到，上面两条会在两个空集合上"一致通过"。断言总数 `== 24` |
| `TestEachCategoryMatchesItsShape::test_constraints_have_the_shape_their_category_claims` | 类别记错（按形状校验，不只看名字） |

## 变异检查（⚠️ 必填）

| 改坏哪里 | 哪个测试变红 | 结果 |
|---|---|---|
| 台账里加一条 schema 没有的约束 | `test_every_ledger_constraint_exists_in_the_schema` | ✅ **已确认变红** |
| schema 里加一条台账没登记的约束 | `test_every_schema_constraint_is_registered` | ✅ **已确认变红** |
| 把 `required` 改回 `conditional_required` | `test_constraints_have_the_shape_their_category_claims` | ✅ **已确认变红** |
| 拿掉一个表的 `append_only: true` | `test_every_table_with_triggers_is_declared_append_only` | ✅ **已确认变红** |

## 是否可被测试固化？

✅ 可以（文件内容与 schema 都是可断言的事实）。

## 遗留

- **只比对名字与形状，不比对表达式文本。** 有意为之：SQLite 会规范化表达式文本，比对字符串会引入脆弱的空白/引号差异。所以"约束存在但逻辑写反了"不会被这个测试抓到 —— 那要靠行为测试（`tests/unit/test_watchlist_api.py` 与 `tests/integration/test_migrations.py` 的"必须被拒绝"用例）。
- **`identity` 与 `conditional_required` 在"同字段 NULL 守卫"上仍可能互相误报**（`x IS NULL OR length(trim(x)) > 0`）。已在 `test_storage.py` 的 `CATEGORY_MARKERS` docstring 写明，没有假装它是严密的。
- **与 README 规则 3 的偏差**：规则要求"每个缺陷一个测试文件"，本条缺陷的测试位于 `tests/unit/test_storage.py` 而不是单独的 `tests/regressions/test_issue_0002.py`。理由：这些测试的 fixture（内存 schema、清单临时目录）是**文件级共享**的，拆成单文件会复制一整套脚手架，而"独立运行"用 node ID 已经能做到（`pytest tests/unit/test_storage.py::TestTheLedgerMatchesTheSchema`）。**这是一处有意偏差，不是遗漏。**
