# spec 025 · 任务

> ✅ = 完成并被门禁覆盖 · ⚠️ = 完成但**未验证** · ⬜ = **未做**

## 已做

| # | 任务 | 验证方式 |
|---|---|---|
| 1 | 本地参考项目调查 | 记录在 spec §1.1 |
| 2 | 两份规范逐条裁定，写 `docs/FRONTEND_STYLE_GUIDE.md` | 人工评审（**V-03 / V-08 仍需人工**） |
| 3 | 4 个依赖安装 + 宪法 §3.2.1 记录批准 | ✅ V-07 断言 `package.json` |
| 4 | `lib/cn.ts` | ✅ 编译 + 单测 |
| 5 | `styles/globals.css` 令牌扩充 | ✅ V-05 / V-06 / 红涨绿跌 |
| 6 | `components/ui/` 7 个底座 | ✅ 编译 + 渲染 |
| 7 | `components/data/DataTable.tsx` | ✅ 渲染 + 今日页 E2E 间接覆盖 |
| 8 | `components/nav/CommandPalette.tsx`（⌘K） | ⚠️ **手动验证过，无 E2E 断言** |
| 9 | `app/AppShellFrame.tsx` 三栏 | ✅ `nav.spec.ts` / `routing.spec.ts` |
| 10 | `TodayPage` 迁移到应用语汇 | ✅ `today.spec.ts` / `today-hub.spec.ts` |
| 11 | V-01~V-08 变测试 | ✅ **9/9 变异全抓** |

## ⬜ 未做（**下一轮的入口，按"最实战"排序**）

| # | 任务 | 为什么它排在前面 |
|---|---|---|
| 1 | ⭐ **另外四页迁移到应用语汇** | 今天的壳已经立住，剩下四页是同一套改法，**收益最大、风险最低** |
| 2 | ⭐ **把 `detail` 槽位用上**（列表/详情真正分栏） | 槽位已存在但**无人使用**；分栏是知识程序与任务列表的分界 |
| 3 | **Lucide 图标真正用上** | **已批准已安装，一个都没用**；规范 §5 全部未落地 |
| 4 | **`BacklinkList` / `RecordTimeline`** | append-only 数据**一条都没渲染**；这是"知识库像知识库"的地方 |
| 5 | **补 E2E 覆盖 ⌘K** | 目前只有手动验证，**未被测试钉住** |
| 6 | 剩余 5 个组件（Drawer / Popover / Select / Toast / DatePicker） | 规范 §4.3 清单未完成 |
| 7 | j/k 列表导航 | 规范 §8.2 |
| 8 | ⭐ **加一条静态检查 S-14：「每个源文件都被 git 跟踪」** | 本轮 `DataTable.tsx` 被 `.gitignore` 的 `data/` 静默排除，而**门禁 10/10 全绿**（spec §7.1）。这个视角**没有任何现有检查覆盖**，而它一失败，别人 clone 就是编译不过 |
