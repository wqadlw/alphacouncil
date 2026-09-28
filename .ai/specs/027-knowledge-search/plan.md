# spec 027 · 计划

| # | 步骤 |
|---|---|
| 1 | 迁移 `0008_notes_search`：`notes_fts` 虚拟表 + 三个触发器 |
| 2 | 台账加 `notes_fts`（`constraints: {}`）· `append_only: false` 并写明为什么 |
| 3 | `test_storage.py` 加一条测试：**`{}` 只允许虚拟表** |
| 4 | `repositories/notes.py` 加 `search()` —— ≥3 走 FTS5，<3 走 LIKE |
| 5 | pytest：3 字 / 2 字 / 编辑后 / 删除后 / 排序不变 / 通配符 |
| 6 | API 加 `?q=`（与 `?tag=` 共存） |
| 7 | 前端 `VaultPage` 搜索框 + 契约测试 |
| 8 | 变异检查 + 门禁 + 台账 |
| 9 | ⭐ 顺带：把 `detail` 槽位用上（知识库页天然是「很多条 → 选一条 → 读它」） |

## ⭐ 预置的三条

1. **导航不能挂计数** —— `nav.spec.ts` 断言导航内**无任何数字**、无催促词。
2. **`retrospective.spec.ts` 断言危险象限下 `document.body` 整页无数字** —— 知识库页
   不进那个断言，但**别把带数字的东西带进外壳**。
3. **`.gitignore` 的 `data/` 无前导斜杠**（spec 025 §7.1）—— 新目录别叫 `data`。
