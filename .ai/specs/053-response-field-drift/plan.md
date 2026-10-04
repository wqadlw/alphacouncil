# 053 · plan

## 技术方案

### 一、解析器（`backend/checks/rules/no_response_drift.py`）

**线的一侧**：复用 S-16 的构造方式 —— `TestClient(create_app(settings))` + `GET /openapi.json`，
⭐ 因为 pydantic 让这份 schema 与后端**永远一致**，⭐ 所以它就是「现实」，不需要快照。

**客户端一侧**：手写扫描器，⭐ 与 S-16/S-17 同量级（宪法 3.2.1 不许加运行时依赖）。

```
DECL   = ^(?:export )?(?:declare )?(interface|type)  NAME  [= ] {
MEMBER = ^  (?:readonly )? NAME  ?  :
```

⭐⭐ **一条必须写进 docstring 的规则：成员名的位置，累计深度必须为 0。**

⭐ 这不是风格选择，是**AC-5 的全部内容**：`due: {` 这一行既声明成员又开启嵌套，⭐
而「本行括号净值 > 0 就跳过」会把 `due` 丢掉并把它内部的字段提到顶层。
⚠️ 第四号探针就是这么错的，⭐ 而且是被 `tsc` 的既有正确性出卖的（`TodayPage.tsx:91` 在读 `due`）。

同时：成员正则只接受 `:`，**不接受 `(`** —— ⭐ 方法不是线上的字段。

**嵌套不递归。** 递归就得判定「`Today.due` 这个内联字面量是不是 `DueRead` 的镜像」，
⭐ 而内联字面量与具名类型在文本上同形，⭐ 判据会立刻退化成「字符串包含」。
⇒ 嵌套 schema 走豁免，⭐ 并把这件事写进规则的「已知的边界」。

### 二、判据与阈值

```
schema.properties ⊆ client_type.top_level_fields   ⇒  通过
```

`DISCRIMINATION_FLOOR` 的值由探针量出：⭐ 3 字段的 `Symbol` 被 `WatchlistEntry`、
`InstrumentDetail`、`TickerResolution` 三个类型同时满足 ⇒ **低于 4 个属性时子集匹配没有判别力。**
低于阈值 ⇒ **报 note**，⭐ 既不放过也不报红。

### 三、豁免表

`NOT_MIRRORED: dict[str, str]`，⭐ 形状照抄 S-16 的（仓库已有这个模式，⭐ 不发明第二个）：

- **必须带理由**，⭐ 且理由过不了 `_reason_is_real` ⇒ 报错（与 S-16 同一判据）。
- **必须活着**：表里有一条 schema 已经不在 `openapi.json` ⇒ 报错（与 S-16 同一判据）。
  ⭐ 「一条匹配不到任何东西的豁免不是豁免」是 S-16 自己交的学费（`no_enum_drift.py:430-432`）。

## 涉及文件

### 新增

| 文件 | 作用 |
|---|---|
| `backend/checks/rules/no_response_drift.py` | 规则本体 |
| `backend/tests/unit/test_response_drift.py` | 单元测试，⭐ **含调用 `run()` 的负例** |
| `.ai/specs/053-response-field-drift/{spec,plan,tasks}.md` | 本三件 |
| `.ai/regressions/0027-*.md` | 变异记录（M1..M5） |
| `.ai/memory/2026-10-04.md` | 工作日志，⭐ **补 10-03 与 10-04 两段** |
| `.ai/logs/changes/2026-10-04-spec-053-response-field-drift.md` | 变更记录 |

### 修改

| 文件 | 改什么 |
|---|---|
| `backend/checks/registry.py` | 加一条 `Rule(...)`，⭐ 放在 S-16/S-17 之后、S-14 之前（同样要构造 app） |
| `backend/src/alphacouncil/core/error_codes.py` | 加 `CHECK_RESPONSE_DRIFT` |
| `.ai/error-codes.md` | 登记同一码（`S-05` 双向守） |
| `.ai/checks/static/README.md` | §3 加一行（`S-12` 双向守） |
| `frontend/src/api.ts` | ⭐ **补 `DailySeries` 的 5 个字段**、**`DailyBar` 的 3 个字段** |
| `frontend/src/api.ts` | ⚠️ 加 `DailySeriesRead` 的镜像时**必须写清 `clamped` 的容差语义** |
| `backend/checks/rules/no_enum_drift.py` | ⭐ **删掉那句不存在的探测**（`:185-187` 声称 `test_static_checks.py` 有两个负例，⭐ 实测零命中） |
| `.ai/failure-modes.md` | 新增条目 |
| `.ai/status.md` | 同步（`:4` 「只改代码不改这里，视为未完成」） |

### ⚠️ 顺带修掉的三处**实测出来的不实陈述**

| 位置 | 声称 | 实测 |
|---|---|---|
| `backend/scripts/dev.py:157-158` | 「`check` 是 CI 门禁集：**everything, including the not-yet-written ones**」 | `CHECK` 里 11 个，**没有 `check-data`** ⇒ 这句注释是假的 |
| `.ai/status.md:82` · `.ai/memory/2026-10-02.md:186` · `.ai/logs/changes/2026-10-02-plan.md:95` | 「`check-data` 未实现 ⇒ **`dev.py check` 永远 INCOMPLETE**」 | ⭐ **实测 `dev.py check` 退出码 0** ⇒ 结论错。**真正的洞是那道门禁不在清单里，于是没人看得见** |
| `backend/checks/rules/no_enum_drift.py:185-187` | 「`test_static_checks.py` 用十个形状探测它，**其中两个必须不匹配**」 | 实测 `test_static_checks.py` 里 `S-16` 零命中 |

⭐⭐ **三处都是「一个检查声称自己被守着，而那个守护不存在」。**
⇒ 这本身就是本规格要处理的那一类缺陷，⭐ **所以它们进本规格，而不是进某个「顺手清理」**

## 关键取舍与理由（为什么不用更简单的方案）

| 想要的做法 | 为什么不做 |
|---|---|
| 提交 `openapi.json` 快照再 diff | ⭐ pydantic 让它与后端永远一致，快照只会多一个新陈旧源。**快照的价值在「人改了 schema 文件」，而这里没人改那个文件** |
| `openapi-typescript` 生成 `api.ts` | 要加依赖（`V-07`），⭐ 且会推翻 `api.ts` 1074 行的手写风格。`2026-10-02-plan.md:17` 已否 |
| 命名映射表（后端 schema 名 → 客户端类型名） | ⭐ 实测有 6 处改名、2 处内联 ⇒ 映射表有 8 个手工条目，⭐ 而 `no_raw_http.py:127-140` 已经写下：「这份表是手工维护的，⭐ 而那是一个会生长的洞」 |
| **精确相等** | ⭐ 探针量出 26 个不匹配 ⇒ **26 条的豁免表不是豁免表，是把缺陷改了个名字** |
| 递归进嵌套对象 | 内联字面量与具名类型文本同形，⭐ 判据退化成字符串包含 |
| 比对类型而不只是字段名 | 需要真正的 TS 解析器。⚠️ 本轮不做，⭐ **写进「已知的失败」，不假装覆盖** |
| 修 `notesContract.test.ts` 使其真的对照 `api.ts` | ⭐ 它的 fixture 是自己声明的字面量（实测只 import vitest）⇒ **改成真的对照会让它与 S-18 重复**，⭐ 而 S-18 是结构性的。⇒ 本轮**改掉那句声称**（AC-9），⚠️ 留作独立决定 |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| ⭐ **门禁第一天就红**（`2026-10-02-plan.md:101-103` 记的次序教训） | ⭐ **先修漂移（补 `api.ts`），再进规则**，⭐ 然后用变异证明它会咬。豁免表只放**结构上不可比**的那些（嵌套 schema、无客户端的 capabilities），⭐ 每条带理由 |
| 手写解析器被重排击败 | ⭐ **AC-5** 直接把三种排版（同一行 / 换行 / 缩进）写成断言 |
| ⭐ **`as T` 让 `tsc` 继续看不见这一切** | ⚠️ 本轮不动（改它要动 1074 行）。**明确记为未做**，⭐ 不假装这条门禁解决了类型安全 |
| 豁免表变成第七张手工表 | 每条豁免**必须活着**（schema 消失即报错）⭐ 且**必须带理由**（理由不合格即报错） |

## 对既有模块的影响

- **无**运行时代码改动。⭐ 只有 `api.ts` 的类型声明补全，⭐ **不新增页面、不新增字段的读取**，
  ⭐ 所以产品行为不变 —— 补的是「服务器早就在发、客户端没声明」的三处，⭐ 不是「客户端读不到的新东西」。
- ⚠️ 补 `DailyBar.fetched_at` 会让 `tsc` 开始检查它，⭐ 而**当前没有任何代码读它** ⇒ 不可能红。
- `S-18` 每次跑多构造一次 app。⭐ 与 S-16/S-17 同样的成本，⭐ 已在 `registry.py` 的注释里说明排序理由。
