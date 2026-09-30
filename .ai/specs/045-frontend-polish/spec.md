# spec 045 · 前端打磨：排版分层、图标、append-only 流水、缺的四项浮层

> 日期：2026-09-30 · 状态：进行中
> 依据：`docs/FRONTEND_STYLE_GUIDE.md`（v1.0，2026-09-28 主人批准）
> 主人在 2026-09-30 选定本轮四项范围，并裁定 **不加动画库**（见 §一·1）

---

## 一、主人裁定与它带来的约束

### 1. ⭐ 动画库：不装，铺开 L1/L2

主人要求「动画库、动效库再好好打磨」，而 `FRONTEND_STYLE_GUIDE.md` 三处明文禁止：

| 位置 | 原文 |
|---|---|
| §6 依赖预算 | **明确不装**：… · **auto-animate / motion / GSAP** · 图表库 · 自托管字体包 |
| §0.1 冲突裁定 | 入场动画 —— 姊妹项目用 `fade-slide 0.18s`；**裁定：采纳本项目，本产品零入场动画** |
| §7.2 六条禁令 | 入场动画（stagger / fade-in-up）· 骨架屏 shimmer · **数字滚动 count-up** · 弹跳/过冲 · 视差/粒子 · 图表入场 |

⭐ 补一条**当时没被写下的实情**：`styleguide.test.ts` **V-06 已经禁止 `@keyframes`（任何 CSS 文件里）与
`animate-*` / `duration-\d`（任何组件里）**。所以「装个动画库」会同时撞上 V-06 与 V-07 两条
**会被门禁抓住**的验收项。

⭐ 主人的裁定（2026-09-30）：**不加库，铺开 L1/L2**。本 spec 的阶段 A 因此只做
**用现有 tailwind + 一段 CSS 实现 §7.1 的两级时长**，零新依赖。

### 2. 本轮四项范围（主人勾选全部四项，按此顺序）

| 阶段 | 内容 |
|---|---|
| **A** | 17px+ 衬线主张与字号分层（+ L1/L2 动效铺开） |
| **B** | Lucide 图标体系 |
| **C** | RecordTimeline + BacklinkList |
| **D** | 补齐 Drawer / Popover / Toast / DatePicker |

---

## 二、现状（2026-09-30 实测，非推断）

| 规格 | 实测 | 差距 |
|---|---|---|
| §8.1 八个底座组件 | 8/8 ✅ | — |
| `DataTable` / `CommandPalette` | 11 / 3 处引用 ✅ | — |
| `.serif` 分工 | 25 处 ✅ | — |
| §2.2 字号分配 | **`text-[17px]` 全项目 1 处**；`text-[11px]`+`text-[12px]`+`text-[13px]` **255 处** | ⭐ **主张排版基本不存在** |
| §5 Lucide 图标 | 产品代码 **0 处**（`lucide-react` 只出现在 `styleguide.test.ts` 的依赖白名单里） | ⭐ **装了 0 用** |
| §3.3 自绘金融图标 | **0 个 `<svg>`** | — |
| §8.2 `RecordTimeline` | 组件 **0**；`cards_repo.list_events()` **已存在但零调用者**；`GET /cards/{id}/events` **不存在** | ⭐ **⚠️ 这行原来是错的，见下** |
| §8.2 `BacklinkList` | 组件 **0**；`notes.backlinks_for()` **已存在但零调用者**（`notes.py:517`）；`GET /notes/{id}/backlinks` **不存在** | ⭐ 数据在库里、屏幕上没有 |
| Drawer / Popover / Toast / DatePicker | **0 / 0 / 0 / 0** | — |
| §7.1 动效 | `[data-motion='l1']`/`'l2'` 类已定义；**组件里 `data-motion` 用得极少**；`l2` 写的是 `transition: all` | ⭐ L2 无处可用，`all` 也不对 |

⭐ 三个「零」不是「没做」，是**做了一半**：`list_events` 与 `backlinks_for` 都在仓库里躺着，
没有端点也没有组件。这正是 `FRONTEND_STYLE_GUIDE.md` §0 自己写的病——「规范没被实现」——
的第二次复发。

---

## 三、阶段 A · 排版分层与动效

### A.1 字号成为一类东西，而不是 255 次手写

⭐ **问题的形状**：`FRONTEND_STYLE_GUIDE.md` §2.2 是一张裁定过的表，而项目里有 255 处
`text-[11px]` / `text-[12px]` / `text-[13px]`。一条被违反 255 次的规则不是规则。

⭐ **做法**：把 §2.2 的表变成 `globals.css` 里的**排版类**（一个家），并加一条**门禁可抓的**
断言：**组件里不得出现裸 `text-[Npx]`**。

| 类 | 规格（§2.2） | 允许 11/12px |
|---|---|---|
| `.type-page-title` | 22 / 30，衬线 | — |
| `.type-claim` | 17 / 24，衬线 | — |
| `.type-claim-lg` | 26 / 34，衬线 | — |
| `.type-prose` | 13 / 20，无衬线 | ⛔ |
| `.type-cell` | 13 / 18，无衬线 | — |
| `.type-meta` | 12 / 16，全大写 `letter-spacing: 0.06em` | ✅ |
| `.type-badge` | 11 / 14 | ✅ |

⭐ **为什么禁裸 `text-[Npx]` 而不是禁 `text-[11px]`**：grep 不知道一段 11px 的字是表格表头
还是散文。禁「手写字号」把判断从每次评审移到**一次**（写这个类时），这才是能机械化的那条。
⭐ 代价要说清楚：**这是本轮最大的机械改动**（约 255 处 × 若干文件），每一个类名的语义都要人工分一次。

### A.2 主张真的变大

⭐ 「有 `.serif` 类」和「有主张」是两件事。规格要的是 **17px 以上衬线**承载卡片主张、
象限判语、决策理由。阶段 A 必须让这四类文本在成品里**肉眼可辨地**更大、更衬线，
而不仅仅是「类名换对了」。

⭐ **未验证**：这一条只能靠截图人工评审（V-03 本身就是人工项），我用截图自查，但
**没有机械判据**证明「主张足够大」。诚实标注。

### A.3 L1/L2 落地

| | 现状 | 本阶段 |
|---|---|---|
| L1 | `data-motion='l1'` 只在 8 个底座组件里 | 铺到**表格行、链接、列表行、nav 项** |
| L2 | `transition: all 200ms` 且**零使用** | 改成**具名属性**（不许 `all`），留给阶段 D 的 Drawer |
| reduced-motion | 已有 `@media (prefers-reduced-motion)` | 保留并加测试覆盖 |
| 非法时长 | **无任何检查** | ⭐ 加断言：**任何 `transition`/`transition-duration` 的时长必须在 100–120ms 或 180–220ms 之间** |

⭐ V-06 只**禁**，不**管**。§7.1 给了精确区间却没人检查，于是 `transition: all 4s` 今天能过门禁。
新增的 `V-09` 管这一条。

---

## 四、阶段 B · Lucide 图标体系

- `components/ui/Icon.tsx`：`<Icon name="…" size="sm|md|lg" />`，**调用点不许直接 import
  `lucide-react`**——用一张具名注册表，理由是可审计与可测试。
- 三档 stroke-width（§5）：`sm` 1.5（<14px）/ `md` 1.25（16–20px，默认）/ `lg` 1（≥24px）。
- 只用 `currentColor`；⛔ 禁 emoji 作功能图标（这条**可 grep**，见下）。
- §3.3 自绘金融图标（三表/估值/决策/复盘/知识）——**只此一份 SVG sprite**，24×24、
  `stroke-width: 1.5`、圆角线帽。涨跌 ▲▼ **已经存在**（1 处），保持自绘、不换成图标库箭头。

⭐ 新增 `V-10`：**产品源码里不得出现 emoji**（一个正则覆盖常用区段）。
⭐ 新增 `V-11`：**注册表里不得有零使用的图标**（防止注册表变成图标仓库）。

---

## 五、阶段 C · RecordTimeline + BacklinkList

### C.1 组件是通用的，**适配器按页分**

⭐ 七张 append-only 表（`card_events` / `card_reviews` / `reviews` / `note_reviews` /
`note_schedule` / `lesson_*` / `audit_log`）形状各不相同。做一个「后端把所有表 union 起来」的
端点等于**新造一层抽象，它自己需要一份 spec**。

⭐ 所以：`RecordTimeline` 收**已归一的 `TimelineEvent[]`**，**每个页面自己适配**。
通用组件一份，映射函数按页一份。这是本阶段最重要的一个取舍。

### C.2 一个端点（不是两个）—— ⚠️ 本节在调研后被推翻

⭐ **下面这张表的第一行原本是错的，而它是这张表的全部依据。**

| 端点 | 背后已有 | 调研后的实际状态 |
|---|---|---|
| ~~`GET /cards/{id}/events`~~ | ~~`list_events()` 零调用者 ⇒ 需要新端点~~ | ⭐ **不需要**。`card_events` **早就在接口上了**，走的是私有 `_load_events()` → `CardRow.events` → `CardRead.events`（`routes/cards.py:156-162` 的 `events` 字段 + `to_read` 的 `:188-196`），⭐ **而前端已经在渲染它**（`CardSection.tsx:379-393`）。API 测试也钉死了（`test_cards_api.py:365`）。「零调用者」是真的，但**零调用者不等于数据没上线** —— `list_events()` 只是那条已通路径的私有版本 `_load_events()` 的公开镜像 |
| `GET /notes/{id}/backlinks` | `notes.backlinks_for()` | ⭐ 函数存在、**零调用者**、**无端点**、**前端零渲染** —— 这一个是真的缺口 |

⭐ **「函数零调用者」与「这个能力不存在」是两回事**，而我把前者当成了后者。
判据应该是**数据有没有出现在响应体与屏幕上**，不是有没有一个公开函数被调。

⭐ **C.1 的组件设计随之要改**：`RecordTimeline` **不是「把 card_events 首次画出来」**，
而是**把已经画出来的那段 ad-hoc `<ul>` 变成通用组件，并让另外六张 append-only 表复用它**
（`card_reviews` · `reviews` · `note_reviews` · `note_schedule` · `lesson_*` · `audit_log`）。
⇒ **C 的真实缺口是「通用组件 + 其余表的适配器」，不是「一个端点」。**

⭐ 顺带确认的三条**会写错代码**的事实（子 agent 逐行核过）：

- **`backlinks_for` 返回 `list[str]`（裸 note id），不是行对象**。⭐ `test_notes.py:501` 的注释
  记着上一版曾断言成 `[row.note.id …]` —— **那是写路径的形状**。直接返回 id 是对的
  （前端要的是「有哪些笔记指向它」，标题要自己去取），但**它意味着端点要决定要不要补标题**。
- **`ORDER BY from_note_id` 是按 id 字符串排序**，而 id 形如 `note_<millis>` ⇒ 字典序≈时间序，
  **仅在毫秒位数相同时成立**。跨位数（比如 999ms → 1000ms）就不成立了。
- **`NOTE_NOT_FOUND` 不在 `errors.py` 的 `_STATUS_BY_CODE` 里** ⇒ 若不显式 `try/except`，
  路由会返回 **400 而不是 404**。`notes.py:281-287` 那个 `try/except` 是承重的，不是样板。

---

## 六、阶段 D · Drawer / Popover / Toast / DatePicker

手写，`aria-*` + 焦点陷阱，**不引 Radix**（§6 的理由：shadcn 的模式就是
`cva` + `clsx` + `tailwind-merge` 手写，需要无障碍就自己写）。

⭐ **明确不做**：不引 `@radix-ui/*`、不引任何浮层库。浮层出 `box-shadow` 由 V-01 直接抓住。

---

## 七、明确不做（与「打磨」无关的事）

| 不做 | 为什么 |
|---|---|
| ⭐ **把文件搬进 guide §9 的目录结构** | §9 要求 `app/` / `hooks/` / `lib/`，而实际是 `useResource.ts`、`api.ts`、`cn.ts`、`format.ts` 与全部页面都在 `src/` 根。**搬它要动 30 个文件和它们全部的 import 与测试，视觉收益为零。** 这是真实差距，记在这里而不是偷偷不做 |
| 改 A 股红涨绿跌 | §2.3，且 V-05 已在守 |
| 任何 `@keyframes` | V-06 / §7.2 |
| 「README / 演示模式 / 引导」 | 与规格无关 |
| 把 `gsap`/`motion` 加进 `devDependencies` | 主人已裁定不加；V-07 会红 |

---

## 八、新增验收项（会进 `styleguide.test.ts`）

| # | 项 | 判据 | 阶段 |
|---|---|---|---|
| **V-09** | 动效时长合规 | 任何 `transition*` 的时长 ∈ {100–120, 180–220}ms；无 `transition: all`；`prefers-reduced-motion` 在场；⭐ 另有防空洞守卫 | A |
| **V-12** | 字号只有一个家 | 产品源码无裸 `text-[Npx]`；八个类按 §2.2 的数字逐个钉住；**且必须是 `@utility` 而非裸类**；每个类的使用次数落在区间内；`.caps` 无手搓写法 | A |
| **V-10** | 无 emoji 功能图标 | 产品源码 grep | B |
| **V-11** | 图标注册表无死项 | 注册表每项至少被引用一次 | B |
| **V-13** | 主张字号与字面 | **页面级**断言：六个「欠读者一个主张」的页面各至少一处 `.type-claim*`，且各至少触及一次 `.serif` | A |

⭐ V-13 是**弱判据**：它只能证明「该有主张的页面有主张类」，证不了「主张足够大」。
⭐ 而它的**强处**是 V-09/V-12 都给不了的：**那两条检查「用了就对了」，V-13 检查「该用的时候用了」**——
`TodayPage` 的判据句（全产品最大的一句，spec 040 的全部产出）在 A6 之前一直是 `.type-prose`，
**V-09 与 V-12 都不会红**。⇒ 这正是它存在的理由，不是凑数。

⭐ **`PoolPage` 被有意排除**（理由写在测试注释里）：**关注池是一个列表**，规则 6 的密度豁免
正是让列表成为列表的东西。把二十个代码变成二十个主张，就是这份规范花十节防的那件事。

---

## 九、调研结论（2026-09-30，查过业界做法后改了三处设计）

⭐ 这一节记的是**查完之后改变了什么**。只记「我查了什么」而不记「所以改了哪个字」的调研，
过三个月就只剩一句「当时参考了 Tailwind 文档」，等于没查。

| 来源 | 结论 | 对本 spec 的影响 |
|---|---|---|
| **Tailwind v4 官方文档** · Adding custom styles | 自定义工具类的机制是 `@utility`，不是裸 `.class` | ⭐ **A1 改了**：八个排版类从裸类改成 `@utility`。换来两件事——① `md:type-prose` 这类 **variants** 可用，裸类一个都没有；② 注册工具类在 **utilities 层**内，而裸类写在 `@import` 之后 = **不在任何层里**，同优先级下压过整个 utilities 层，正是迁移里反复撞到的顺序陷阱。⭐ 而且它**把测试也逼对了**：原来 `\.type-prose\s*\{` 也能被裸类满足，断言比它声称的弱 |
| **lucide-react 官方性能建议 + 实测 `package.json`** | `sideEffects: false` + `dist/esm/icons` 有 4236 个文件 | ⭐ **B 的设计被确认而非修改**：具名注册表 = 一次 barrel + 静态可分析的具名导入，比「每处调用点各 import」**更优**（一个模块、静态可摇树）。附带的硬指标见下 |
| **WAI-ARIA APG · Dialog (Modal) Pattern**（W3C） | `role="dialog"` + `aria-modal`；Tab 在框内循环；**Escape 关闭**；关闭后焦点回到**触发元素**，元素已消失则退到一个「提供合理工作流」的元素，**明确排除 `document.body` 与页首**；`tabindex="-1"` + 初始焦点是最广泛支持的做法；原生 `<dialog>` + `showModal()` 一次给到 top layer、inert、Escape | ⭐ **D 的实现方向定了**：优先用原生 `<dialog>.showModal()` 而不是 div + 手写焦点陷阱——§6 禁的是 Radix 这类**库**，`<dialog>` 是平台。⭐ 而本仓已有 `CommandPalette` 手搓过一遍遮罩与焦点，**D 必须先读它**，别造第二个家 |

### 9.1 附带量到的两条

- ⭐ **JS 包 514.63 kB / gzip 158.01 kB，Vite 已警告超 500 kB**（主要是 spec 034 的 `lightweight-charts` 与 `@milkdown/*`）。⇒ **B 有一条硬验收：加入图标后包体不得变大**。「装了 0 用」变成「用了并且不许拖慢」是一个更可测的目标。
- ⭐ **`@milkdown/*` 装了但未接进 vault 页**（`styleguide.test.ts` V-07 的注释里已记）。⭐ 它是包体偏大的原因之一。本 spec 不动它（超出范围），但记在这里：**S5 打包实测时它会被算进去**。

### 9.2 查完之后**没有**改的

- ⭐ **不加 `motion` / `GSAP`**：主人 2026-09-30 已裁定，且 §6 / §7.2 / V-06 / V-07 四处都禁。调研只是复核了「CSS transition + `@starting-style` 足够实现 L1/L2」，不构成加库的理由。
- ⭐ **不搬目录结构**（§9 的 `app/` `hooks/` `lib/`）：调研没有改变这一点，见 §七。

---

## 十、诚实边界

- ⭐ **V-03（衬线只出现在主张）与 V-08（空状态）仍是人工评审项**，`styleguide.test.ts`
  的文件头已经写明理由。本 spec **不**试图用 grep 假装解决它们。
- ⭐ 阶段 A 的 255 处改动**以门禁 + 120 单测 + 89 E2E 全绿为通过标准**，但
  「更好看」这件事**没有任何自动化判据**，只有截图。
- ⭐ 阶段 B 的 `lucide-react` v1.48 的导出名**未逐一核对**——写 `Icon.tsx` 时以
  `node_modules/lucide-react` 的实际导出为准，核不出来就记进变更日志的「未验证」。