# spec 026 · 计划

## 执行顺序（后端先，它是承重的）

| # | 步骤 | 为什么在这个位置 |
|---|---|---|
| 1 | 迁移 `0007` + 登记 manifest | schema 先定，否则 domain 无处落地 |
| 2 | `domain/note.py` | 规则与错误码在这里，和 `domain/card.py` 同构 |
| 3 | `storage/repositories/notes.py` | 事务边界在这里 |
| 4 | pytest：domain + 仓储 + 迁移 | **先测后接线** |
| 5 | `api/routes/notes.py` | HTTP 面 |
| 6 | pytest：API | |
| 7 | 前端 `api.ts` 类型与调用 | |
| 8 | `routing.ts` 加 `vault` | 路由表是唯一真源（spec 022） |
| 9 | Milkdown 编辑器组件 | 主人本轮批准 |
| 10 | `VaultPage` —— **卡片与笔记并列** | |
| 11 | 接入三栏外壳 + 导航 | 导航**零数字**（`nav.spec.ts` 钉死） |
| 12 | 变异检查 + 门禁 + 台账 | |

## ⭐ 三条容易踩的，已预置

1. **导航不能挂计数** —— `nav.spec.ts` 断言导航内**无任何数字**。
2. **`retrospective.spec.ts` 断言危险象限下 `document.body` 整页无数字** ——
   新页面若进入外壳，**它渲染的任何数字都在那个爆炸半径里**。
3. **`.gitignore` 的 `data/` 无前导斜杠**（spec 025 §7.1）——
   新目录若叫 `data` 会被静默排除。**本轮不建 `data` 目录。**
