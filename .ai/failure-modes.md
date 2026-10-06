# 失败模式清单

| F-165 | ⭐ **A regex cannot tell code from prose, and I got that wrong **three times in one hour**** | `V-15` asserted against the **raw** source three separate ways and each was defeated by a comment rather than by a mutant: ⭐ the delegation check `/useModalFocus\(\{[^}]*open[^}]*panelRef[^}]*\}\)/` was satisfied by `// useModalFocus({ open, panelRef })` (commenting out the call, the most likely way a refactor gets silently undone); ⭐ the same shape also matched `useModalFocus({ open: !open, panelRef })` — ⭐ an **inverted** flag, which type-checks because both are objects with the same keys; ⭐ and the `tabIndex={-1}` check was satisfied by the comment I had written *about* the `tabIndex={-1}` | ⭐ `styleguide.test.ts` already has `stripComments` for exactly this, ⭐ and the fix was to use it every time — the lesson is not 「remember the helper」 ⭐ but **「a source assertion must say whether it is reading code」** |
| F-166 | ⭐ **Green after a refactor is the weakest evidence a refactor was correct** | Moving the three modal behaviours into `useModalFocus` left all 12 palette E2E and 144 unit tests green. ⭐ That is not evidence: the failure mode of an extraction is **silent** — the copy compiles, the copy is installed, ⭐ and only a test that would have gone red catches it. ⭐ The mutants were aimed at the **seam** instead of the logic (the delegation, the argument shape, the effect deps), ⭐ and one of them was ⭐ **`useModalFocus({ open: !open, panelRef })`** ⭐ which is exactly the mistake a person makes while moving code around and which `tsc` cannot see |
| F-167 | ⭐ **`focus()` on an element with no `tabindex` is a silent no-op, and the mutation was the only way to see it** | `useModalFocus`'s empty-panel branch calls `panel.focus()`, and the palette's panel is a `div` with no `tabindex`. ⭐ A query with no matches leaves the panel with **one** focusable thing (the input) and the branch fires, ⭐ and `focus()` on a non-focusable element does nothing at all — ⭐ the reader is left on the page behind with the panel still open and **nothing looks wrong**. Found by the mutant 「the panel loses `tabIndex`」 surviving, not by reading. Fix: `tabIndex={-1}`, ⭐ which is focusable programmatically without joining the tab order. ⭐ And the E2E trap test only ever walked a **populated** panel, ⭐ so it could not have caught this either |
| F-168 | ⭐ **A verification that cannot be run is not a verification, and I wrote one** | The `useModalFocus` extraction script ended with `for gone in ('trapFocus', 'previousFocus', …): if gone in after: fail`. ⭐ It rejected the file because the **new comment** says 「this used to be three effects and a `trapFocus`」 — ⭐ and that sentence is the only thing stopping somebody putting the three effects back. ⭐ The reflex would have been to delete the comment; ⭐ instead the check learned to look for **code** (`trapFocus(`, `.inert =`) rather than the word. ⭐ Same class as `F-165`, and the cost of getting it wrong is a verification that deletes the evidence |
| F-169 | ⭐ **The survey that changes the plan is the one worth doing before the code** | Stage D's four items were surveyed before building: ⭐ **`Drawer` and `Popover` do not exist at all** (only `CommandPalette` is a floating layer) ⭐ **`DatePicker` is already native in both places** and §4.3 says 「不要做复杂控件」, ⭐ and the use it specifies — a **range** — has no caller ⭐ **`Toast` has 16 call sites and all 16 are `setError`**, ⭐ so there is no success feedback anywhere for a 「操作反馈」 toast to report. ⭐ `Select/Combobox` is in the same table and also has no caller. ⭐ Building four components against that is `F-149` again ⭐ — 「the library has it」 is not 「the product uses it」 — and the plan for the next step should start from the survey, not from the list of component names |

| F-158 | ⭐ **A rule that checks a **prefix** of a value is not checking the value** | `V-15` asserted `/createPortal\([\s\S]*?document\.body/` and the mutant `document.body.firstElementChild` **survived** — ⭐ the portal target being the shell's own first child, which puts the panel straight back inside the subtree it disables, is a prefix match of the pattern | ⭐ The two directions are both real: `F-148`/`F-153` are me being too **wide**, this is too **narrow** in the sense of not ending where the value ends. ⭐ Fix: `document\.body\s*[,)]` | ⭐ A pattern that does not say where the value **stops** will accept every longer value that starts the same way, and the mutation report is the only thing that finds out |
| F-159 | ⭐ **The compiler rejecting a malformed mutant is filed as a mutant that survived** | Two of five focus mutants reported `BUILD FAILED`: one injected `if (true) return`, which makes the rest of the callback unreachable, and one deleted the `trapFocus(event)` call, which leaves the function unreferenced. ⭐ `npm run build` is `tsc -b && vite build`, so **both were rejected before they could teach anything** — and the script printed `BUILD FAILED`, ⭐ which reads exactly like 「the mutant broke the build」 | ⭐ **A mutant must be type-clean, not just behaviour-changing.** Both were rewritten (`previousFocus.current = null`; `stops.length >= 0`) so only behaviour moves. ⭐ And the harness must print `error.message` as well as `error.stderr`, ⭐ because with `shell: true` on Windows `cmd.exe` does not pass stderr through the pipe and the first run showed an empty stderr with status 2 — ⭐ **a probe that cannot say why it failed files the failure under the wrong cause** |
| F-160 | ⭐ **`stdio: 'ignore'` made a successful build report a non-zero status** | The focus mutation harness ran `execFileSync('npm.cmd', ['run','build'], { stdio: 'ignore', shell: true })` and got **status 2 for a build that had succeeded** — ⭐ so the first run reported all five mutants as `BUILD FAILED`. `stdio: ['ignore','ignore','pipe']` returns 0 on the same build | ⭐ Not a rule about mutants at all; a rule about the harness. ⭐ **The gate and a probe must invoke the toolchain the same way**, ⭐ and here they did not: the gate calls `npm.cmd` with a redirected file, the probe called `npm` (which resolves to `npm.ps1` and is refused by this machine's execution policy) ⭐ and then discarded the output streams. ⭐ A harness that reports a different environment's failure as a result about the code is worse than no harness |
| F-161 | ⭐ **The obvious reading of a defect was the reading that hid it** | `CommandPalette` declared `role="dialog"` + `aria-modal="true"`, and Tab forwards stayed inside the panel for **five** presses while backwards left on the **one**. ⭐ The reading that makes this harmless is 「the panel is last in the DOM so forward Tab is naturally safe」 — and it is **true-looking and wrong about the cause**: the panel is portalled, ⭐ so forward Tab had to cross the whole page first, ⭐ and those five safe steps were the browser's own order, not a trap. ⭐ **A defect that hides behind a correct-looking explanation is the expensive kind** | ⭐ Probe before reasoning, and ⭐ press **more keys than there are rows** in both directions ⭐ — `rows` presses pass against a missing trap, since the pre-fix escape took exactly `rows + 1` |
| F-162 | ⭐ **A locator that matches nothing fails as a timeout, which is a bad way to learn a name** | `palette.spec.ts`'s focus test used `getByTestId('nav-市场')`. ⭐ The shell's testid is `nav-${entry.label}`, so the shape was right and the view was wrong, ⭐ and Playwright reported it as a bare 30s `locator.focus` timeout with no assertion output at all. A second attempt used `nav-${ROUTES[0].name}`, which is wrong in the other direction (`name` vs `label`) ⭐ and produced the same silence | ⭐ **No output means the locator matched nothing** — not that the product is slow. ⭐ And the value is now derived from `ROUTES[0].label`, ⭐ which is the third dead constant this file has now had and the reason it already had a paragraph about deriving them |
| F-163 | ⭐ **I concluded a fix worked by arguing about it, and the argument was the wrong shape** | After adding the focus trap and `inert`, the next step considered was to move `CommandPalette`'s call site from `AppShellFrame` into `App` so the panel would be a sibling of the shell. ⭐ `createPortal(node, document.body)` already makes the node a **sibling of `#root`**, so the move would have changed nothing — ⭐ and the DOM order, measured afterwards (`panelParentIsBody: "body"`, `panelInsideShell: false`), is what says so | ⭐ **Where a portal *lands* is decided by its argument, not by where it was written.** ⭐ A refactor that reads as necessary because the mental model was missing a DOM fact is a refactor that adds a prop and moves a responsibility for no behavioural gain |
| F-164 | ⭐ **The trap's own first working shape was invisible because it was in the wrong place** | The obvious place for a focus trap is a `window`/`document` keydown listener. ⭐ The first version was going there, and it would have fixed the backward case while leaving the forward case broken — ⭐ because a `keydown` on the focused element is already handled before it bubbles past React's root listener, ⭐ so a `Tab` pressed on the input never reaches it. ⭐ The handler therefore lives on the panel's own `onKeyDown`, and the mutation 「remove the trap call entirely」 is kept in the suite specifically to catch a future refactor back to the plausible-but-wrong shape | ⭐ **The mutation that matters is often the one aimed at the fix you nearly wrote.** ⭐ The forward walk needs `rows + 1` presses to expose it, ⭐ and a shorter walk passes against the broken version |

> **本清单只增不改。** 每条记录一种"会误导人的思路"，**给 agent 自查用**。
> **命名失败模式比"要仔细"有用得多 —— 因为它可自查。**
> 建立：2026-09-26 · 依据 `references/deep-dives/06-mem0.md` 决定 12 · `10-akshare.md` · `04-langfuse.md`

---

## 一、为什么要有这个文件

三类"缺陷固化"载体中，本文件回答的是：**"某种思路会误导人"**。

| 载体 | 回答的问题 |
|---|---|
| `spec.md` 的 `## 已知的失败` | **验收时该检查什么** |
| **本文件** | ⭐ **某种思路会误导人** |
| `.ai/regressions/` | **运行时行为错了** |
| `.ai/checks/static/` | **某段代码不该存在** |

**"要仔细"不是一条可执行的规则；"首因支配"是一条可自查的规则。**

---

## 二、取数类（`DATA_SOURCE_*`）

| # | 失败模式 | 表现 | 自查问法 |
|---|---|---|---|
| F-01 | **猜函数名 / 猜端点** | 凭印象调用一个不存在的接口 | "我**见过**这个端点返回数据吗？还是我**推断**它存在？" |
| F-02 | **假设列名** | 拿到返回后按自己想象的字段名取值 | "我**打印过**返回结构吗？" |
| F-03 | **假设单位** | 把百分比当小数、把元当万元 | "这个字段的单位**写在哪里**？" |
| F-04 | **假设数据是新的** | 用缓存/僵尸数据当当日数据 | "这条数据的**采集时间戳**是多少？" |
| F-05 | ⭐ **把"确实没有"当成"接口坏了"**（或反之） | 返回空表 → 报系统故障；或抛错 → 显示"无数据" | "这是**业务结果**还是**系统故障**？" |
| F-06 | ⭐ **把"接口坏了"当成"确实没有"** | 见上，方向相反，**更危险** | 同上 |
| F-07 | **连续失败变轰炸** | 失败后立即重试，触发封禁 | "失败有没有**计入限流时间戳**？" |
| F-08 | **403 后重试** | 风控信号被当成网络抖动 | "这个错误码**允许重试**吗？" |
| F-09 | **静默降级** | 备胎数据不完整但不标记 | "降级**用户能看到**吗？" |
| F-10 | **用当前快照当历史数据** | 前视偏差 | "这个数据**有时点**吗？" |
| F-11 | **`re.search` 捞 6 位数字** | 从 `SH000001.SZ` 里捞出 `000001` | "我的正则是**整串锚定**吗？" |
| F-12 | **从代码推断市场** | 用 `000001` 猜出市场 | "市场是**输入/返回**的，还是我**推断**的？" |
| F-151 | ⭐ **A guard written from an assumption instead of a measurement** | `GET /notes/{id}/backlinks` first version carried `if row is not None` with a comment explaining that a backlink to a deleted note is skipped. ⭐ The comment was wrong on both halves: `note_links.from_note_id` **cascades**, so deleting the note removes the link row first; and `get_by_id` **raises** rather than returning `None`, so the guard could never be reached | ⭐ **The mutation check is what found it** — removing the guard left the suite green, which I first read as a hole in the rule and only then as a fact about the code. ⭐ A probe that measures (`probe_delete.py`) answered in one run: before the delete `[source]`, after `[]`; `get_by_id` RAISED | ⭐ **Never write a defensive branch before checking whether the case exists.** A guard that cannot be reached survives review, reads as diligence, ⭐ and the protection it appears to offer was never there — this is the same shape as `EVENT_LABEL` deleted an hour earlier for the same reason |
| F-152 | ⭐ **A test that never asserts its own setup did anything** | The deleted-note test did `DELETE FROM notes WHERE id = ?` and then asserted the list was empty. ⭐ Nothing asserted that the delete matched a row, so when the behaviour it claimed to test turned out not to exist (F-151), the test **stayed green** | ⭐ A setup that can quietly do nothing produces a test that cannot fail, ⭐ **and it looks exactly like a test that passed**. The replacement asserts `note_links` has zero rows for that id, so a broken cascade now fails the test that is about it | ⭐ **Ask what the setup would have to do for this test to still pass with the feature removed.** If the answer is 「nothing」, the setup is not being exercised |
| F-153 | ⭐ **I widened the rule, again, and this time the false positive was on the correct code** | `V-14`'s first regex was `\.(events|history)\s*\.\s*(map\|length\s*>\s*0\s*&&)`, and it reported `CardSection.tsx:395` — ⭐ `{card.events.length > 0 && <CardTimeline events={card.events} />}`, which is the **correct** delegation, in the file that delegates | ⭐ A rule written as 「do not touch this field」 catches the guard that makes the good case good. ⭐ **A rule about a shape must be written against the shape it forbids** — here 「mapping the array into JSX yourself」, not 「naming the array in a page」 | ⭐ This is `F-148` for the **third** time in three commits, which is a habit and not an accident. ⭐ The tell is the same each time: a rule that a lot of correct code violates on first run |
| F-154 | ⭐ **A filter that can match zero files makes a count assertion report a false cause** | `V-14`'s adapter-count test filtered `FILES` on `'/components/data/'` and got **0 files** — ⭐ `FILES` holds raw platform paths and only `RELATIVE()` normalises them, so on Windows every path is `components\data\`. The test then asserted `toBe(2)` against nothing and printed 「found 0」, ⭐ which reads as 「somebody deleted both adapters」 | The real cause was 「the filter never matched a file」. ⭐ Neither `/` nor `\` may be assumed; `RELATIVE` exists in this file precisely because this is a known trap | ⭐ **A test that fails with a count is a claim about the world. Before believing it, prove the filter matched something** — ⭐ otherwise the message teaches the next reader a thing that is not true |
| F-155 | ⭐ **`toContain('identifier')` tests that a word exists, not that it is wired up** | V-14's third test asserted the source of `RecordTimeline` contains the string `absentDetail` and the suite was green. ⭐ The word appears in the props interface, the destructuring, the default and the JSDoc — ⭐ **five mentions** — and the mutation that replaced the render site `{absentDetail}` with `{''}` left all five intact, so the component would have rendered an empty second line and the test would not have noticed | ⭐ The assertion is now on the **render expression** (`{absentDetail}</p>`), because that is the thing that can be wrong | ⭐ Also worth recording: **this repository cannot render a component in a test** — no `jsdom`, no `@testing-library/react`, all ten test files are pure logic or source scans — ⭐ so 「wiring」 is the honest ceiling here, and adding a DOM environment is a dependency-budget decision (V-07) that has not been made |
| F-156 | ⭐ **A mutation to a comment is not a mutation** | The V-14 probe's fourth mutant appended `DISABLED` to the comment above the absence branch. ⭐ That changed no behaviour, the suite stayed green, and the script printed 「SURVIVED: V-14 does not catch a broken timeline」 — ⭐ which was **false in the strongest possible sense**: the probe had done nothing at all | ⭐ The replacement replaces `{absentDetail}</p>` with `{''}</p>`, and the script now distinguishes **NOT APPLIED**, **SURVIVED** and **wrong reason** on output | ⭐ This is `F-150` for the **fourth** time, from a new direction: ⭐ before, the mutant satisfied the rule; now, the mutant did not violate anything. ⭐ **A mutant must change what the code does** — and the surviving-mutant line in a report is only as trustworthy as that |
| F-157 | ⭐ **One custom failure message per assertion, or the probe reports a kill as a false cause** | The probe expected the failing test's name to appear in the output (`appearing_in_its_backlinks`), and got 「wrong reason」. ⭐ The mutation **had** killed the suite — ⭐ `pytest -q` prints a failing count and not the test ids, so a name lookup can never match. The backend round hit this and the V-14 round hit it again, ⭐ this time because only the first of two `expect`s in one test carried a custom message | ⭐ **Assert the message you wrote, per assertion.** A `pytest`/`vitest` failure line contains the runner's own text, and a probe that greps for something the runner does not print will call every kill a false cause | ⭐ Identical to the anchor lesson in stage A: **「假设要改的地方」和「实际改的地方」要能互相找到**, ⭐ here between the assertion and the probe that reads it |

---

## 三、数据契约类（`CONTRACT_*`）

| # | 失败模式 | 表现 | 自查问法 |
|---|---|---|---|
| F-20 | **启发式单位转换** | `if value < 1: value *= 100` | "我是不是在**猜单位**？" |
| F-21 | **一个字段编码两件事** | 用正负号同时表达数值与单位 | "这个字段**只表达一件事**吗？" |
| F-22 | **口径混用** | 图上画前复权、算收益用不复权 | "这个序列里**所有点**都是同一口径吗？" |
| F-23 | **缺币种的裸金额** | `amount: 1234.5` | "币种**在哪**？" |
| F-24 | **用自然日算"N 个交易日后"** | 交易日/自然日混用 | "我数的是**交易日**吗？" |
| F-25 | **用未来股本算历史换手率** | 股本口径错 | "股本公告日**不晚于**目标交易日吗？" |

---

## 四、状态与记录类

| # | 失败模式 | 表现 | 自查问法 |
|---|---|---|---|
| F-30 | ⭐ **用布尔跟踪状态** | `reviewed=false, scored=false, …` 组合出语义不明的状态 | "需要**几个**布尔描述同一对象？≥2 就是状态机" |
| F-31 | ⭐ **用"未成熟"填 0** | `result_score = 0` 表示"还没结果" | "0 是**真的 0**，还是**不知道**？" |
| F-32 | **从派生表推断状态** | "有 review 行 = 已复盘" | "状态**有没有独立真源**？" |
| F-33 | **把失败包装成收获** | "虽然亏了，但学到了…" | "`outcome` 允许 `failed` 吗？" |
| F-34 | **用组合条件推导语义** | `Manual + ease==0` = reset | "这个语义**需要长注释才能看懂**吗？" |
| F-35 | **修改历史记录** | UPDATE 决策记录 | "数据库**会不会拦住**我？（触发器）" |
| F-36 | ⭐ **靠人肉纪律维持"只增不改"** | 文档写了但没人拦 | "这条规则在**第几层**？（0.2）" |
| F-232 | ⭐⭐ **`status=ok` 且零错误码，同时少给了四年** | `?start=2015-01-01` 回 320 根（2025-06 起）、`status="ok"`、无 error —— 后端 `MAX_DAILY_WINDOW_DAYS` 夹一次、源再夹一次，**两次都没人记** | "**成功的那一次，凭什么说它给全了？**" —— 响应体里有没有**调用方要的那个东西**？（⭐ `KlineChart.tsx:372` 本来就画着交付区间 ⇒ **屏上早写着真相，只是没人问「那是我要的吗」**） |
| F-234 | ⭐⭐ **一个探针报告了客户端的缺陷，而 `tsc` 绿着** | 探针报 `Today` 缺 `due`，而 `TodayPage.tsx:91` 正在读 `today.data?.due` | 「**探针和编译器不一致时，先信哪个？**」 —— 编译器对。⇒ 不要去改客户端，要去查解析器。⇒ 本会话四次探针三次作废，**作废的三次全是我的解析器**：① 成员只在「本行括号净值为 0」时才算——`due: {` 既声明成员又开启嵌套；② `DECLARATION` 匹配不到 `type X = {`；③ 按行读成员——单行 `interface T { a: string }` 读出零个。⚠️ 三者在本仓**全部无影响**（76 个声明全是多行，零个单行），而 `no_enum_drift.py:194-196` 写着本仓对自己的要求：**「a rule that can be defeated by reformatting is not a rule」** |
| F-235 | ⭐⭐ **一个因为「能让数字变小」而被选中的常数** | `DISCRIMINATION_FLOOR = 4`，把 findings 从 12 条压到 4 条 | 「**这个数字如果换成另一个问题就不成立了，我会为什么重写它？**」 —— 隐藏 findings 的阈值与不存在的阈值**效果相同**，区别只在于其中一个被写下来了。⇒ 换成十二张豁免表，每条给一个**关于代码的事实**，每条都能靠读一个文件反驳。⚠️ **常数被调到某个 fixture 上，就已经是一种失败模式了** |
| F-236 | ⭐⭐ **一条没红的变异必须先被诊断，才能被相信** | M1..M6 里有四条没红，而四条都是我的错：相邻字符串**隐式拼接**（`「n/a」` 变成 `n/athe payload of ...`，够长且非空于是通过了判定）、改 `.py` **对已 import 的类不可见**、元组没有 `.strip()` | 「**这条没红，是规则不可靠，还是我的变异写错了？**」 —— 如果只写「6 条里 4 条没红」，读的人会去削弱规则让它变红。⇒ 修好 harness 后 **6/6 与规格一致**，其中 M5（重排字符串）**findings 完全不变** |
| F-237 | ⭐⭐ **三个检查声称自己被守着，而那个守护不存在** | `dev.py:157-158`（声称 `check` 包含未写的门禁，**实测 `CHECK` 里没有 `check-data`**）、`.ai/status.md` B4（声称「永远 INCOMPLETE」，**实测退出码 0**）、`no_enum_drift.py:185-187`（声称有一个探测，**实测零命中**）| 「**这个检查的保护由谁守？那个守护在哪一层？**」 —— 它们都没有。⇒ 三处量下的真相：**红的门禁有人看见**，而不在清单里的门禁连「不运行」都不会说。⚠️ **发现它的不是新规则，是一次盘点** |
| F-238 | ⭐⭐ **分不出「写错了」与「没走这条路」的门禁，会被调到数字看起来合理为止** | `S-18` 给「客户端没声明的字段」一个判决，⚠️ 而它十二条 findings 全是同一个形状：服务端提供了客户端还没开始用的东西（包括它当初要抓的那五个，**而没有任何页面读其中任何一个**）| 「**这条无法区分两种情形，我怎么知道哪一种？**」 —— 一个冒版只能被调成永远红或盲。⇒ 读 `required`：**必填未声明 = 客户端可能读到 `undefined`**（缺陷），**可选未声明 = 客户端不走那条可选路径**（不是）。⚠️ **代价：它让一小时前发布的那五个字段从 error 变成 note** —— 它们仍然每次运行都打印带字段名，但想让它们变红就得改服务端自己的可选性 |

| F-239 | ⭐⭐⭐ **一条被断言了五遍的结论，而守它的测试就在同一个套件里** | 量到 `APPEND_ONLY_TABLES` 15 个名、14 个被迁移创建 → 判定「`S-04` 在为一张它看不见的表亮绿灯」→ 删条目、加运行期发现、写新测试文件。⚠️ `test_storage.py:698` 已经决定过这件事（docstring 写着「正因为前向声明值得保留」）。 | ⭐ **我读了规则、`.ai/status.md`、ADR-0013、`constitution.md`、`.ai/memory/decisions.md` 五处，没读测试**—— 理由居住在测试的 docstring 里。⭐⭐ **记在测试 docstring 里的决定，是读代码的人找不到的决定**→ 改下一个清单之前先 grep **测试文件**，因为测试里有结论而不是另一份声明。 |
| F-240 | ⭐⭐⭐ **一个检查的对象是数据库拿不到的状态** | `D-01` 查「决策指向不存在的标的」，而 `decisions` 有复合外链 `(market, code) -> instruments`、`PRAGMA foreign_keys = 1`、`on_delete = NO ACTION`——实测插入直接被拒。⚠️ 它 docstring 里写的「schema 没有提供这个保证」**两句都是假的**，两句都没量。 | ⭐ *这条检查写出来的时候，它能看见什么？**——不能。→ **写一条检查前先计算它的对象达不达到**，通过手：尝试写入一行能进去的数据。⚠️ **若那一行写不进去，这条检查就是一段汽水**——但它仍然可能绿着，因为没有人写过它能达的状态。 |
| F-241 | ⭐⭐⭐ **约束的函数与检查的函数同名时，检查继承盲点** | `decisions` 的 `CHECK (length(trim(counter_evidence)) > 0)` 用 `trim()`，而 SQLite 的 `trim()` 只去空格。实测：一个 tab、一个换行、一个全角空格、一个换页符，全部被接受并保存。⚠️ D-07 第一版也用 `trim()`，也误上。 | ⭐ *它与被它检查的那个对象重叠了什么功能？**——受限的那一层。→ **检查与约束同时读一个函数时，先问这个函数有哪些行为**（**它的文档说了吗？还是你假定它只去空格？**）⚠️ 这一次两层同时误，而错的那一层就在红线 4 的实现约束上。 |
| F-242 | ⭐⭐⭐ **代理判断只在它尚未被违反时有用** | `dev.py:285` 的前置条件是 `gate.cwd is not None` ，即「有工作目录 ⇒ 需要 Node」。⚠️ `check-data` 是纯后端门禁，第一次跑就报 `cannot run: backend/node_modules is missing`——它根本没起来过。 | ⭐ *这个代理当时为何无违？**——因为当时每一个门禁都恰好同意。→ **写一个代理时要写下它在什么时候会失效**（本例：一个后端门禁声明了 `cwd`）。⚠️ 更好的问法：**判断来自命令本身**（`_needs_node(argv)`），而不是从容器的一个属性推断。 |
| F-243 | ⭐⭐⭐ **「37 passed」与退出码 1 可以同时成立** | `data.readonly()` 的探针失败路径泄了连接（`finally` 在 `try` 之外）。pytest 报「37 passed」、mypy 干净、ruff 干净、而 `PytestUnraisableExceptionWarning` 印在**汇总行之下**。 | ⭐ *我看的是哪一行？**——「通过了多少个」。→ **只看汇总行的人会读到正确结论**，而退出码才是判定。⚠️ 这是 `make check` 当作「完成」定义的**第一个实测理由**，且它是以一个 bug 的形式到的。 |
| F-244 | ⭐⭐⭐ **多行注释的续行会丢掉 `#`，而修正脚本会堆出 `# # #`** | 一个多行注释只在第一行写 `#`、续行不写 → 文件不能解析（**本会 5 次**）。修正脚本不幂等 → 第二轮又给已修正的行加了一次 `#`（261 处）。 | ⭐ *工具为何不能接住这个？**——因为注释里的一个 `#` 是**字符**，不是注释，而一个落在 docstring 里的修正**不会报语法错**。→ **注释与文档一律用行号写入，改完立即 `compile()`**；修正脚本必须**幂等**（跳过已带 `#` 的行）。 |
| F-245 | ⭐⭐ **一个打印了「判定」列的探针，会被当成测试那样被信任** | 第一版可写性探针用 `partition(".")` 取表名 → 不带表名的列名（`volume`、`trade_date`）表名为空 → 两个分支都不触发 → 应判「可写」，**而输出印 UNIMPLEMENTABLE**。 | ⭐ *它的输出样式是什么？**——24 行、每行一个判定、一个总数，**像测试一样可信**。→ **写出判定列的代码先自测**：若判定表里出现一个意外值，那不是探针结果，是探针写错了。⚠️ 第二版换成「全库搜列名并说出在哪张表上」。 |
| F-246 | ⭐⭐⭐ **同一个事实有两条解析路径，⭐⭐ 而应用那条带缓存** | `Settings()` 每次新建 ⭐⭐ 读环境；`get_settings()` 是 `lru_cache(maxsize=1)` ⭐⭐ 首次调用就定死 ⭐⭐ 实测：改完环境变量后两者指向**不同文件** ⭐⭐ 而 `conftest.py:65` 是唯一清缓存的地方 ⭐⭐ 今晚新增的三处 `setenv` 没清 ⭐⭐ ⇒ `test_today_api.py` 的断言里出现了**主人真实库**里的 `gross_margin` | ⭐⭐ *「这个配置在哪」有几条路能回答？* —— ⭐ **两条，⭐⭐ 而它们可以指向不同的文件。** ⇒ `checks/data.py` 改走 `get_settings()` ⭐⭐ 一个进程一个答案 ⭐⭐ 并加一条断言「两条路径不得分叉」⭐⭐ ⭐ ⭐ **注意 `conftest.py:59-62` 早就把这个警告写下来了 ⭐⭐ ⭐⭐ 而我读的是它的函数体 ⭐⭐ 没读它的理由。** |
| F-247 | ⭐⭐⭐ **`app.routes` 给出一个关于这个应用的假答案，⭐⭐ 而它看起来完全正常** | 量 B3 的探针走 `app.routes` 找 review 路由 ⭐⭐ 报**零条** ⭐⭐ 而这个应用有十一条 ⭐⭐ 根因与 **spec 050 记录的根因逐字相同**：`app.routes` 上有 12 项 `_IncludedRouter`，`.path` 是**空串**，`getattr(r, "path", "")` 把 12 条**全部**变成跳过 ⭐⭐ **而这是我这一轮第二次踩同一个坑，⭐⭐ 在一支专门用来量路由的探针里** | ⭐⭐⭐ *「我报『找不到』的时候，⭐ 这个『找不到』有没有可能是我自己坏了？」* —— ⭐ **`F-213` 说分不开，⭐⭐ 而这里分开了：换成读服务端自己发布的 `app.openapi()` 就分开了。** ⇒ 探针与测试都读**已发布的 schema** ⭐⭐ `test_the_response_is_published` 就是这条的反测。⭐ **判据：一个能报「零」的扫描器，⭐⭐ 必须先证明它能报出「一」。** |
| F-248 | ⭐⭐⭐ **一张表存在，⭐⭐ 不等于所有用它的地方都用了它 —— 而「唯一的一个家」是句要重测的话** | `ratings.ts` 第 2 行写着「⭐⭐⭐ **their one home**」，⭐⭐ 而 spec 049 收敛了**三处**、留下**第四处**：卡片的四个评分标签是 `ReviewPage.tsx:250-261` 的五个 `<Button>` 字面量 ⭐⭐ 实测：卡片的 `good` 可以改成笔记的「还是我的想法」而**门禁全绿** ⭐⭐ | ⭐⭐⭐ *「这张表有几个调用方？⭐⭐ 我上次量它的时候是三个。」* ⇒ 把 `ReviewPage` 改成 import，⭐⭐ 并加**源断言**「它一个字都不许自己写」⭐⭐（不是 DOM 断言 —— ⭐⭐ **缺陷正是「字面量相同而来源不同」，⭐⭐ DOM 断言看不见来源**）⇒ ⭐ **表的存在是声明，不是证据。** |
| F-249 | ⭐⭐ **一次 `oldString` 结束在方法中间的插入，⭐⭐ 不会响 —— 文件照样解析** | 往 `test_reviews_api.py` 中间插入一个新 class，`oldString` 取到某个方法的**倒数三行**而不是结尾 ⭐⭐ 那个方法的最后一行 `assert client.delete(...)` 被落到了新 class 里 ⭐⭐ 而报出来的错是 `AttributeError: 'FixtureFunctionDefinition' object has no attribute 'delete'` ⭐⭐ **指向一个和插入毫无关系的测试** | ⭐⭐ *「这次改动的边界，⭐ 是我以为的那个方法结尾吗？」* ⇒ 插入点必须取到**整个方法**或**整块分隔符**，⭐⭐ 且插入后 `git diff` 只应有增无删 —— ⭐⭐ **本次 `git diff` 全是 `+`，⭐⭐ 而少了的那一行照样不见了**，⭐⭐ 所以**「diff 没有 `-`」不足以证明没破坏结构。** |
| F-250 | ⭐⭐⭐ **一个 hook 的依赖数组里放了一个每次渲染都变的东西，⭐⭐ 而三个 reporter 都只说「超时」** | `useResource` 的 `useEffect` 依赖是 `[...deps, describeError]` ⭐⭐ 而我传了一个**内联箭头** ⇒ 每次渲染重跑 `run()` ⇒ `publish()` ⇒ 再渲染 ⇒ **无限循环** ⭐⭐ 实测：`card-enrolment.spec.ts` 的 **A4 / A5 各超时 30 秒**，⭐⭐ 而 `line` / `list` / `json` 三个 reporter **都只打印「Test timeout of 30000ms exceeded」—— 没有栈、没有行号、没有断言名** ⭐⭐ 最后靠 `git stash` 单文件**二分**出来 | ⭐⭐⭐ *「这条超时是**慢**，还是**永远不会停**？⭐⭐ 而报告有没有区分这两件事？」* —— ⭐⭐ **它没有。** ⇒ 修法两层：⭐ 调用点改 `useCallback`（与所有既有调用点一致）⭐⭐ **并且把 hook 本身修好** —— `describeError` 与 `fetcher` 一样走 ref 读，⭐⭐ `deps` 重新成为「唯一能重新发请求的东西」，⭐⭐ **而那正是这个 hook 头部早就写着的那句话。** ⇒ ⭐ **代码现在与文档一致，而不是反过来。** |
| F-251 | ⭐⭐ **我调用了一个自己没有读过的函数，⭐⭐ 而那句话本仓早就写在另一个文件里** | 给一条 API 测试写断言时，两次伸手去用 `client.app.state.services` ⭐⭐ ⭐ **它不存在** ⭐⭐ 而 `styleguide.test.ts:1219` 早就写着「⭐⭐ **do not call a function you have not read**」，⭐⭐ 就在我**读过**的那个文件里 ⭐⭐ | ⭐⭐ *「这个属性是**我推断的**，⭐ 还是**我读到的**？」（`agent-guide.md` §4.2）* ⇒ 正确写法不是绕过，而是⭐⭐ **承认这条断言写不成**：⭐ `POST /review/{id}` 对客户端提交的 `duration_ms` 答 **422**，⭐⭐ 所以 **HTTP 造不出带时长的行**，⭐⭐ 端到端断言那条路本身就是错的。⭐⭐ **一个写不成诚实写法的断言，⭐⭐ 通常在告诉你边界画错了，⭐⭐ 而不是 fixture 少了。** |
---

## 五、测试与验证类

| # | 失败模式 | 表现 | 自查问法 |
|---|---|---|---|
| F-40 | ⭐ **期望值从被测代码读取** | `assert x == MODULE.LIMIT` | "把代码**改坏**，这个测试会红吗？" |
| F-41 | **断言太宽** | 只断言"返回了列表" | "我断言的是**行为**还是**形状**？" |
| F-42 | ⭐ **"检查通过" ≠ "检查运行了"** | 缓存命中与真跑输出一样 | "输出里有 `Cached:` 行吗？" |
| F-43 | **复述 diff 的测试** | 测试内容等于代码改动 | "这个测试**捕获了什么独有回归**？" |
| F-44 | **改断言让测试过** | 实现错了改测试 | "我先怀疑**实现**还是**测试**？" |
| F-45 | **只测全新安装** | 首次启动的升级路径没测 | "**升级**路径有测试吗？" |
| F-46 | **"没发现回归"当成"已修复"** | 缺根因证据 | "结论应该是「**修复未经验证**」吗？" |
| F-47 | ⭐ **套件全绿 + 未 mock 的真实请求** | `ECONNREFUSED` 打在日志里，退出码仍是 0 | "日志里有**本该被拦下的请求**吗？" |
| F-48 | ⭐ **同义反复 / 不可能失败的断言** | `assert x is None or True`；只有一行的桩测试 | "把它删掉，**这个测试还在吗**？" |
| F-49 | ⭐ **「两处编辑」被做成一处** | 规则自己预测过失败，又失败了第三次 | "这条规则的注释里**写过它怎么失败**吗？" |
| F-50 | ⭐ **只修门禁报出来的那几条** | 同类的漏网留在文件里 | "**同类**的地方我全看了吗？" |
| F-233 | ⭐⭐ **「可达」是量出来的，不是看签名看出来的** | 我断言 `getDaily(market, code, {start, end})`（`api.ts:1077`）⇒「主人真会踩到」；全前端 grep 只有一个调用点 `InstrumentPage.tsx:95`，**不传任何参数** | "**可选参数 ≠ 产品会用到它。** 我说的是「可达」，量的是**签名**" （`F-49` 家族：**我预测会失败的那次，失败在别处**） |
| F-230 | ⭐ **pydantic 强转让测试绿、mypy 让它红** | `fetched_at=utc_millis()`（返回 `str`）填进 `datetime` 字段：**5 条测试全过**，只有 mypy 报 `incompatible type` | "**两个检查不一致时，先信哪个？**" —— 红的那个知道我错在哪；绿的那个只是**还没走到**那条路 |
| F-229 | ⭐⭐ **断言为真的理由不是它声称的理由** | `assert t.Contains('_CLAMP_TOLERANCE_DAYS = 7')` 通过 —— 但那处字符串被 PowerShell 的**无界** `[String]::Replace` 写进了 **docstring 的句子中间**，真正的模块级定义是另一处 | "**把它改成错的，那条断言还会为真吗？**" （`F-98` 的自查「两侧同形先失败」在本例**失效**，因为**被污染的那处不是同形文本，而是更长的行**） |

---

## 六、Agent 协作类

| # | 失败模式 | 表现 | 自查问法 |
|---|---|---|---|
| F-50 | **首因支配**（first topic dominance） | 只处理对话/文档开头提到的第一件事，后面全漏 | "**后半段**我处理了吗？" |
| F-51 | ⭐ **反射性恭维** | "这个想法很好！" | "我是在**同意**，还是在**有用**？" |
| F-52 | **把"能跑"当"通过"** | 未跑 `make check` 就说完成 | "我**跑了**吗？还是**觉得**它会过？" |
| F-53 | **未运行却暗示已通过** | "应该没问题" | "这句话有**证据**吗？" |
| F-54 | **投机性抽象** | 写"以后可能用得上"的代码 | "**谁**现在用这个？" |
| F-55 | **顺手重构** | 改动无关代码 | "这行改动**属于本次范围**吗？" |
| F-56 | **新增"可选弹性"** | 加一个没人要求的重试/缓存 | "它防止的**具体故障**是什么？" |
| F-57 | **元抽取** | 抽"用户做了什么"而不是抽内容 | "我抽的是**内容**还是**行为**？" |
| F-58 | **细节污染** | 把已有细节混进新记录 | "这个细节**来自本次输入**吗？" |
| F-59 | **隐式属性推断** | 从"买了燕麦奶"推断"乳糖不耐" | "这是我**读到的**，还是**推断的**？" |

---

## 七、产品红线类（最严重）

| # | 失败模式 | 违反 | 自查问法 |
|---|---|---|---|
| F-70 | **加"每日精选/机会推送/异动提醒"** | 红线 8 · 11 | "这个功能是**拦截**还是**推荐**？" |
| F-71 | **展示收益率 / 排行 / 徽章 / 打卡** | 红线 9 | "这是**事实**还是**成绩**？" |
| F-72 | **"草率但奏效"显示盈利数字** | 红线 9 · 10 | "这个决策**过程**合格吗？" |
| F-73 | **安慰话术**（亏损时说"长期看好"） | 红线 10 · 13 | "我在**帮他面对**，还是在**帮他逃**？" |
| F-74 | **允许"稍后再答"** | 红线 13 | "有没有**第三选项**？" |
| F-75 | **降低"写下"的门槛** | 红线 13 | "**索取在先**还在吗？" |
| F-76 | ⭐ **让 agent 替用户写决策** | 红线 15 · 13 | "这个工具**存在**吗？不该存在" |
| F-77 | **把产品做成惩罚工具** | 红线 14 | "**日常**用起来顺吗？" |
| F-78 | **止损提示不含"恢复所需年数"** | 红线 12 | "用户知道**时间成本**吗？" |

---

## 八、文档与流程类

| # | 失败模式 | 表现 |
|---|---|---|
| F-80 | **把"调研过"说成"借鉴了"** | 虚报借鉴深度 |
| F-81 | **用比喻回答"是什么"** | 听起来深刻，但答不出"首页放什么" |
| F-82 | **截图文档** | 与安装版本不符，**本质上不可维护** |
| F-83 | **PR 级临时文档放根目录** | 与长期文档混淆 |
| F-84 | **早期取舍决策不留档** | 半年后被重复调研 |
| F-85 | **"Known inconsistencies" 被隐藏** | 假装一致会让后来者以为是自己错了 |
| F-86 | **新增规则不声明落在第几层** | 只写第 ① 层 = 迟早被违反（0.2） |
| F-87 | **一张台账建两处** | 职责重复，迟早不一致 |
| F-88 | **未实现的功能不标注** | 后来者会去找 |
| F-89 | ⭐ **台账说一件已完成的事没做** | 边做边写「还没做」，做完了没回头改 | "我这一轮改的东西，台账里**还有哪句是假的**？" |

---

## 九、本机环境类

| # | 失败模式 | 表现 | 规避 |
|---|---|---|---|
| F-90 | **用 `rm`** | 被 `genie-trash` 拦截，`Permission denied`，中断整条命令链 | **绝不使用 `rm`** |
| F-91 | **直接 `mv`** | 间歇性 `Permission denied` | **先 `cp` 再 `mv`** |
| F-92 | **假设目录结构** | `ls packages/react/src/` 不存在（62 个组件目录直铺） | **先 `ls` 再假设** |
| F-93 | **整读超大文件** | > 256KB 读不了 | **先 `grep -n "^#\{1,3\} "` 看结构，再定点读** |
| F-94 | **在 `D:\AAA\A-kew\` 找 `.ai/`** | 项目根其实是 `alphacouncil\` | 用 `find . -maxdepth 3 -type d -name ".ai"` 定位 |
| F-95 | ⭐ **`core.autocrlf=true`（本机）** | 新 clone 每个文件哈希都不同，内容却一样 | 比哈希前先**归一化换行符**；`CR=0` 只在**工作树**上成立 |
| F-96 | ⭐ **here-string 吃掉 f-string 的转义引号** | `SyntaxError: unexpected character after line continuation` | 含 `\n` / 引号的 Python **一律写成文件再跑**，不走 shell |
| F-97 | ⭐ **`Out-File -Encoding utf8` 写 BOM** | `json.loads` 报 `Unexpected UTF-8 BOM` | 读 JSON 用 `utf-8-sig`；发中文 body **用 Python**，不用 `ConvertTo-Json` |
| F-98 | **`replace(old, new, 1)` 只改第一处** | 脚本报告「改了 3 处」而实际有 4 处同类行 | 全替换后**断言长形式已消失**，不要只报计数 |

| F-99 | ⭐ **`StrEnum` 让 `min`/`max` 按字符串排序** | 严重度表方向对了，但 `OR`/`AND` **同时颠倒** —— 合法、类型正确、完全反了 | `min`/`max` 在枚举上一律传 `key=`；⭐ **且必须有一条测试同时断言两个运算符**，否则反转照样通过 |
| F-100 | ⭐ **`glob('*/package.json')` 漏掉全部 `@scope/name`** | 包数偏小（153 而非 306）**而且看起来完全合理** | glob 的形状要**对着真实目录列一遍**；⭐ scoped 包在 npm 里不是例外，是**一半** |
| F-101 | ⭐ **护栏在写盘前 `return`，文件没变** | 下一步替换了一个还不含新代码的文件，引用不存在的符号 | **护栏拦住的是那一次写盘**；它不拦住别的。下一步必须**重新确认文件状态**，不能假设 |
| F-102 | ⭐ **检查排在它所检查的替换之后** | 断言永远失败（要找的东西已经被替换删掉了） | 断言要么在前，要么改成**确认不存在**；⭐ **顺序错的断言教人忽略断言** |
| F-103 | ⭐ **删掉出问题的字符来「修」编码问题** | 编码测试变红，而编码早就修好了 | `✗` 崩溃要靠 `use_utf8()` 修，**不是**靠把它换成 `x`；⭐ 删掉症状等于把问题藏起来 |
| F-104 | ⭐ **同类错误有两个调用点，只改了一个** | 另一半继续静默出错，只有另一条测试才发现 | 修复后 **grep 模式，不是 grep 那一行**；把收窄逻辑放进一个 helper |
| F-105 | ⭐ **给遍历加第二条入队路径，却没在同一处展开子节点** | 缺失的条目**完全不出现**，报告和平时一样健康 | 每条入队路径都要展开子节点；⭐ 测试断言**缺失的名字出现在输出里**，而不只是断言已有集合 |
| F-106 | ⭐ **读取世界的地方没有缝** | 既有测试的 monkeypatch 失效，测试转而断言真实安装的东西 | `main()` 只走一个 `scan()`；⭐ **失败的是测试、错的可能是重构** —— 替换点不是偶然 |

| F-107 | ⭐ **fixture 让测试断言了真话、但说的是另一件事** | 测试绿，而它测的东西根本没被触发（`git add -A` 把待测文件变成已跟踪） | fixture 必须构造**缺陷真正的样子**；⭐ 断言要精确到「是哪一条」，否则多一条也照过 |
| F-108 | ⭐ **变异后的文件不能解析，却算成了 killed** | pytest 报 **error** 而不是 **failed**，脚本按通过处理 | 变异检查**先编译每个变异**，编译不过的记为「**未测**」；⭐ 坏掉的实验产不出证据 |
| F-109 | ⭐ **「已应用」守卫用子串写，旧形式反而满足它** | 改名类脚本报「已应用」而其实没改（`_SKIP_DIRS = ...` 含 `SKIP_DIRS = ...`） | 守卫**锚到行首或整行**；⭐ 子串守卫的唯一作用就是在不该通过时通过 |
| F-110 | ⭐ **「圈定了范围，所以只可能」——范围里住着什么不由我说了算** | 规则第一次跑真实仓库就报出它声称不可能的告警（`.pytest_cache/README.md`） | 断言「只可能」之前**先在真实仓库上跑一次**；⭐ 工具缓存就住在被扫的树里 |
| F-111 | ⭐ **两个模块要用同一个列表 → 复制而不是提升** | 列表会漂移，而漂移之后告警会为一种没人写下来的理由响起 | 私有名跨模块要用 → **提升为公开**；⭐ 「一个概念一个家」在目录名上同样成立 |
| F-112 | ⭐ **文档里写下了一个数字，而没有人核对它** | docstring 说 DEA 预热 `25+8`，代码给 25，**34 条测试全绿**；实测数非空值才发现 | 文档里的数字**就是断言**；⭐ 把它断言出来（`dea` 进预热参数表，值 33）比留一句注释便宜 |
| F-113 | ⭐ **丢弃一个东西，却仍然给它一个名字** | 未知指标从图上被丢掉，图例却仍列出它 —— **图上有一条没有线的图例项** | 丢弃是**要告诉人的决定**：图例只列画出来的，剩下的用一句话说出来；⭐ `?? 默认值` 是在掩盖这个决定 |
| F-114 | ⭐ **一条规则：扫到就修** | 4 个 U+FFFD 命中里 3 个在引述规则本身、1 个是被记录的损坏**证物**；「修」掉就把证物改成正常的 | 扫完**逐个判断是不是故意的**；⭐ `.ai/regressions/` 里围栏中的乱码是**存档**，不是缺陷 |
| F-115 | ⭐ **一条规则有两个条件，而 fixture 只破坏了一个** | S-01 构造检查是「对的文件 **且** 对的函数名」；fixture 把函数叫 `fetch`，删掉文件条件后测试照绿 | fixture 要**只**破坏一个条件；⭐ 「这条测试通过」不等于「这个条件被测过」 |
| F-116 | ⭐ **用目录回答一个关于模块的问题** | S-01 判「在 `providers/` 目录下」而它要守的是「客户端在认可的地方被构造」；目录里将来长出的每个文件都自动获得直连资格 | 白名单写成**具名文件**；⭐ 「客户端在这里构造」是一句话能说清的理由，「行情在这里」不是 |
| F-117 | ⭐ **用一份不相关的地图说「那边没有路」** | TSP 能力矩阵只覆盖数据层，却被用来否掉整个功能面；而 `status.md` 自己把「主动触达」记了两次 | 判「不做」之前**打开被引用的那份文档**；⭐ 项目自己的「还差」清单比外部对照更权威 |
| F-118 | ⭐ **一个从未到达过的分支，所以也从未被测过** | `NO_BARS` 状态在生产里不可达（路由先判了 bars），于是把它映射成 `not_crossed` 的变异存活 | 公开函数要**全函数**：空输入也要有答案；⭐ 「生产到不了」不是「可以不测」 |
| F-119 | ⭐ **缺失字段在渲染中抛异常 → 白屏** | E2E fixture 少一个 `metric` 键，`metric.state` 在 render 里炸掉，整个今日页变白 | 数据字段缺失降级成**一句话**而不是崩；⭐ 在「读者专门来看出了什么事」的那一页上白屏是最贵的一种失败 |
| F-120 | ⭐ **规则的标题/docstring 比它守护的东西宽** | S-01 四处都写「唯一入口 / 全部出口」，而实现只覆盖 HTTP —— `smtplib` 与 socket 一年没人拦 | 规则改名或改实现，⭐ **两者都不改，读的人就得到一个比真相乐观的印象** |
| F-121 | ⭐ **粗粒度的名字代替细粒度的能力** | `urllib` 同一包装着解析器与客户端；顶层包匹配会把 `card.py` 的 `urlparse` 报成出口 —— 与 ADR-0031「目录代替模块」同形状 | 匹配**精确的点分名**；⭐ 两次都是同一个错误 |
| F-122 | ⭐ **合法形态有测试 ≠ 非法形态被拦住** | 变异「把 `smtplib.SMTP` 从构造器清单删掉」存活：只有「工厂内合法」被测，全树安静也测不出 | 每类构造器都要有一条「在真代码里能构造、换个函数名就被拦」的测试 |
| F-123 | ⭐ **从 grep 输出下结论，而不是读代码** | 断言 `indicators.py` 两处除法「没有守卫」，实际两处都有 —— 同一形状的错误当天第二次 | 断言缺陷前**读那一段**；⭐ grep 给你的是候选，不是结论 |
| F-124 | ⭐ **聪明的滚动计数是 off-by-one 的藏身处** | `annualised_volatility` 的 `undefined` 计数器连错两次，症状是**序列被永久遮蔽**而不是报错 | 窗口内直接计数；⭐ 一个 bar 的错 = 一条再也不画的曲线，且没有任何东西会抛 |
| F-125 | ⭐ **门禁的结论取决于你怎么调用它** | `\| Select-Object` 过滤输出时 `npm run test:e2e` 在 89 全过后仍退出 1；重定向到文件则退出 0 | ⭐ **管道 + UTF-8 是 `regressions/0004` 那一族**；测试和门禁自身都直接 spawn 进程，**所以这条没有任何测试覆盖** —— 只有人或 agent 用管道调用时才会出现 |
| F-126 | ⭐ **枚举里有、文档里有、全项目没有一个地方产生** | `.ai/error-codes.md` 写着「限流与封 IP 必须分成两个 code」，而 `_guard` 把 403 和 429 抛成同一个 `ProviderBlockedError`；`DATA_SOURCE_RATE_LIMITED` 与 `DATA_SOURCE_IP_BLOCKED` **由零个地方 raise** | 文档规定了区分就**按它拆**；⭐ 枚举上的拆分若不改变**行为**就只是一次改名 —— 冷却时长必须跟着分档 |
| F-127 | ⭐ **一条 docstring 指向了一个不存在的地方** | `core/http.py` 写「no jitter, no serialisation —— 那些在行情路径里，`router.py` 已经有了」，而 `providers/` 里除新写的一个文件外**一个 `sleep` 都没有** | 指路之前**搜一遍被指的那个地方**；⭐ 指向不存在实现的注释比不写更贵：读者会据此相信已覆盖 |
| F-128 | ⭐ **样本采到了几个，就以为那是全集** | 变异「把 `roe_avg` 改成 `NOT NULL DEFAULT 0.0`」存活：三个「缺失」测试恰好都空的是**另外三列** | 「每一列都可以是空的」要么**逐列参数化**，要么不写；⭐ 三个样本不是关于八个列的性质 |
| F-129 | ⭐ **一个真值恰好和兜底顺序一致，于是守卫看起来有效** | `totalShare` 与 `liqaShare` 都填 `12.56`，两列互换后所有断言照过 —— 「流通股 = 总股本」对真公司是**真话** | 让 fixture 里**每个字段取不同值**；⭐ 一个字段的取值与另一个相同，就等于没有测它 |
| F-130 | ⭐ **对不存在的运行结果下了正确的结论** | 变异脚本把 `BACKEND` 写成 `scripts/`，pytest 收集不到测试并以 **5** 退出；脚本据此打印「BASELINE IS RED」 | 「什么都没跑」与「跑了并且红了」是两种结果；⭐ 守卫自己先证明它测到东西（`regressions/0006` 的同一形状） |
| F-131 | ⭐ **给变异体挑了不走那段代码的测试** | 「`exc.code` 被忽略」的变异存活，因为我把目标指向 `test_recovery_policy.py`，而它**手工构造 `DataResult`**，根本不调 `_failure` | 变异体的目标必须**执行**被改的那行；⭐ 一个变异存活，先怀疑测试选择，再怀疑测试内容 |
| F-132 | ⭐ **守卫比它自己列举的东西更宽，于是它自己是多余的** | `_ABSENT_CELLS` 列了 `""`/`"--`/`"null"` 等，而它们**全都**也让 `float()` 抛异常；删掉整个正则，测试全过 | 写完守卫就**问：能不能整体删掉**；⭐ 与其证明它在，不如证明它是唯一路径 |
| F-132 | ⭐ **索引顺带满足了查询，于是查询里的排序看起来是多余的** | 删掉 `ORDER BY ... , fetched_at DESC` 测试照过，因为 `idx_...` 本身就按 `fetched_at DESC` 建 | 顺序依赖要**写出来**（索引注释里一句「末位承重」）；⭐ 两处都在时无法互相区分，只能靠文档 |
| F-133 | ⭐ **测试的严格部分被一个巧合抵消，于是它看起来是对的** | ① fixture 把 `last_sent` 设成**时钟第一次读就返回的值**，「更新了」与「没动」是同一个数；② URL 用例写 `file:///x`，`netloc=''` 让它**因为没有主机**被拒，而不是因为 scheme —— 两个变异都存活 | 断言的期望值必须是**被测代码之外**能产生的东西：让 fixture 的起点成为时钟产生不出的值；⭐ 每条用例**只隔离一个拒绝理由** |
| F-134 | ⭐ **docstring 承诺了一个实现没有的豁免，而它一直隐形** | `no_print.py` 的文档写着「`__main__.py` 的 stdout 就是接口，应豁免」，实现扫全包 —— ⭐ 而**从来没有入口用过 `print`**，所以没人发现 | 规则文档里写的**范围**就是该实现的范围；⭐ 新增能力时先核对「文档早于实现」的那些条目 |
| F-135 | ⭐ **一个只有一种合法取值的列不是数据，是常量** | `delivered INTEGER NOT NULL CHECK (delivered = 1)` —— ⭐ 而且我为它写了一段长注释辩护（「让『成功』成为数据里的一件事」） | 台账的**形状检查**能抓住它（不属于任何类别）；⭐ **常量伪装成数据**的那个注释，通常就是伪装本身的证据 |
| F-136 | ⭐ **用一个 `global` 携带的理由，被 `--fix` 连带删掉** | 三处模块级全局 + `global`，`ruff --fix` 删掉承载理由的 `noqa`，理由随它一起没了 | 把状态**收进一个对象**，让替代方案（传自己的进去）显形；⭐ 依赖它的测试才写得出理由 |
| F-137 | ⭐ **熔断开了却永远关不上** | 唯一能重置计数器的是那次成功，⭐ 而熔断打开后就再也够不到它 | 按**次运行**而非按时间窗；⭐ 没有后台循环时，「等会儿再试」只能由**再跑一次命令**表达 |
| F-138 | ⭐ **按行扫描的断言，扫的是换行写的那条声明** | V-09 用「本行含 `transition` 就收本行的 `ms`」，而 `globals.css` 的 `transition:` 简写**跨四行** —— 只找到 1 个时长而不是 7 个，⭐ 而规则是「期望零违规」，于是**报绿** | 声明按 CSS 自己的边界（`;`）读，不用行；⭐ **防空洞断言（anti-vacuity）第一次就红时，先怀疑它守的断言**——那是「它还没生效」的证据，不是「数据不对」 |
| F-139 | ⭐ **计数把被测对象本身算成它的一个样本** | V-12 数 `.type-*` 的使用处，`occurrences()` 连 CSS 一起走，⭐ 而定义 `.type-page-title {` 里的 `.` 不是单词字符，**lookbehind 放行** —— 七个类各得 1 分，真实是 0 | 「使用数」与「定义」**分文件域**统计；⭐ 任何计数断言都要问：**被测对象本身会不会落在被扫描的集合里** |
| F-140 | ⭐ **临时工具放在永久工具的目录里，于是门禁为它红了** | 迁移脚本与变异脚本写进 `backend/scripts/`，`lint` 报 `RUF100`/`E501`、`S-14` 报未跟踪、**门禁 11 步红 3 步** —— 而它存在的全部理由是被删掉 | 一次性工具**不进仓**（放 `%TEMP%` + 参数传路径）；⭐ 若必须在仓内，则**同一轮内删除**，不留到下一次门禁 |
| F-141 | ⭐ **文档把实现该做的事写成了它已经做的事，而机器照着实现了** | `core/console.py` 是从 `scripts/_console.py` **整份复制**的，ⓘ 但两份的模块 docstring 讲的是**不同的故事**（一份讲 GBK 事故，一份讲转发关系）⇒ 复制时只带走代码、留下不一致的理由 | 复制文件后**逐段对比 docstring**；⭐ 更稳的做法是**移动而非复制**，让「两份」在物理上不可能出现 |
| F-142 | ⭐ **一次性迁移脚本的第一个版本，路径指向了错误的树，而它报绿** | `_t045_typescale.py` 算 `parents[1]/"frontend/src"` ⇒ 指向 `backend/frontend`（不存在）⇒ 迁移 **0 处**、**退出码 0**、**无任何警告** | 迁移脚本**必须断言「我改到了东西」**：改 0 行 ⇒ 非零退出；⭐ 这与防空洞断言是同一条规则在脚本侧的形态 |
| F-143 | ⭐ **门禁红了，而我第一反应是「这次不算」** | `gateB` 3 步红，⭐ 而这 3 步**全由我自己的临时脚本引起** ⇒ 绿树里其实有 4 处真问题（`core/console.py` 未 `git add` 等）等着被一起放过 | 门禁红**永远是先修门禁**；⭐ 「这次的失败不算」这句话本身要写进变更日志，否则下一次会有人说它 |
| F-144 | ⭐ **一句「规则不做 X」的注释，被机器照着做了** | 我为避开 `RUF002` 在注释里解释「`#` 注释里的中文不受管」—— 而 `RUF003` **恰好管注释**；⭐ 修 `RUF002` 时新写的注释里又带了一次全角逗号 | 写「这条规则不管什么」之前**去读那条规则的实现**；⭐ 注释里引用规则时，**它是断言不是解释**，要和其它断言一样进变异检查 |
| F-145 | ⭐ **关于「某个字符不能用」的注释，本身含那个字符** | 第一次改用「描述它」，⭐ 第二次又把该字符写进引号里当例子 ⇒ 连红两次 | 遇到「某字符被禁」时，注释**只能描述、不能引用**；⭐ 若规则禁的正是引号本身，**先写完再自查一遍有无残留** |
| F-146 | ⭐ **脚本改 0 处并退出 0，于是「迁移完成」看起来是真的** | `_t045_typescale.py` 路径算成 `parents[1]/"frontend"`（该目录不存在）⇒ **迁移 0 行、无警告、退出码 0** | 一次性脚本**必须自查「我改到了东西」**；⭐ 迁移类脚本要**同时报「改了几处」与「跳过几处」**，两个数都为 0 就是失败 |
| F-147 | ⭐ **门禁跑的时候我改了被测的树，于是门禁测的是一个半写状态的文件** | `gateC` 11:06 启动，⭐ 我在 11:09 改 `StopLossPrompt.tsx`（把 JSX 注释写成了 `return (` 之后的 `{/* … */}`）⇒ **11 步里 3 步红**；⭐ 而树静止后单独重跑 `typecheck` / `lint` / `build` **全 exit 0** | ⭐ **门禁运行期间不许碰被测目录**（`frontend/src` · `backend/src` · `tests/`）；改 `.ai/` 下的文档可以，改代码不行。⭐ 而「多步红 + 单独跑全绿」这个组合**本身就是信号** —— 先比时间戳，别急着改代码 |
| F-148 | ⭐ **I widened the rule, and the machine faithfully reported a hundred-odd hits that were none of them violations** | `V-10` written as 「no emoji anywhere」, while §5 says ⛔ 禁止 emoji 作**功能图标**」 ⇒ every one of the 150+ hits was this repository's own comment marker | ⭐ When copying a rule into an assertion, **copy the qualifier too**; ⭐ and ask first how many lines would have to change for the rule to pass — ⭐ **a lint that needs a hundred edits gets deleted, and those edits are where the reasoning lives** |
| F-149 | ⭐ **「register it just in case」 was judged dead code by the new rule on its first real input** | `Icon.tsx`'s registry started at 13 entries (5 views + 8 interface actions) and ⭐ V-11 reported all 8 as dead on its first run | ⭐ 「the library has it」 is not 「the product uses it」; ⭐ registries grow on their own, so **dead entries have to be a gate rather than a habit** |
| F-150 | ⭐ **The mutant turned its own violation into compliance** | Adding `icon2: 'ghostly',` to `routing.ts` to make an unnamed registry entry — ⭐ and that edit **supplies the literal `ghostly`**, which is exactly what the rule asks for ⇒ the suite went green **and it was right to** | ⭐ Before manufacturing a violation, ask whether **the edit also satisfies the rule**; ⭐ **「mutant survived」 and 「mutant never applied」 are different results and must be reported separately** — conflating them files a broken probe as a weak rule |
| F-170 | ⭐⭐ **A hand-written class outside every `@layer` outranks the whole utilities layer, and 36 elements were asking it for a colour it does not have** | `globals.css:73`'s `.mark` sets `border-left: 2px solid var(--color-rule)` as a **shorthand**, in a rule written after the `@import` and therefore in no layer. ⭐ An unlayered rule beats `@layer utilities`, so on any element carrying **both** `.mark` and a `border-l-*` utility ⭐ the utility loses. ⭐ **Thirty-six classNames across twelve files** were in that state: ⭐ error rows asking for `--color-up`, notices asking for navy, and every log row in `RecordTimeline` ⭐ — ⭐ **all of them rendering with `--color-rule`**, ⭐ which for the logs meant the one marked row was indistinguishable from the three beside it. ⭐ It surfaced because a mutation the E2E let survive (`tone: 'neutral'`) sent me looking, and only `getComputedStyle` found it | ⭐ **A class-name assertion passes on a class that is present, spelled right, and overridden.** The class was there; the cascade was wrong; no amount of reading the JSX finds that. ⭐ `palette.spec.ts` had already set the pattern for visual contracts — assert a computed style — and the reason is exactly this: **a contract that lives in the cascade can only be checked in the cascade**. ⭐ And the fix is not to repair `.mark`: ⭐ **four places use it correctly** ⭐ — ⭐ they want `--color-rule` ⭐ — ⭐ so the rule is 「`.mark` and a `border-*` utility do not share an element」, and `V-14` now says so |
| F-171 | ⭐ **A byte-for-byte `innerText` comparison over a region fed by in-flight requests compares two moments in a race** | 「取消编辑不会动笔记」 took `note-detail`'s whole `innerText`, edited, cancelled, and asserted equality. ⭐ The panel is not one thing: it holds 「这条笔记是什么」 and 「关于这条笔记还知道些什么」 ⭐ — enrolment, review history, outgoing links, backlinks — ⭐ and the second half is **filled in by requests that were still running when the snapshot was taken**. ⭐ It passed only because the two moments landed close together. ⭐ Adding the review history added a second request whose answer appears inside the snapshot window, and a **correct** feature lost the race | ⭐ **An assertion's scope is part of the assertion**, and 「the container」 is not a scope when the container has parts with different lifetimes. ⭐ The fix reads the `h2` and `note-preview` ⭐ — the note itself ⭐ — and adds one `toBeVisible` so the test does not stop checking that cancelling left something on screen. ⭐ **A test that only passes when the machine is quiet is a test with a hidden input, and the input is timing** |
| F-172 | ⭐ **A fixture that holds only the cases the code handles agrees with the code** | The review-history fixture had three rows: two `reviewed` and one `reset`. ⭐ `NoteReview['outcome']` has three members, and the third ⭐ — `deferred` ⭐ — was in the source, in `OUTCOME_LABEL`, and in **no test at all**: ⭐ 「我说以后再看」 had never been rendered by a single assertion. ⭐ A mutant that weakened the rating guard survived, and reading that as 「the fixture needs a `deferred` row」 rather than as 「this label is untested」 is what made the row worth adding | ⭐ **Ask which branches of a union the tests reach.** ⭐ The cheapest way to find out is to give the fixture one row per member and see which assertion you then have to write. ⭐ This is the fixture-side twin of `F-151`: ⭐ **a branch or a label that cannot be reached looks exactly like one that is never needed** |
| F-173 | ⭐ **A compiler-rejected mutant is a third verdict, and filing it as 「survived」 sends somebody to write a test for a bug that cannot be written** | `review.rating !== undefined` replacing the `rating !== null` guard was reported `SURVIVED` with `BUILD FAILED` in the body, and the harness exited 1. ⭐ `rating` is `ReviewRating | null` ⭐ — ⭐ `!== undefined` does not narrow away `null` ⭐ — ⭐ so `RATING_LABEL[review.rating]` **does not compile**. ⭐ The type system is a real guard here, and it is **stronger** than a red test, because nothing about the product changed | ⭐ `F-159` met this wall from the side of 「a mutant must be type-clean」; this is the same wall from the **reporter's** side. ⭐ Three verdicts, printed three ways ⭐ — **killed (unit/e2e)**, **rejected by the build**, **SURVIVED** ⭐ — ⭐ and only the third is a failure. ⭐ And a finding worth keeping apart: **「no test covers this」 and 「this cannot be written」 are different results**, ⭐ and a probe that cannot tell them apart reports the second as a hole in the first |
| F-174 | ⭐ **An exact-match assertion on a row containing a local-time timestamp passes in Shanghai and fails in San Francisco** | The `defer` row's text was asserted as `'我说以后再看 下一次 2026-10-01'`, and the real row is 「标签 · **时间戳** · 明细」 ⭐ — ⭐ `2026-09-20T00:00:00Z` is `2026-09-20 08:00` at UTC+8 and `2026-09-19 17:00` at UTC-7. ⭐ It failed here, which is lucky ⭐ — ⭐ but only because this machine is east of Greenwich | ⭐ The other timestamp assertions in this file already assert the **day**; the habit was missing from the one assertion that happened to use equality. ⭐ **When a rendered string is made of a fact you control and a fact the platform formats, assert the two separately** ⭐ — ⭐ here: the four rating labels are absent, the due date is present, and neither is a timestamp |
| F-175 | ⭐ **A one-pass 「change as you go」 script cannot tell 「my pattern found one」 from 「my pattern found eight and wrote seven wrong」** | The script that removed `mark` reported `removed 1 className(s)` against a gate message that had just listed eight. ⭐ Three faults hid behind that one number: the regex matched quoted strings **across the whole file**, so the first quote it met opened a span running to the next one hundreds of lines later; ⭐ the boundary was a phrase that **also appears inside the region being removed**, so it could not be its own boundary; ⭐ and a `U+FFFD` guard rejected the whole run because `BacklinkList.tsx` **shipped in stage C with one already in it** ⭐ — ⭐ a veto, not a check | ⭐ Count in a separate pass, ⭐ **refuse to write below a plausible floor**, ⭐ and assert *planned == written* before declaring success. ⭐ The two sub-rules are worth their own lines: ⭐ **a search string that can appear inside the region being removed cannot be its own boundary** ⭐ (anchor on the code line beneath it), ⭐ and ⭐ **a corruption guard must distinguish 「I broke it」 from 「it was already broken」** ⭐ (compare against the file's prior state). ⭐ The floor is the part that matters: ⭐ a script that writes on a suspiciously small number is worse than one that fails, ⭐ because it prints success |
| F-176 | ⭐ **A test written against the class you just deleted matches nothing, and 「0 rows, all unmarked」 is what a broken feature looks like** | The computed-style check was written as `li.mark` in the same commit that removed `mark` from every one of those rows, so it found 0 and failed on the count. ⭐ Rewritten as `li` it found **5** ⭐ — ⭐ the three review rows plus the outgoing-link rows plus the link picker's ⭐ — and the assertion 「exactly one row is marked」 would then have been about four components at once. ⭐ It is `ol li`, and that is not arbitrary: ⭐ 「次序是重点」 is the reason the review history is an ordered list | ⭐ **When a fix removes a class, every test that named it is now a test of nothing** ⭐ — ⭐ and it fails loudly, which is the good case. ⭐ The quiet version is widening a locator: ⭐ **an assertion scoped to a container holding four components is an assertion about all four**, ⭐ and the failure message will not say so. ⭐ Scope by the thing the assertion is about ⭐ — ⭐ here the `ol`, whose existence is a product decision ⭐ — ⭐ not by 「whatever matches」 |
| F-177 | ⭐⭐ **A rule that finds only defects is a rule that will eventually delete the evidence, and the first run of S-15 proved it** | S-15 (`no-mojibake`) shipped and found **five** U+FFFD in `.ai/` on its first run. ⭐ **Two were real damage** ⭐ — 「界面是␦␦␦衬线」 ⭐ and, in a heading, a U+FFFD where the repository's own `⭐` marker belongs ⭐ — ⭐ and **three were legitimate**: ⭐ `agent-guide.md` and one change log *quote* U+FFFD in order to warn about it, ⭐ and `regressions/0005` **is the record of a mojibake incident** and quotes the corrupted output verbatim inside a fence. ⭐ Auto-fixing all five would have deleted a regression record | ⭐ **A finding is not a defect, and a rule that cannot tell them apart will eventually 「fix」 the one document whose whole job is to be broken.** ⭐ The three dispositions came out different and each is right: ⭐ two prose mentions were rewritten to *name* the character (`U+FFFD`) ⭐ — ⭐ a document about mojibake does not need to contain it — ⭐ and the regression got a **file-level** exemption ⭐ because **every** U+FFFD in that file is evidence, ⭐ which is a true statement about the file rather than a blanket suppression. ⭐ Two follow-ons worth their own lines: ⭐ the **exemption's shape is load-bearing in markdown** (`#` must start the line *and* the reason must end it, so a file-level exemption has to live in a fence) ⭐ — documented in `.ai/checks/static/README.md` §4.4 ⭐ — ⭐ and ⭐ **the test for a rule about a character cannot contain that character**, because the test file is itself in scope, so the fixtures build it with `"\ufffd"` |
| F-178 | ⭐ **I typed the very character I was removing, into the exemption that removed it** | Adding the S-15 exemption to `regressions/0005`, the reason sentence came out 「把这份回归记录␦␦空」 ⭐ — ⭐ two U+FFFD inside the sentence explaining why U+FFFD must not be there. ⭐ The next `python -m checks` run caught it, ⭐ which is the only reason it was caught | ⭐ **The write path is the defect, and a rule about the write path gets violated by the act of writing the rule.** ⭐ Nothing about the file was wrong before the edit ⭐ — ⭐ the edit introduced the thing it was exempting. ⭐ The lesson is not 「be careful」 ⭐ but ⭐ **「put the guard in place before the edit it guards, not after」** ⭐: the rule was already running when this happened, ⭐ and had it not been, this sentence would have shipped. ⭐ The same order matters for a one-line exemption: ⭐ it is the smallest possible self-test, ⭐ and it is free |
| F-179 | ⭐⭐ **一个从未被算过价的批准不是批准，是一个带许可的愿望** | `@milkdown/core` · `@milkdown/react` · `@milkdown/preset-commonmark` 自 2026-09-28 起在 `dependencies` 里，⭐ 是主人批准的（spec 026 §3），⭐ 许可实测 MIT，⭐ V-07 的允许清单里也有它们，⭐ 而**没有一个源文件 import 它们** ⭐ —— **构建出货 0 字节**。⭐ 两天的讨论里没有人算过接上它要多少 ⭐ —— ⭐ 直到为了回答「要不要接」才第一次 build 了两遍：**535.36 kB → 898.18 kB，gzip 164.55 → 275.14** ⭐，⭐ 也就是 **+363 kB / +111 kB，JS 涨 68%** ⭐ —— ⭐ 为了**一个面板**里的一个编辑器 | ⭐ **「主人批准了」是一句关于过去的话，不是一个调用方。** ⭐ 批准解决的是「能不能用」⭐，⭐ 没有解决「值不值」⭐，⭐ 而后者要的是一个数字 ⭐ —— ⭐ 数字一直在那儿，只是没人去 build 两遍。⭐ **所以这类项的下一个动作不是继续讨论，是量** ⭐，⭐ 哪怕只写一个 20 行的探针 ⭐ —— ⭐ 门禁会告诉你探针没编译在哪一行 ⭐（真的：两处 `tsc` 错 ⭐，见 F-182） |
| F-180 | ⭐⭐ **V-07 读的是清单，所以它看不见 import** —— 而 npm 会把传递包提升到根 `node_modules` | V-07 问的是「这个包被批准了吗」，⭐ 方法是读 `package.json`。⭐ 它**不可能**看见另一个方向：⭐ 清单里没有一行说明谁 import 谁。⭐ 而 npm 把传递依赖提升到根 `node_modules` ⭐ —— ⭐ 所以 `import { getMarkdown } from '@milkdown/utils'` ⭐ **能解析、能编译、能构建**，⭐ 而 V-07 一言不发 ⭐，⭐ 因为那个包根本不在 `package.json` 里 ⭐ 而 V-07 只读 `package.json`。⭐ 实测：**68 个源文件、12 个裸包、0 处未声明** ⭐ —— ⭐ 漏洞是**预防性的**，⭐ 但下一个接 Milkdown 的人**一定**会踩 ⭐，⭐ 因为从 typings 读出来的三条读法**全部**在传递包里 | ⭐ **V-16 是 V-07 的另一半，两个方向。** ⭐ 「允许清单」只能回答「能不能」，⭐ 预算要成为预算就得同时回答「有人在用吗」⭐ 与「有人在用没声明的吗」。⭐ 第一条现在**是活的**（Milkdown）⭐，⭐ 第二条现在**是干净的** ⭐ —— ⭐ 而「干净」也是量出来的，不是假设的。⭐ 这也是 V-11 的教训搬到依赖上：⭐ **依赖清单就是一个注册表** ⭐，⭐ 注册表会自己长大 |
| F-181 | ⭐ **一个不豁免的豁免表比没有豁免表更糟** | V-16 的第一个版本建了一张 `APPROVED_BUT_UNWIRED: Record<string, string>` ⭐ —— ⭐ 每个包一条理由 ⭐ —— ⭐ 然后**把三个包照旧报了出来** ⭐，⭐ 只是给其中两个在消息后面附了理由。⭐ 测试红。⭐ ⭐ 危险的地方在于：**它读起来像「这件事被考虑过了」** ⭐，⭐ 于是下一个人删掉这张表 ⭐ 并把问题发出去 | ⭐ **一张不豁免的豁免表训练读者「豁免是装饰」。** ⭐ 修法三件一起：⭐ **有理由的包不报** ⭐（豁免生效）⭐，⭐ **理由为空的不算豁免** ⭐（`CHECK_EXEMPTION_UNREASONED` 的教训 ⭐ —— 留一个字符 `''` 就是让测试变绿的最便宜方式）⭐，⭐ **条目指向已卸载的包也是红** ⭐（否则豁免表自己会变成没人维护的文档 ⭐ —— 而一份没人维护的豁免表会让下一个读者判断「这张表不可信」） |
| F-182 | ⭐ **两个 slice 名字挨着、两件事，而 `tsc` 各抓了一次** | 写 Milkdown 探针时两次写错：⭐ ① `useEditor` 收的是 **getter** 不是实例 ⭐，⭐ 且 `Editor.create()` 是 `Promise<Editor>` ⭐ —— ⭐ 而文档与博客的写法都是 `useState(Editor.make()…)`；⭐ ② ⭐ **`rootCtx` 是 DOM 根节点不是正文** ⭐ —— 它的类型是 `RootType = Node \| undefined \| null \| string` ⭐，⭐ 那个 `string` 是 **CSS 选择器** ⭐，⭐ 正文在 `defaultValueCtx` ⭐，⭐ DOM 节点在 `rootDOMCtx` | ⭐ **从装好的 `.d.ts` 里读，10 秒；猜，两次红。** ⭐ 这与 spec 034 读 `lightweight-charts` 4.x 的类型才避开 v5 的 `addSeries` 是**同一个动作** ⭐ —— ⭐ 本仓已经把它当习惯了，⭐ 这次只是没先做。⭐ 顺带：⭐ 「已批准但未接」的项**第一次要写代码** ⭐，⭐ 于是它的隐藏成本第一次露出来 ⭐ —— ⭐ **API 形状本身就是成本** ⭐，⭐ 而不接线的人从来不会知道 |
| F-183 | ⭐ **模块头部的散话是唯一没有任何测试会检查的文档，而后续提交把它变成假话时是静默的** | `VaultPage.tsx` 的头部注释写着「the body is still shown as source rather than rendered」⭐ —— ⭐ 而**上一个提交刚把正文改成渲染**（自写 `Markdown`）。⭐ 编译过、测试全绿、页面正常 ⭐，⭐ 只有那句话在描述一个已经不存在的版本。⭐ 顺带：⭐ 那句话引用的**不接线理由**（「所见即所得要保证书写和阅读同颜色」）⭐ **它的前提正是上一个提交推翻的那件事** ⭐ —— ⭐ 两边现在都是渲染后的文字 ⭐，「同颜色」已经做到了 | ⭐ **一个模块头部的论断是一个没有人 review 的断言** ⭐，⭐ 而它通常是对**自己所在文件**的断言 ⭐ —— ⭐ 改文件的人和改那句话的人是同一个 ⭐，⭐ 所以 diff 里两句挨着 ⭐，⭐ 而 review 的眼睛看代码不看注释。⭐ 这和 `F-165`（源码断言被自己的注释满足）是同一件事的两端 ⭐：⭐ 那边是**注释满足了断言** ⭐，⭐ 这边是**断言满足于注释** ⭐。⭐ 现在这两句仍然为真的部分**各自点名了一个门禁或一个决定**（V-16 与 ADR-0032）⭐ —— ⭐ 一句散话最该做的事是**指向那个会失败的东西** |

| F-184 | ⭐⭐⭐ **文件走查解析到不存在的目录，于是每一条规则都在迭代空列表并报绿** | `styleguide.test.ts` 的 `SRC_DIR = process.env.SRC ? … : '.'` 在 Windows 上解析失败（实测：`import.meta.url` 的 pathname 是 `/D:/AAA/…`，剥掉前导斜杠后是一个**当作相对路径用的绝对路径**，它不抛错、只是不存在，回退到 `frontend/` 根）。而唯一的样式表在 `src/styles/globals.css`，根目录**一个 `.css` 都没有** → `FILES.filter(f => f.endsWith('.css'))` 是空数组，十一条 `for (const file of CSS)` 的规则**一次都没执行过**。实测：往 `globals.css` 塞一个 `@keyframes`，**三十七条测试全绿**。⚠️ 既有的「扫描不再找到东西时每条规则都靠检查了零个东西通过」写在时长检查下面，**而所有覆盖 CSS 的规则都没有这条语**。 | 【这一类没有新意思的方式，新的是**它发生在一个已经写了「不要空转」的文件里**】**我一边写了那条规则一边没写。守卫必须和它守的东西写在一起：**守卫写在 240 行之后，就没人写**。自查问法：**「我这条规则迭代的列表，它本次运行给出了几个元素？」** |
| F-185 | ⭐⭐⭐ **探针只读一行判词，于是每个**成功抓到**的违规都被报成「没触发」** | `v06_teeth.py` 只用 `re.search(r'Tests\s+(\d+) passed', blob)` 读判词。若期望它发火，虚拟违规会让套件变红，而红的输出里**只有 `· Tests  1 failed | 37 passed` 而没有 `37 passed`」** → `count == 0` → 判词恰好是「没跑」。结果：**四个 case 里有三个确实被规则抓住，而探针报三个「没触发」**。修法：**两行都读**（`Tests  (?:(\d+) failed[^|]*\|\s*)?(\d+) passed`），并且额外断言 `V-06` 确实出现在输出里。⚠️ 分三次才测对，且**第一版写的是「只读了、它报 clean 才对」**。自查问法：**「我的探针在〇**通过**与〇**失败**两种结果下，读的是同一行吗？」** |
| F-186 | ⭐⭐⭐ **探针写的文件不是被测代码读的文件，于是「没抓到」实际是「没写到」** | `v06_teeth.py` 写 `src/index.css`（不存在），而走查读的是 `src/styles/globals.css`。四个 case 全部「fired: False」，而它应当在至少三个。⚠️ **一开始它报的是「规则不有牙」，而真相是探针写错了地方** —— 两种错误报出了完全相反的结论。修法：先 `assert CSS.is_file()` 并把路径打到报告里。自查问法：**「被测的代码读的那个文件，和我写的那个是同一个吗？」** |
| F-187 | ⭐⭐⭐ **`addInitScript` 的注册顺序决定谁赢，而失败的报错看着像组件不存在** | `openWithLaunchPending` 先注册「清除标记」再调 `routeApi`（其内部注册「设置标记」）。实测：**后注册的赢**（先 SET 后 REMOVE → `null`；先 REMOVE 后 SET → `"SET"`）。序列写反 → 确认标记落在最后赢 → 开屏被压住 → **九条测试报 `element(s) not found`，而那条报错看着像组件不存在。** ⚠️ 上一个探针页面自己覆写了那个 key，把三个结论全盖成一个，第一次探针因此给了错的结论。自查问法：**「我对两个顺序敏感的动作，让它们正反跑一次吗？」** |
| F-188 | ⭐⭐⭐ **每个测试是全新 context，但 `localStorage` 是每 origin 的** | 开屏用 `localStorage` 记住「今天看过了」。Playwright 给每个测试一个新 context，但 **`localStorage` 按 origin 共享**，而 `vite preview` 把所有 spec 服务一个地址 → **先看开屏的那个 spec 把标记写了给所有人，后来每一条都失败在「shell 不在屏幕上」**。实测 10 过 101 挂。⚠️ 修法是**深链绕过开屏**（产品修正）而不是给十二个 spec 各加一次 `clear()`（只把套件变绿）。自查问法：**「我这个测试把东西存在了哪里，下一个测试看得见吗？」** |
| F-189 | ⭐⭐ **一个产品特性会静默地拦住所有既有测试，而失败信息指的是别的地方** | 同上。但真正值得记的是成功的形式：**一个新特性上线后，旧 spec 一条都没改，而它们失败的原因与新东西无关**。如果我把这 101 条当成「新功能引入的回归」改掉十二个测试文件，那个回归会永远不能被复现。⚠️ **新测试自己全绿，而旧测试全红 —— 这两个事实放在一起就是线索**。自查问法：**「新东西上线后，有多少个与它无关的测试变红？」** |
| F-190 | ⭐ **选择器前面有个点，而我的正则要求行首 / 逗号 / 空白** | `styleguide.test.ts` 的 L3 带保护重写成 `/(^|[,\s])startup-/`，理由是不让 `foo-startup-x` 计入。结果：**它连 `.startup-hang` 都不认** —— CSS 类选择器前面是一个 `.`。规则第一次运行就把**树里唯一合法的那条 L3**报成违规。修法是**删掉那个边界**而不是改正则。⚠️ 它防的那个碰撞在这个仓里不可能发生（只有一个屏幕用它），而代价是这条规则失去了它唯一的真实对象。自查问法：**「这条规则保护的碰撞，在这个仓里真的会发生吗？」** |
| F-191 | ⭐⭐⭐ **一条未分层的重置简写压过了整把字号尺，而它做的事和它被写来做的事完全一致** | `input, textarea, button, select { font: inherit }` 写在所有 `@layer` 之外。⭐ 实测该文件 `@layer` 出现 **0 次**，所以这条重置是未分层的，⭐ 而**未分层规则在同等特异性下压过每一个分层规则** —— 也就压过了 Tailwind 的 `utilities` 层，`@utility` 字号类全在那里。实测：`type-page-title` 单独用 22px，挂在 `<button>` 上 **13px**，按钮 `53x20`，**与加这个类之前逐字节相同**。⚠️ **为什么没人发现：因为每个控件本来就都是 13px**（body 的字号），重置在做的事完全正确，没有一处看起来是错的 —— 缺陷只在**本来该不一样大**的控件上可见。⭐ `V-12` 抓不到：它扫组件里手写的 `text-[NNpx]`，而这里是**样式表的简写赢掉了一个组件确实写了的类**。与 `.mark`（`status.md` §〇，36 个元素要一个它没有的颜色）同族。详见 `regressions/0014`。 |
| F-192 | ⭐⭐⭐ **媒体查询是条件，不是优先级** | `.startup-copy { align-self: stretch }` 写在 `@media (min-width: 1180px)` 里，而那个块在**被覆盖的 `.startup-copy` 规则上面**。实测：出口停在 y=481、署名停在 y=531，**逐像素不变 —— 什么都没动**。根因是 `@layer` 出现 0 次：**没有分层时，未分层规则只按位置排序**，同特异性下靠后的赢。⚠️ **这是 F-191 的同一个根因**，只是这次赢的是位置而不是层。⭐ 修法选了「把覆盖挪下去并写下为什么」而不是「整体分层」，因为**整体分层是独立改动，与布局修复放同一条提交会让修复本身读不懂** —— 所以「我这次选了局部修法」必须写下来，否则三年后的人会以为位置顺序就是这个项目的层叠模型。详见 `regressions/0015`。 |
| F-193 | ⭐ **百分比套在自身宽度由内容决定的盒子上，是一个循环测量，而浏览器会用一个中间值把它解掉** | 画框 `width: fit-content`，里面的画 `max-width: calc(100% - 80px)`。实测画 **477px**，而算式说该是 559px：浏览器把这个百分比解析成了 **557** 而不是框的 639。后果是画比算式小了 80px、框比装裱需要的多出 80px。⭐ **修法是让每个长度都有确定依据**：框取栅格轨道的宽度（**确定的**），画取 **vh** 的高度上限 + 框的 `100%` 宽度，于是没有一个百分比是循环的。⚠️ 同一处还量出**三次更差的版本**：v1 框 1.25 : 画 1.27（**框和画几乎同比例，所以它读起来是贴上去的一张图**）；v2 框填满列且定高 ⇒ 横卷配了一个**竖框**，上下各 90px 死白。⭐ 三次都不是靠眼睛否掉的，是靠「框与画的比例必须明显不同」这个量。 |
| F-194 | ⭐⭐⭐ **`min-height` 是地板，而被禁止滚动的祖先会把超出部分裁掉 —— 于是内容在 DOM 里、在渲染树里、测试全绿，读者拿不到** | 开屏是 `min-height: 100%`，而 shell 给 `body` 设了 `overflow: hidden`。实测 900×800：`scrollHeight` 1026 对 `clientHeight` 800，画框顶边 318、署名顶边 **962（超出 162px）**，而**没有任何东西能滚动**。⚠️ **这一条穿过了本仓除一条以外的全部机制** —— 静态检查 11 项、前端 216 条、E2E 112 条全绿，⭐ 因为 **Playwright 的 `toBeVisible()` 是几何的**：元素在渲染树里、有非零盒子，就算绿；**它在屏幕内吗，它问不到**。所以 `hangs the painting whole` 也是绿的：⭐ **它量的是一幅没人看得见的画的宽高比**。⇒ 它不是靠聪明发现的，是**靠在一个 900×800 的窗口里手动量发现的**。修法：开屏必须是自己滚动的那一层（`height: 100%` + `overflow-y: auto`）。详见 `regressions/0016`。 |
| F-195 | ⭐⭐ **「我量了，所以我对」是把测量当成了验收** | 开屏第五版让左栏 `stretch` + `space-between`，**意图确实实现了**（日期落在画框顶边、署名落在底边，数字对得上），而**设计失败了**：左栏被拉成 `480x796`，中间三个约 200px 的洞 —— **四行字铺在 796px 上是四个碎片，不是一个陈述**。⚠️ 同一个形状的另外一面是 F-194：那次数字**没有**量，所以缺陷藏住了。⭐ **差别在于：F-194 需要「多测一个尺寸」，F-195 需要「测完之后再看一眼结果长什么样子」** —— 数字正确和视觉正确是两个断言，而截图只花几秒。⇒ 本轮至少四次截图自查推翻了「数字正确」的方案（装裱过度、画被压小、三个洞）。⚠️ 而且**这一条故意没有门禁**：「四行字不该铺成 796px 高」是审美判断，写成断言就是一条谁都不敢改的假门禁；⭐ 但**回退的理由和留下的理由一样需要被记下来**（两栏中心相差 14px = 屏高 0.7%，明确记为不追）。详见 `regressions/0017`。 |
| F-196 | ⭐⭐⭐⭐ **我用探针往主人真实的库里写了一行，而防这个的开关就在手边** | 2026-10-01 查歧义代码那条路时，我用 `POST /watchlist {"ticker":"600519"}` 打到了 `%LOCALAPPDATA%\AlphaCouncil\alphacouncil.db`，理由栏写着「探针」。⭐ **`ALPHACOUNCIL_DATABASE_PATH` 就是为了这个而存在的**（第一段计划里写的「独立路径的演示库」），**而我没设**。⚠️ 而我写这个探针的理由是「只读探针和写探针在同一个脚本里，顺手一起发」—— ⭐ **同一个脚本不是同一个权限**：前面五个请求全是 GET，第六个是 POST，**而我没有在第五个和第六个之间停下来看一眼自己正在对谁说话**。⇒ 已用产品自己的 `POST /watchlist/remove` 撤掉（**没有 `DELETE` 是有意的**），`watchlist_current` 复查只剩主人那一行（600036）。**只增不改的日志里留下 event 15/16**，理由写着「探针写入，不是读者的记录」—— ⭐ **删掉它们就是篡改历史，这是这个产品对「记录不可改」最直接的一次应用，连对我自己**。↳ **规则：任何可能带写操作的探针，整个脚本都必须带 `ALPHACOUNCIL_DATABASE_PATH`** —— 不是「写的那几行带」，是整个脚本，因为**判断哪一行会写，比多写一个参数贵得多**。 |
| F-197 | ⭐⭐⭐⭐ **表单里一个没有 `type` 的 `<button>` 就是 submit 按钮，而这不是 Tailwind 的默认也不是 React 的** | 给关注池写歧义选择器（spec 047）时，两个市场按钮的职责是「**把提交按钮武装起来，仅此而已**」。实测：
```
  填 000001、填理由、按「加入关注池」   -> 选择器出现，0 个 POST   ✓
  点「上交所」                       -> **1 个 POST**        ✗
```
点一下就把一条**不可改的**关注记录写了：按钮触发表单提交 -> `handleSubmit` 重跑 -> 因为 `picked` 还是 `null` 又解析了一次 -> 又得到 ambiguous -> 表单被清空禁用。⇒ **探针报出来的症状是「第二个按钮点了没反应」，距离原因三十秒。** 根因：`Button` 继承 `ButtonHTMLAttributes` 后把 `{...props}` 直接透传，**`<button>` 无 `type` 时默认 `submit` 是 HTML 规范**。⚠️ **bug 是我写的，而坑是组件的** —— 下一个人把两个按钮放进表单也会踩。↳ 修法两条：`Button` 默认 `type='button'`（**动手前实测四个表单全都已经显式写了 `type="submit"`**，所以这个默认值不破坏任何东西）+ **`V-19` 守「每个 `<form>` 必须显式声明 submit」**，否则改默认值就会静默弄坏一个表单。⭐ **`V-19` 的变异 M2 才是关键那条**：给选择器按钮显式加上 `type="submit"` 而**保留**组件的修复 —— `V-19` 的组件那半条如实地绿了，**而 A2 变红**。**撤销修复只能证明门禁记得那行；重建缺陷的形状才证明门禁理解那个形状。** |
| F-198 | ⭐⭐⭐ **Playwright 的路由处理器「后注册的赢」，而我把它当成了「后注册的补上缺的」** | `e2e/fixtures.ts` 的 `routeApi` 每调一次就 `page.route()` 一次，于是**测试里第二次调用会把 `beforeEach` 整套悄悄扔掉**。症状是四条失败，**每一条都读起来像产品坏了**：
| F-199 | ⭐⭐⭐⭐ **一条已经存在的能力，可以只靠写代码用上** | 复习队列（spec 048）量到的：卡片**只能靠写代码进队列**。对着空库量：`POST /api/v1/cards` -> 201；`GET /api/v1/review/due` -> **0 条**（服务端不主动贡献任何东西）；`POST /api/v1/cards/{id}/schedule` -> 201；再查 -> **1 条**；`grep scheduleCard` -> `api.ts:282` 定义、**零调用者**。⚠️ 而笔记的是 **空的**（本仓已经遇过三次）：`J3` 的「机制齐了却笼不着」、零调用者的 `listNoteReviews`、`RecordTimeline` 的两个实现。⇓ **笔记上悬了很久的缺口不可能长成那么无感，而只要没有人去验证它就会** —— `status.md` 开头那句「凡『还差什么」要靠读代码确认」写了之后，第一次被真正用上就是这一次。⭐ **而真正的缺口不只是按钮：`GET` 端点当时不存在**，界面既不知道一张卡在不在队列里，**也不能从 `/review/due` 推断**（它只给**到期**的，排在下周三的卡不在里面）。⇓ “只能靠点完才知道结果”的按钮是一个赌注。 |
| F-200 | ⭐⭐⭐⭐ **一条测试因为「它经过」而永远变绿，而变绿的原因与它声称测的无关** | spec 048 的「已收敛的卡片不给入队按钮」那条，**第一版没有 stub 那个 schedule 读请求**，所以读走了 404 →控件落进「不知道」态 → **按钮不出现并不是因为收敛了**，而是因为读失败了。于是变异 **M3（删掉 `!converged` 守卫）没有让它变红** —— **它空跑了一个不存在的缺口。⇓ 修法：**把读请求 stub 成 409 `CARD_NOT_SCHEDULED`**（按钮在一个点击之差），完成后 M3 立即变红。⚠️ 这是本会话第二次「少了一个 stub 所以永远变绿」——第一次是 `0012`（CSS 扫描迭代空列表）。⇓ **当一条测试的「不应该绿」需要一个能提供绿的状态时，它往往已经绿了，而且永远不会红**。 |
| F-201 | ⭐⭐⭐ **探针的转发层能让产品看起来像有错，而真过的错在探针里** | 2026-10-02 验证入队控件时，两个探针失败都是探针的，而产品是对的：① 转发对所有方法都用 `p.request.get()` → **入队的 POST 被用「读」的身体回答了**，点一下看起来像失败；② 为了测「读失败」而注册的 abort 路由写在通用路由**之后**，被后注册的守守归零—— ⚠️ **这正是 `F-198` 在探针里重现一次**（Playwright 后注册的赢）。② 等待时间到期的时候把读结果键在 `submitting` 上，快写时它是一帧闪烁、慢写时它根本不在。⇓ **探针必须转发真实的 method 与 body，而不是自己发明的那个**；拓扑的一个误会把产品的正确行为报成错误。 |
| F-202 | ⭐⭐⭐**一条只认单行形状的正则，会在多行形状上安静地报「没有漂移」** | `S-16` 的 `UNION` 第一版是 `^\s*type\s+(\w+)\s*=\s*(.+?)\s*;?\s*$`，而 `api.ts:533` 的 `MetricState` 是**一行一个值**。实测后果：全仓被镜像得最多的那个联合类型它看不见，于是 `CriterionVerdict` 被报成「前端没有镜像」—— ⭐ **而镜像就在那里，只是换了名字（`MetricState`）**。⚠️ 我把「可被格式化骗过的规则不是规则」这句写进了它自己的 docstring，然后自己骗过了自己。⭐ **漂移检测器在自己该抓的东西上报干净，比没有检测器更坏，因为它被信任。**⇒ 联合类型正则是拿十种形状探测的，**其中两种是它必须不匹配的**（`type X = SomethingElse` 与 `interface`） |
| F-203 | ⭐⭐**一个字典装两种豁免，「它还在吗」就有两个意思** | `FRONTEND_ONLY`（前端概念，没有后端对应）与 `NOT_MIRRORED`（后端枚举，前端**故意**不镜像）第一版放在同一张表里，而存活检查问的却是两件事：前者问「**前端联合类型**还在吗」，后者问「**后端枚举**还在发布吗」。实测：一次干净的树上跑出 6 条「已豁免但不再声明」—— 因为一个前端从不镜像的后端枚举**永远不可能**有联合类型可找。⭐ 规则没有判断错任何东西，**是它自己的数据模型错了**，而且输出把这件事说得足够响，形状一眼可见 |
| F-204 | ⭐⭐⭐**用错键匹配的豁免，等于没有豁免** | `NOT_MIRRORED` 第一版按**值的集合**去匹配**前端联合类型**。而这个字典里的每一项都是「后端发布了、前端不镜像」，**按定义就没有联合类型可匹配**。⇒ 干净树上 6 项全部被报成漂移。⭐ 三张豁免表现在按三个不同的键匹配，而这不是不优雅，**这就是它们的区别**：`NOT_MIRRORED` 按名字对后端、`FRONTEND_ONLY` 按值集合对前端联合类型 |
| F-205 | ⭐⭐**一条规则里两次照着没读过的 API 写，于是它崩了两次** | ① `ctx.frontend` 不存在（`ScanContext` 只有 `repo_root` / `backend` / `product`）—— **更深的错不是缺属性**，而是 `S-07/08/09` 已经依赖框架对「什么算前端源文件」的回答，再写一份遍历就是**两个地方决定同一件事**，正是这条规则要抓的形状，由抓它的规则犯下。② `result.files` 装的是**文件**，塞目录进去会让 `apply_exemptions` 读它时抛 `IsADirectoryError`。⭐ 两次都不是逻辑错，都是我没读就写 —— 与 `0008`（猜主键叫 `id`）、`0019`/`0020`（猜枚举）同类。框架自己的判词两次都成立：**崩溃与通过无法区分** |
| F-206 | ⭐⭐**断言「文件里没有这句话」时，文件里的注释也是命中** | `ratings.test.ts` 断言 `timelineAdapters.tsx` 不持有那八个标签中的任何一个，结果它挂在 `OUTCOME_LABEL` 的注释上 —— 那条注释在解释为什么 `deferred` 不叫「延期」，正因如此它必须引「我的想法变了」。⇒ 断言的**范围是代码**，所以读文件时剥掉注释；⭐ **而不是把断言放宽成「出现在注释里就算了」** —— 那等于把三份拷贝全部放行。⚠️ 剥注释的实现要跟踪字符串状态：`'//'` 在 URL 里不是注释，天真的剥法会把行尾之后全删掉，**把一个通过的文件变成看起来干净的文件，因为它被截断了**（`0003` 的形状） |
| F-207 | ⭐⭐**一条测试钉「等于表里写的」，就抓不到「表本身是错的」** | `ratings.test.ts` 的变异 M2：改 `NOTE_RATINGS` 自己的措辞，测试**依然绿**。⇒ 这是**记录在案的边界**，不是缺陷：一张表内部的措辞是产品决定，不是漂移；而**表被重新抄一份**（M1）测试红 3 条。⭐ **知道自己哪些断言是哪一种，是一道门禁和一件装饰品的区别。** 原漂移之所以被抓到，是因为 M1 重新引入了一个**字面量**，而字面量就是第二个家 |
| F-208 | ⭐⭐**一条非贪婪正则匹配不上时是静默的空操作，而文件看起来像被改过** | `re.sub(r"function ratingLabels\(.*?\n\}\n\n", ...)` 没匹配上，脚本在写盘前assert 失败退出，文件保持原样。⚠️ **唯一发现它的是那个 assert** —— 若 assert 没写，这一轮会带着「已经改过」的印象往下走。⭐ 这与 `regressions/0012` 是同一个形状：**一个静默找到零条的扫描，和一个正确找到零条的扫描看起来一模一样。**⇒ 改为按行走，先找 `function`，再删到第一行恰好是 `}` |
| F-209 | ⭐**一条会在正确输出上触发的守卫，会被删掉 —— 然后问题就没人回答了** | `assert "RATING_LABEL[review.rating]" not in text` 在**改对之后**触发了，因为 `NOTE_RATING_LABEL[review.rating]` 的尾巴正是它要找的那个子串。⇒ 修法是加词边界，**不是删守卫**：删掉它，「接线到底改了没有」这个问题就永远没有答案。⭐ 字面上就是 `V-19` 那一类：守卫要守形状，而不是守拼写 |
| F-210 | ⭐**一条写着本项目没启用的规则名的 `# noqa`，是一个没人核对过的声明** | `except Exception as exc:  # noqa: BLE001` —— `pyproject.toml` 的 `select` 里没有 `BLE`，`RUF100` 把它标为 unused。⭐ 我是照着习惯写的，**而 `RUF100` 的存在就是为了发现这类没核对过的声明**。⚠️ 顺带一处口径不一致：我给 `error_codes.py` 写的中文注释里带全角「：」，`RUF003` 报了出来 —— 该文件相邻的注释是英文，于是改成英文而不是新增一条per-file 豁免：**能不改豁免面就不改** |
| F-211 | ⭐⭐⭐**一条承诺「会编译报错」的注释不是那个编译报错** | `routing.ts:201-203` 写着 「Exhaustive over `QueueName` **by construction** — adding a queue server-side without adding a route here is a compile error」，而代码是三元 `queue === 'cards' ? REVIEW_HREF : RETROSPECTIVE_HREF`。⚠️ **三元对联合类型不做穷尽** —— 加第三个队列它照样编译通过，**这条注释承诺的编译错误从来不存在**。⇒ 改成 `Record<QueueName, string>`，承诺变成真的。⭐ **而承诺要测不能信**：M1（`Record` 抓到了）与「M2 换回三元同一变异通过」是一对 —— ⚠️ **只有 M1 时，「Record 修好了」与「tsc 本来就会抓」完全无法区分；M2 绿，正是旧代码从来没有那个保证的证据**。这是 `0005`（文档断言代码不做的事）与 `0011`（标题比它的检查宽）**穿着注释的外衣再来一次** —— 而它最容易发生的地方，恰恰是**刚改完、正觉得 obviously right 的时候** |
| F-212 | ⭐⭐⭐**一个把几乎全部报成坏掉的静态扫描，在描述的是它自己** | `S-17` 第一版：「46 个调用点 · 漂移 46」—— 而前端**完全正确**，后端一侧只有 **1** 条路由。⚠️ ⭐ **这是这条规则唯一一次真正的缺陷，而且不是逻辑错，是失败比例本身不可能**。**四次手搓的版本（26 个孤儿 · 0/36 可达 · 12 · 11）每一次错误都长得像这个**，而没有一次有人问「这个失败比例可信吗」。⇒ 规则加了 `PLAUSIBILITY_FLOOR`：超过 34% 就**跳过并说明「那是关于扫描器的事实，不是关于前端的事实」**。⚠️ 而**跳过的规则不是通过**（`--strict` 下退出码 1）⇒ **它既拒绝指控，也拒绝放行** |
| F-213 | ⭐⭐⭐**`app.routes` 上有一批 `path` 为空的项，于是「遍历路由表」默认会丢掉全部路由** | 本仓 FastAPI 版本下 `app.routes` 16 项里 **12 项是 `_IncludedRouter`、`path` 为空串**。一个 `if not path: continue` 的遍历把它们全丢掉，只剩 `/health`。⚠️ **这就是 `0012` 的形状**：静默找到零条与正确找到零条看起来一模一样。⚠️ 而要够到它们得用私有属性（`original_router` / `include_context`）—— **那是框架内部实现，升级就会动，而一条建立在私有属性上的门禁会把升级报成漂移**。⇒ 读 `openapi.json`：**路径是 FastAPI 自己算的**，⇒ 「我忘了前缀」这一整类错误**不是被处理掉，而是无法发生** |
| F-214 | ⭐⭐**一个断言「文件里没有这句话」的检查，必须先说清它读的是代码还是散文** | ⚠️ 本轮第三次撞这一类，但这次是反向的：`ratings.test.ts` 断言 `timelineAdapters` 不持有那八个评分标签，而它挂在 `OUTCOME_LABEL` 的注释上 —— 那条注释在解释为什么 `deferred` 不叫「延期」，正因如此它必须引那一句。⇒ 断言的**范围是代码**，所以读文件时剥注释，**而不是把断言放宽成「出现在注释里就算了」** —— 那等于把三份拷贝全部放行。⚠️ 剥注释的实现要跟踪字符串状态：`'//'` 在 URL 里不是注释，天真的剥法会把行尾之后全删掉，**把一个通过的文件变成看起来干净的文件，因为它被截断了**（`0003`） |
| F-215 | ⭐⭐⭐**我的变异写错了，而正确的做法是先证明「测试错了」再去改规则** | spec 050 变异 M4：把调用从 `/api/v1/notes/due` 改到 `/api/v1/notes/tags` 并期望红 —— **而 `GET /api/v1/notes/tags` 真的存在**，这个变异只是把一个调用变成重复调用，**规则绿是对的**。⚠️ 而「测试错了」是最诱人的结论 ⇒ 处理方式不是改规则也不是改测试，**是先把变异改成一件结构上不同的事（多一段）**。⇒ **MISMATCH 是信息，不是失败** |
| F-216 | ⭐⭐**用了记得的字符串而不是读过的字符串，于是脚手架说「自检没触发」而它触发了** | 变异 M5b 的判据找的是 docstring 里的措辞「that is a fact about the scanner」，而**跳过消息里那句首字母大写**（前面跟着 `⭐ `）。⇒ 自检其实触发了，脚本报了 MISMATCH。⭐ 这与 `0019`（fixture 第二次调用丢掉第一次）同一类：**判据本身错了，而判据是用来判断对错的** ⇒ 改为检测运行器自己的 `[SKIP ]` 标记。⚠️ **一个判据写错、且错的方向与它要找的缺陷相同的脚手架，比没有脚手架更坏**，因为它给出一个没有含义的绿 |
| F-217 | ⭐⭐**一段 (文件, 锚点) 表格是关于这棵树的断言，而它必须对着树核对，不能靠记得** | 变异脚本的 `BREAKABLE` 表里第五个锚点属于 `notes.ts` 而表里写的是 `API` —— `assert` 当场抓住。⚠️ 同类：`M5` 的说明写「破坏一半调用点」而实际只破坏了 5 个，**5 / 46 = 11% 远低于 34% 的阈值**，⇒ 自检当然不触发。⭐ **「一半」是心算而不是测量**，而本轮第一次跑 `S-17` 时我报的是「46 / 46」。⇒ 断言锚点存在，是这类表格唯一便宜的保险 |
| F-218 | ⭐⭐⭐⭐**「找不到东西」与「找不到东西是因为我坏了」必须能分开，否则同一个形状会第四次重来** | `0012`（CSS 扫描迭代空列表）· `F-202`（只认单行的正则）· `F-208`（非贪婪正则静默空操作）· **`F-213`（`app.routes` 上 path 为空的项）** —— ⭐ **四次，四种完全不同的入口，同一个后果：一次扫描报告零条，而读的人分不清那是对的还是错的。** ⇒ 本仓现在有三种机制分开它们，且都已在 spec 049/050 里落地：**① `CheckResult.skipped` 不是一个通过**（`.ai/checks/README.md` 维护规则 3）；**② `S-17` 的 `PLAUSIBILITY_FLOOR`** —— 失败比例不可信时规则拒绝下结论；**③ 变异检查**（`regressions/README.md` §五）—— **撤销修复只证明门禁记得修复，重建缺陷的形状才证明门禁理解形状**。⚠️ **这三条都不是新的**，而前四次仍然发生了 —— ⇒ 结论不是「再加一个机制」，而是**机制齐了也不等于够得着** |
```
  A2  「已记录（事件 #99）」 element(s) not found
  A6  expected "is not a six-digit code"
         received 「请求被拒绝（HTTP 400）」
       expected "'zzz' is not a six-digit code"
         received 「请求被拒绝（HTTP 404）」
  pool.spec.ts 同款失败
```
⚠️ **400 是 `routeApi` 自己「你传了个裸状态码」的分支，404 是它「e2e fixture missing for …」的分支** —— **fixture 自己的诊断信息，以产品句子的形状出现在失败输出里，这是最坏的位置**。⇒ 已改成**每页一份、累加**，路由只注册一次。⭐ 而这条机制**本仓已经量过两次**，在另一个地方：`addInitScript` 「后注册的赢」写在 `launch.spec.ts` 的注释里，**写反过一次，代价是 101 条测试失败**。⚠️ **同一个规则、同一个方向、在第三个地方又踩一次 —— 因为三处的注释互相看不见。**⭐ 顺带修的：裸 `400` 那个用例本身也是错的（**空 400 就该只有「请求被拒绝（HTTP 400）」，那是 `request()` 的正确行为**，是我的 fixture 在冒充服务端），所以补了 `{ status, body }` 这种「带真信封的拒绝」。↳ **A6 那条现在断言的是透传**：服务端那句英文**原样显示且不翻译**（spec 047 §3.4），翻译它就要在前端维护一张错误码表，**而那张表会和 `api/errors.py` 漂移 —— `S-05` 只保证文档↔枚举↔代码那三方，前端那一份没有这个保证**。 || F-219 | ⭐⭐⭐**测量用错了尺子，拿到的数字照样像是对的** | `len()` 数码点、`ruff` 数显示宽度；中文横字 1 码点 / 2 列，同一行 92 vs 102。⭐ **我的脚本报了「0 行超过 100 列」—— 有格式、有信心、关于一个没人问的属性** | → 写包装之前先确认工具量的是什么 |
| F-220 | ⭐⭐⭐**结论已经在文件里，我还是把它生产出来了** | 三个脚本要给 `criterion_sentence.py` 加 `RUF003` 封封，而那一行 **spec 044 就在**，连下一行 `financial.py` 都记着「这个仓的答案是不封封、改用 ASCII 标点」。⭐ `F-218` 的形状推上一层：**问答可达，而一条门禁不能拦一个从未被测试的错结论** | → 写脚本前先读那一段 |
| F-221 | ⭐⭐**行的前缀不是行，把代码插进了语句中间** | 两个脚本锚在 `from … import` 的**前缀**上插入，而那是多名 import 的一部分，文件因此不再是 Python。两个次，两个脚本 | → 只在**整行**后插入，定位用行尾而不用子串 |
| F-222 | ⭐⭐**拿「看着像那件事的东西」当检查** | `assert "domain/criterion_sentence.py" in text` 报了封封已存在，而那个路径在文件里别处就出现过。⭐ **今天第三次「检查了不对的那个东西」而让错结论通过** | → 一行配置是 `key =`，不是 `key` |

| F-223 | ⭐⭐**一个 changelog 的一句话被我读成了端点的边界，而端点就在本机** | baostock 帮助文档的更新日志有一句「新增2006年01月-2018年09月指数成分股数据」，我据此推断「成分股数据只到 2018-09」，并把一个**不存在的缺口**当成待决问题报给主人，还据此提了三个方案。⚠️ **实测否证**：`2018-10-31` / `2024-03-15` / 今天各返回完整 300 条。⇒ 那句话说的是**这一大类数据的起始**，不是**这个端点的截止**。⭐ 与 `data-sources.md:138` 是同一条：都是我拿二手描述当一手事实。⭐ **判据**：.ai 文件里的每一条限制，落地前必须在本机打一次那个端点 —— .ai 记的是**别人的实测**，不是这个端点的实测 |
| F-224 | ⭐⭐⭐**「吻合」不是「定义」：一个字段在 N 个已知真值上都对，第 N+1 个样本仍可能推翻它** | baostock 成分接口的 `updateDate`：探针 `2025-06-16` → `2025-06-16`，`2025-12-15` → `2025-12-15`，**两次都精确等于《沪深300 指数编制方案》说的生效日**。⭐ 我当时的判断是「它就是生效日，可以当 `effective_from`」。⚠️ **而第五个样本 `2025-07-11` → `2025-07-07` 就推翻了** —— 那天是周一，不是任何调整日。⚠️ 真正的形状：**五个 `updateDate` 全是周一**，它是每周一批的入库戳；前两次「吻合」只因为那两天的生效日本身落在周一。⇒ 差点建出来的一列是**一个意思是我推断出来的数据源字段**。⭐ 判据：**用来定量的字段，必须有一个样本能证伪它的定义，而不只是与它吻合**；吻合次数不构成证据 |
| F-225 | ⭐⭐**「成功」不是「有数据」——而这一次，`F-218` 那个家族的同一个形状是第五次** | `query_hs300_stocks('2007-07-23')` 返回 **`error_code='0'`（成功）且零行** —— 四周后那个周一没有入库批次。⚠️ 而同一个函数在别处还返回过 `WinError 10053`（连接被中止）与 `error_code='10002007'`。⭐ 若把零行读成「那天没有成分」，写进去的就是**「沪深300 有 0 只成分股」** —— 一个荒谬值，而**它不会让任何地方报错**。⚠️ `F-218` 已归纳过同形状四次（`0012` / `F-202` / `F-208` / `F-213`），**这是第五次，而入口是数据源不是代码**。⇒ 三条机制照样管用：摄取契约写成**类型**（失败不产生行，而不是失败产生「空集」行）、`failures` 计数**落库**而不是打日志、每条 `SKIPPED` 带原因。⭐ 结论要推一层：⭐ **`F-218` 说过「机制齐了也不等于够得着」——这次的补充是：入口可以是网络，而网络的失败形状比文件多** |
| F-226 | ⭐⭐⭐**八个名字/形状的猜测，每一个都被断言抓住，没有一个是我看出来的** | 一个会话里猜了：import 路径 ×2（`alphacouncil.providers._baostock` 写成不存在的形式）、import 形状 ×2（把单行 `from ... import ErrorCode` 写成多行）、模块成员（`context.context` 而它就是 `context`）、依赖（`deps.get_connection` 而真名是 `DatabaseConnection`）、签名（`rollback(database_path=)` 而它没有这个参数）、helper（`INSTRUMENT_HREF` 而真名是 `instrumentHref`）。⚠️ **六次在同一个小时内。** ⭐ 危害不是猜错 ⭐ **是「我读到了那一行却仍然按路径猜」** —— 有一次那一行 import 已经打印在我自己的输出里了。⇒ **断言是唯一起作用的东西**，所以纪律是**先写断言再读文件** ⭐ 代价是每次多一行 ⭐ 而这个代价我八次都没付 |
| F-227 | ⭐⭐⭐**一个占位符不是一次暂停，它是一行在两种读法下含义不同的东西** | 一个星号加等号再加 None 作为占位符，在一个会话里出现 **5 次** ⭐ 每次都是语法错误 ⭐ **代价是整个函数重写，其中两次。** ⚠️ 而如果它活进了一个**被写盘的文件**，那就是一个什么都不表示的行留在出厂代码里。⭐ 根因是我把「我马上要填」与「我写了」混为一谈 ⭐ 而本仓已经有答案：**写到 write 工具里的文件用字面字符，走 PowerShell 的才需要转义** —— 而三 位十六进制的 u 转义（那种不是 4 位的）**在两个脚本上各犯一次，在本条目自己身上又犯一次** ⭐ **而 PowerShell 根本没有 u 转义** ⭐ **所以「能用」的那个转义恰恰是静默匹配不到东西的那个** |
| F-228 | ⭐⭐**穷举性与元素新鲜度是两件事，而只有后者会在门禁里露出来** | `App.tsx` 六个并列三元换成 `Record<RouteName, ReactNode>` ⇒ **`tsc` 过、`vitest` 过、E2E 挂在 `strict mode violation: getByTestId(...) resolved to 2 elements`** —— 复习页挂了两份。⭐ 原因：三元每次 render 产生**新**元素对象，React 靠它卸载旧子树；⭐ 而模块级常量元素**永远复用同一个对象** ⇒ 旧子树从未拆掉。⇒ 修法是 `Record<ViewName, () => ReactNode>` —— **thunk 而不是元素**。⭐⭐ **「加了视图而忘了页面」从零红变成编译错（可固化），而「重复挂载」没有任何测试守着** —— 它是被 nav/palette 那两条既有 e2e 靠 Playwright 的 strict 模式撞出来的 ⭐ **症状在三个文件之外**。详见 `.ai/regressions/0026` |
---


| F-231 | ⭐⭐ **用「另一个进程」验证「我改的代码」** | 连 `curl` 三次都拿到旧形状；`Get-NetTCPConnection` 报 8000 的 owner pid **不存在**，而磁盘上的代码、editable 安装、`inspect.getsource` 三处都是新的 | "**进程/端口层面的事能能证明代码对吗？**" —— 让**被测代码自己**回答（进程内断言），或让服务自报版本；**端口表只说明有人在听** |
| F-252 | ⭐⭐⭐ **一个 hook 的依赖数组里放了一个每次渲染都变的东西，⭐⭐ 而三个 reporter 都只说「超时」** | `useResource` 的 `useEffect` 依赖是 `[...deps, describeError]` ⭐⭐ 而我传了一个**内联箭头** ⇒ 每次渲染重跑 `run()` ⇒ `publish()` ⇒ 再渲染 ⇒ **无限循环** ⭐⭐ 实测：`card-enrolment.spec.ts` 的 **A4 / A5 各超时 30 秒**，⭐⭐ 而 `line` / `list` / `json` 三个 reporter **都只打印「Test timeout of 30000ms exceeded」—— 没有栈、没有行号、没有断言名** ⭐⭐ 最后靠 `git stash` 单文件**二分**出来 | ⭐⭐⭐ *「这条超时是**慢**，还是**永远不会停**？⭐⭐ 而报告有没有区分这两件事？」* —— ⭐⭐ **它没有。** ⇒ 修法两层：⭐ 调用点改 `useCallback`（与所有既有调用点一致）⭐⭐ **并且把 hook 本身修好** —— `describeError` 与 `fetcher` 一样走 ref 读，⭐⭐ `deps` 重新成为「唯一能重新发请求的东西」，⭐⭐ **而那正是这个 hook 头部早就写着的那句话。** ⇒ ⭐ **代码现在与文档一致，而不是反过来。** |
| F-253 | ⭐⭐⭐ **`reuseExistingServer` 让顺序跑的变异互相污染，⭐⭐ 于是同一个变异两次运行两个结果** | `playwright.config.ts` 有 `reuseExistingServer: !isCI` ⭐⭐ 本地 `true` ⇒ 第二次跑复用的是**第一次已经构建好的 bundle** ⭐⭐ 实测：把卡片的 `deferred` 措辞改成「延期」，**E2E 一次红（报 B1）一次绿** ⭐⭐ 而两次都不是谎话 —— **一次量的是这次的产物，一次量的是上一次的** | ⭐⭐⭐ *「两次跑出来不一样，⭐⭐ 是我改了两次，还是我只改了一次？」* —— ⭐ **`git diff` 答不了，而产物答得了。** ⇒ 每次跑之前 ⭐⭐ **`grep dist/assets/*.js` 找变异标记**，⭐⭐ 找不到就判 **VOID** 而不是判绿（`F-140` 上移一层）。⇒ ⭐⭐ **结论：这台机器上 E2E 不是源码级改动的可靠裁判**，⭐⭐ 所以 spec 055 的三条红线守卫全部写成**值断言**（不开浏览器、不构建）—— **裁判不可靠的门禁比没有门禁更坏，因为它看起来像门禁。** |
| F-254 | ⭐⭐⭐ **一个让构建失败的变异，被当成了一次「通过」的变异** | 标色那条变异写成 `tone: (…) as const` ⭐⭐ 而 `as const` 不能用在条件式上 ⇒ **`TS1355`** ⇒ `npm run build` 失败 ⭐⭐ ⇒ 那个用例**根本没有产出过产物** ⭐⭐ 而我在第一轮把它记成「E2E 绿」 | ⭐⭐⭐ *「这次变异跑完了吗，⭐⭐ 还是它根本没跑起来？」* ⇒ 三种结局不是两种：⭐ **RED · GREEN · VOID** ⭐⭐ 且**「构建失败」必须单独一档** —— ⭐⭐ **把它算成绿色，等于对一个不存在的实验下了结论。**（`F-140` 的形状，而 `spec 054` 已有四条同类） |
| F-255 | ⭐⭐⭐ **一个只禁「时长」的守卫，⭐⭐ 第一版断言了错误的物体，⭐⭐ 绿着放过了它本该抓的那条** | 红线 11 的第一版守卫断言**导出的标签表**（`CARD_OUTCOME_LABEL` 等）⭐⭐ 而时长是印在 `detail` 那个**模板字符串**里的 ⭐⭐ ⇒ 变异「把 `duration_ms` 印进 detail」**绿** ⭐⭐ | ⭐⭐⭐ *「这个守卫检查的是**读者会看到的那个东西**，⭐⭐ 还是它旁边那张表？」* —— ⭐ **`ratings.test.ts` 的警告在一个新地方重演：「值断言看不见在离它一行远的地方拼出来的字符串」。** ⇒ ⭐ 导出两个 **builder**，⭐⭐ 断言**它们产出的行**；⭐⭐ 并且 ⭐ **同时断言那行「仍然必须说」什么**，⭐⭐ 因为 ⭐ **一个只写成禁令的守卫，空字符串也满足它。** |
| F-256 | ⭐⭐ **一条红线被我写成「不许出现数字」，⭐⭐ 而那会逼我删掉产品欠读者的一句话** | 计数守卫的第一版是 `not.toMatch(/[0-9]/)` ⭐⭐ 而 `detail` 合法地装着**一个日期**（「下一次 2026-10-16」）⭐⭐ ⇒ 断言当场变红 | ⭐⭐ *「我这条禁令的**对象**是什么，⭐⭐ 而不是我用正则方便找到的那一类字符？」* ⇒ 红线 11 禁的是**戴了活动量词的数字**（`4 次` / `3 遍` / `12 条`），⭐⭐ **不是日期** —— 日期是关于时间的事实。⇒ 判据写成 `\d+\s*(次\|遍\|回\|轮\|个\|条\|张\|天\|小时\|分钟)`，⭐⭐ **并且另加一条断言把那个日期钉住**，⭐⭐ 让「宽版禁令」不可能悄悄回来。 |
| F-258 | ⭐⭐⭐ **一条记着「未修 · 待产品决策」的边界，⭐⭐ 而它的**理由**先失效了，⭐⭐ 没人重新审视** | K1 把 `card_<millis>` 主键的同毫秒冲突记为「未修——**保持与既有仓储一致的语义**，记录于此待产品决策」。⭐ 写下的那天 `cards` 是**唯一**裸毫秒 id 的仓储，所以「一致」支持不改。⭐⭐ **此后 `notes` / `note_recall` / `lesson` 三家都改成了向前走一毫秒，`cards` 没被重新审视** ⇒ **理由失效了，而决定还挂着「待决策」。** ⚠️ 四轮之后 `dev.py demo` 的播种器第一次跑就撞上 —— 正是那条记录预测的「脚本化调用可能」 | ⭐⭐ *「这条记着『待决策』的边界，⭐⭐ 它的**理由**现在还成立吗？」* —— ⭐⭐ **理由比决定更容易悄悄失效，因为理由依赖的是邻居而邻居会变。** ⇒ 边界记录里凡有「与 X 保持一致」的措辞，⭐⭐ **X 变了就要回来重读这条**；⭐⭐ 而「待决策」的条目应当**有条件**：条件消失时它自己就该作废，而不是等人想起来 |
| F-259 | ⭐⭐⭐ **播种器把自己数出来的数当成功报告，⭐⭐ 而那个数来自一张表、却数了两张表** | `dev.py demo` 打印 `reviews 4 (in file: 1)` ⭐⭐ 原因：单个 `tally.reviews` 同时被 `reviews_repo.record`（决策复盘，写 `reviews` 表）与 `recall_repo.record_review`（笔记回忆，写 `note_reviews` 表）自增，⭐⭐ **而真实行数是 1 和 6**；另有一次自增写在**不拥有它的那个循环之外** | ⭐⭐⭐ *「这个数字是**从文件读回来的**，⭐⭐ 还是**我自己加出来的**？」* —— ⭐⭐ **自己加出来的那一列必然在某个时刻说谎，⭐⭐ 而它说得和真的一样。** ⇒ ⭐⭐ **打印「声称」与「实测」两列**（本轮正是这一列抓到的），⭐⭐ 并且 ⭐⭐ **加一条断言要求两列相等** —— 否则那只是好看，不是门禁。⭐⭐ 附带：**一张表一个计数器**，因为「reviews」这个词在两张表里都成立 |
| F-260 | ⭐⭐⭐ **变异检查的「确认落地」步骤，⭐⭐ 对一个「把它删掉」的变异不成立** | 变异 N2 让横幅永不渲染 ⇒ ⭐⭐ **`data-testid="demo-banner"` 被 tree-shaking 整个从 bundle 里删掉** ⇒ 而我的落地校验是 `assert 'demo-banner' in dist/*.js` ⇒ ⭐⭐ **对一次完美落地的变异报了 VOID。** ⚠️ 第二版把它改成「无条件断言存在」，⭐⭐ **同一个错误换了一顶帽子** | ⭐⭐ *「我这个『变异确实落地了』的检查，⭐⭐ 能不能对一个**目的就是删掉它**的变异也成立？」* —— ⭐⭐ **只肯确认自己预期的那件事的检查，⭐⭐ 在它最该工作的那个方向上是瞎的。** ⇒ 落地校验必须写成 ⭐⭐ **每个变异各自声明「标记应该在 / 不应该在」**，⭐⭐ 而不是脚本级的一个固定断言 |
| F-261 | ⭐⭐⭐ **资源只在成功路径上被释放，⭐⭐ 而 Windows 上这让「失败的命令」永久不可用** | `seed()` 把 `connection.close()` 写在 150 行函数体的**最后一行** ⇒ 成功没问题，失败就泄漏 ⇒ ⭐⭐ 下一次 `dev.py demo` 在 `stale.unlink()` 处 `PermissionError` —— ⭐⭐ **在任何重试之前就死掉**，⇒ **一次失败的播种把这个命令自己弄废了**，而读者屏幕上只剩下一个跟原因无关的错误 | ⭐⭐ *「我的清理代码，⭐⭐ 在**失败的那条路**上跑到了吗？」* —— ⭐⭐ **成功路径能跑通，⭐⭐ 恰恰是它掩盖这件事的原因**（本轮就是：手工跑通了，测试才把它逼出来）。⇒ ⭐⭐ 连接的所有权交给**一个 `with`**（`contextlib.closing`），⭐⭐ `return` 放在 `with` **内部**，⭐⭐ 因为「赋值给变量、最后统一 close」的写法正是那个洞本身 |
| F-262 | ⭐⭐ **解释「不要写 X」的文字里写着 X，⭐⭐ 而门禁扫的就是注释** | `S-03 no-prediction-field` 扫全仓的**字符串字面量，含注释** ⇒ 我那段说明「种子文案不得出现价格目标」的注释**自己包含了那个词**，⇒ `CHECK_PREDICTION_FIELD`。⭐ 同一个文件里**两次**：一次在注释，一次在模块 docstring。⚠️ 第三次是 `F-244` 的同形状 —— 一条解释 ruff 抑制标记的注释**自己成了抑制** | ⭐⭐ *「我写了一段解释『不要写 X』的文字，⭐⭐ 那段文字里有 X 吗？」* ⇒ ⭐⭐ **描述一个被扫描的构造时，要绕开那个构造的表面形式**（写「抑制标记」而不是写出标记）。⭐⭐ 与 `F-244` 同形：**解释机制的那句话，本身就是机制的一部分** |
| F-263 | ⭐⭐⭐ **外键让一个守卫永远走不到，⭐⭐ 而测试「通过」了两次，⭐⭐ 每次都是因为错的原因** | 我给播种器写了「任何表为空就报错」的守卫，⭐⭐ 然后想用「让 `notes.create` 静默不写」来证明它会响 ⇒ ⭐⭐ **两次都红了，但两次都不是这个守卫响的**：第一次死在 `add_link`（`NoteNotFoundError`），第二次死在 `note_recall.enroll` 的 **`FOREIGN KEY constraint failed`** —— ⭐⭐ **外键先响，所以「缺一条笔记」永远到不了那个检查。** ⇒ 最后改去 stub `sched_repo.enroll`，⭐⭐ 因为 **`*_schedule` 没有任何外键指着它**，⭐⭐ 那才是这个守卫真正能守的东西 | ⭐⭐⭐ *「我要守的那一行，⭐⭐ 有没有外键指着它？⭐⭐ **有的话，守住它的不是我的检查，是数据库** —— ⭐⭐ 而我的检查会因此变成一段永远不执行的代码，看起来还很像门禁。」* ⇒ ⭐⭐ 挑守卫的对象时按「**有没有东西指着它**」排序，⭐⭐ 不按「重不重要」 |
| F-264 | ⭐⭐⭐ **产品的建议里全是它自己不持有的名字，⭐⭐ 而校验只查形状** | `DecisionForm` 失效条件的 placeholder 是 `gross_margin`；`routes/decisions.py` 的 `metric` 字段描述举例 `gross_margin` / `revenue_yoy` / `price`。⭐⭐ **三个都不在 `CATALOGUE`(24) 与 `FINANCIAL_CATALOGUE`(8) 任何一张表里。** 域层只校验 `[a-z][a-z0-9_]*` ⇒ `POST /api/v1/decisions` **201 原样入库**；写入时**一句提示都没有**；`/today` 在 `as_of` 前什么都不显示 ⭐ **而那是对的，于是没有任何东西是红的**。⭐⭐ **而产品有毛利率，叫 `gp_margin`，标签「销售毛利率」** | ⭐⭐ *「产品举出来的例子，⭐⭐ 它自己答得上来吗？」* —— ⭐ **`read_metric` 早就返回 `MetricStatus.UNKNOWN_METRIC`**，⭐ docstring 写着「早退的顺序就是全部设计」；⇒ **能力端到端都在，只是问晚了几个月。** ⇒ 把词表接到界面上，⭐⭐ 并且 ⭐ **告知不能变成拒绝** —— `criterion_sentence` 有整个句子状态是为「算不了」准备的，⭐⭐ 换成 `<select>` 就是**删能力而不是修缺陷** |
| F-265 | ⭐⭐⭐ **一个「待决策」的边界，⭐⭐ 和一个「未修」的字段描述，⭐⭐ 说的是同一个谎** | 修 `metric` 字段描述时，`kill_criteria` 的描述**就写在下面一行**，原文：「至少一条，⭐⭐ **而且它必须是可求值的**」。⭐⭐ **没有任何东西强制它** —— 实测 `gross_margin` 返回 201。⇒ **同一个请求体里同一个谎出现了两次，而第一轮修复通过了它自己的测试** | ⭐⭐ *「我修的那句话，⭐⭐ 它的**邻居**是不是也在说同一件不成立的事？」* ⇒ ⭐⭐ 断言必须落在**服务端真正发出的那段文字**上（`/openapi.json`），⭐⭐ 而不是「我记得我改了」—— ⭐⭐ 否则测试只能证明你动了你看见的那一处 |
| F-266 | ⭐⭐⭐ **一句安慰，⭐⭐ 而它在承诺一个没有日期的事件** | 那句告知的第一版写：「判据照样记下来 —— 它会一直在这儿等，⭐⭐ **等到我能算为止**」。⭐⭐ **那是假的**：⭐ 不在两张表里的 token，⭐ **不是这个版本「打算」学会的东西**；「等到我能算为止」指着一个没有日期的事件。⭐ 那是安慰（红线 13 不讨好）+ ⭐ **产品兑现不了的承诺**，⭐ 而且和这个屏幕刚修的 bug **是同一个物种：说点好听的而不是说点真的** | ⭐⭐ *「这句提示里，⭐⭐ 有没有一个**我无法兑现的时间点**？」* ⇒ ⭐⭐ 只写**已经会发生的事**：「判据照样记下来；到期时它会照实说『不在我们能算的指标里』」。⭐⭐ **产品已经有一句那样的话，⭐ 所以正确的做法是引用它，而不是发明一句更好的** |
| F-267 | ⭐⭐ **「我没算」有两件完全不同的事，⭐⭐ 而 `Set` 的空把两件都变成了同一件** | `.BJ` 实测：`daily` 与 `financial` **都是 `pending`** ⇒ **32 个一个都算不了**；⭐ 而 `vocabularyKnown === false`（请求失败）时也是「什么都不知道」。⭐⭐ **两者都会让 `uncomputable()` 面对一个空集合，⭐⭐ 但答案必须相反**：⭐ 前者该说「都算不了」（那是关于数据层的事实），⭐ 后者必须**闭嘴**（那是网络错误，⭐ 指控读者是比什么都不说更坏的失败） | ⭐⭐ *「我这个『空』，⭐⭐ 是**答案为空**还是**我不知道答案**？」* ⇒ ⭐⭐ 两个参数分开：⭐ `computable: Set` 与 `vocabularyKnown: boolean`，⭐⭐ 而**测试必须成对地断言它们方向相反** —— ⭐ 只测一个，⭐ 另一个就是没人守的 |
| F-268 | ⭐⭐⭐ **一个守卫的量法不可靠，⭐⭐ 于是「只由它守着」就等于没守** | 变异 P2（那句话也对该算得出的 token 触发）在浏览器里连报 **三次 VOID「build failed」**，⭐⭐ 而同一处改动单独构建**干净通过**（连测两次）。⭐ 前两个假设都错：`CI=""` 无关（unset / 空 / `=1` 都构建通过），⭐ 语法也无关 | ⭐⭐⭐ *「我这条守卫，⭐⭐ 在**量它的工具自己出错时**，⭐⭐ 还剩几层？」* ⇒ ⭐⭐ 把纯函数（`uncomputable()`）抽进独立模块并用 **vitest** 钉住，⭐⭐ 变异在毫秒级死掉；⭐⭐ **E2E 仍保留** —— ⭐ 它证明那句话**到达了屏幕**，⭐ 那是单测看不见的。⭐⭐ **两层，因为它们失败的方式不同** —— 与 `F-253`（`reuseExistingServer`）和 `F-254`（构建失败被算成通过）是同族，⭐⭐ 而这一条是它们的**结论**：⭐⭐ **不可靠的裁判不该是唯一的裁判** |
| F-269 | ⭐⭐⭐ **我读了一个 count，⭐⭐ 没有读那些行是什么，⭐⭐ 而那个 count 被我当成了三个文件里的结论** | 全程报告 `decisions 5`，⭐⭐ 写进了 spec 057、`status.md`、记忆日志，⭐⭐ 也对用户说过三次「主人记过决策」。⭐⭐ **实测：5 条里只有 1 条是真的。** ⭐ 一条「冒烟测试：验证到期条件能出现在今日页」，⭐⭐ 三条「评测用：crossed / not_crossed / undetermined — D4 没建」，⭐⭐ 而那三条 id 相距 **30 / 33 毫秒**、⭐ id 是**真实墙钟时间戳**（不是 fixture 的整点形状）⇒ **某个进程打过真实 API** | ⭐⭐⭐ *「这个 count 对上了我的预期，⭐⭐ **那些行是什么**？」* —— ⭐⭐ **吻合不是定义。** ⭐ 仓里已记过一次同形（`F-224`）。⇒ ⭐⭐ **凡是要拿一个 count 去支撑「主人用没用」这种结论，⭐⭐ 必须把行读出来看**，⭐⭐ 因为 count 分不清「5 条决策」与「1 条决策 + 4 条测试数据」。⭐⭐ 而**这一条尤其贵**：它让后面每一个基于「主人已经记决策了」的判断都建在沙上 |
| F-270 | ⭐⭐⭐ **一个负向断言在它守护的元素还没出现时，⭐⭐ 是恒真的** | `the author markup never reaches the reader` 读完 `goto` 就读 `document.body.textContent`，⭐⭐ 而那个区块**要等 `/api/v1/capabilities` 回答之后才存在** ⇒ ⭐⭐ **断言读的是一个还不含被守对象的文档**，⭐⭐ 于是「把 `⭐` 放进 JSX」这个变异**存活了** —— ⭐⭐ **它漏给了读者，而守卫是绿的。** ⭐⭐ **同一个 describe 里另一条测试是碰巧对的**：⭐ `the provider names never reach the page` 在读之前 `await expect(notice).toBeVisible()`，⭐⭐ **这就是它的变异死掉、而这条活着的原因** | ⭐⭐⭐ *「我的负向断言，⭐⭐ 断言的东西**那时候在页面上吗**？」* ⇒ ⭐⭐ **先 `await expect(...).toBeVisible()`，⭐⭐ 再读 DOM** —— ⭐⭐ 「没找到」与「找到了、里面没有」是两件事，⭐⭐ 而 `expect(...).not.toContain()` 分不开它们。⭐⭐ **一个恒真的守卫比没有守卫更坏**，⭐⭐ 因为它报绿 |
| F-271 | ⭐⭐⭐ **`innerText` 是渲染感知的，⭐⭐ 于是它对「这个字符在文档里吗」这个问题会瞎** | 变异把 `⭐`（U+2B50）放进 JSX，⭐⭐ bundle 里量到了（`11088` = U+2B50），⭐⭐ DOM 探针也量到了（`textContent`），⭐⭐ **而 `innerText` 的版本连过三次。** ⭐⭐ `innerText` 尊重渲染，`textContent` 不尊重；⭐ U+2B50 的 `Emoji_Presentation=Yes` ⭐⭐ ⇒ **同一个字符，两种读法，一个看见一个看不见** | ⭐⭐ *「我在断言「文档里有这个字符」，⭐⭐ 那我该用 `innerText` 还是 `textContent`？」* ⇒ ⭐⭐ **`textContent`** —— ⭐⭐ `innerText` 的答案取决于字体回退，⭐⭐ 而**字体是这台机器的事，不是代码的事**。⭐⭐ 与 `F-270` 相加：⭐⭐ **那条守卫同时踩了两个坑**（没等 + 读错属性），⭐⭐ 而**两个坑都让它变绿**，⭐⭐ 所以它看起来像是「验过了」 |
| F-272 | ⭐⭐⭐ **一个豁免，在它守护的东西修好之后，⭐⭐ 就变成了把绿灯藏起来** | `S-18 no-response-drift` 的 `NOT_MIRRORED` 里有 `CapabilityCell` / `CapabilitySource` / `CapabilitiesRead` 三条，理由是「`GET /capabilities` **没有 UI**，grep 零命中」。⭐⭐ spec 059 给矩阵找了一个消费者，⭐ 三条客户端类型现在**字段齐全**，⭐⭐ ⇒ **豁免在遮一条会变绿的检查。** ⭐⭐ 而 **S-18 自己发现了**：「the NOT_MIRRORED entry for `CapabilitiesRead` **waives something no client type is missing, so it is hiding a green result**」 | ⭐⭐⭐ *「这条豁免还在遮的那个漂移，⭐⭐ **现在还成立吗**？」* —— ⭐⭐ 与 `F-258` 同形：⭐⭐ **一条记着「未修 · 待决策」的东西，它的理由会先于决定失效。** ⭐⭐ 而这里的代价更直接：⭐⭐ **留着它，服务端与客户端类型的对应关系就处于「未经验证但看起来已豁免」的状态。** ⭐⇒ 三条已删。⭐⭐ **留着 `S-16` 对 `CapabilityState` 的那条**：⭐ 那是字符串字面量联合、⭐ 不是对象，⭐ S-18 的字段集匹配根本看不见它 ⭐ —— **那是检查够不到的缺口，不是一条遮住绿灯的豁免** |
---

## 十、维护规则

1. **本文件只增不改** —— 已有条目的编号与措辞不得变更（可能有别处引用）。
2. **新增条目必须给"自查问法"** —— 只写"别犯 X"没有用。
3. **每条失败模式必须能被归到某个载体**：要么进本文件，要么进 `.ai/checks/static/`，要么进 `.ai/regressions/`。**不能只留在聊天记录里。**
4. **一次真实踩坑后，第一件事是回来加一条。**

---

## F-273..F-278 · 来自 spec 060（记录能不能被相信）

### F-273 · 把一条 docstring 当成了测量结果

**怎么发生的**：`checks/data_rules/dangling_target.py` 写着 `connect_for_migration` 以 `foreign_keys = OFF` 打开。⭐ 我**照它推理**，断定 `dev.py demo` 的播种器能写出那 4 行孤儿，⭐⭐ 并把这个结论写进了 spec 060。⭐⭐ **实测：它是 1。**

**为什么它危险 / 下次怎么问**：⭐⭐ **读一个解释 ≠ 读一个事实。** ⭐⭐ 当一句 docstring 要替我回答「这个连接的实际行为是什么」时，它就是一个**待验证的断言** — ⭐⭐ 而它恰好写错了。⭐⭐⭐ **自查问法**：「这句解释我核对过吗，⭐ 还是我只是读到了它？」⭐⭐⭐ ⭐⭐ **本会话第三次栽在同一个地方** ⭐⭐⭐ （`cards.id` = `F-258` · `foreign_keys` 机制 = `D-01` · 这次）⭐⭐⭐ ⭐⭐ ⇒ **本仓库自己的账本比我读代码得到的结论更完整。** ⭐⭐⭐

### F-274 · 严重级别是为了让门禁变绿才选的

**怎么发生的**：`D-25` 第一版报 `error`，⭐ 于是 `check-data` 永远红 ⭐⭐ — ⭐ 我第一反应是降级它，而理由（孤儿行不可修）**是真的**。

**为什么它危险 / 下次怎么问**：⭐⭐ **降级可以是对的，⭐⭐ 但必须先量出「为什么对」。** ⭐⭐ 本轮量到了三条：① 两个连接工厂都强制外键 ⇒ 产品写不出孤儿；② 没有任何代码删决策 ⇒ 不可修；③ `data.readonly()` 读的是读者的库 ⇒ **这条规则永远不可能因为本仓库的缺陷而失败**。⭐⭐⭐ ⭐⭐ ⇒ **严重级别是从三条测量推出来的，⭐⭐ 不是为了让门禁变绿。** ⭐⭐⭐ ⭐⭐ ⭐⭐ **真正该做的是把机制搬到能当 `error` 的地方** ⭐⭐ （`S-19`，⭐ 关于代码），⭐⭐ 而不是让一个永远红的门禁变成背景噪音。 ⭐⭐

### F-275 · 一个共享的 code 被拿去认规则

**怎么发生的**：`__main__.py` 与 `exemptions.py` 都用 `issue.code` 反查 check id，⭐ 而四条数据规则共用 `CHECK_DATA_INTEGRITY` ⭐⭐ ⭐ 字典推导取最后一个 ⇒ **D-25 的发现被记在 D-22 名下**；⭐⭐ 同一套逻辑还会让 `# noqa: D-22` 静默消掉 D-02 的发现。

**为什么它危险 / 下次怎么问**：⭐⭐⭐ **一个字段不能同时是类别和身份。** ⭐⭐⭐ `S-05` 要求 code 是已登记的**类别**，⭐⭐⭐ ⭐⭐ 所以 code 永远不可能认出一条规则 ⭐⭐⭐ ⭐⭐ — ⭐⭐⭐ ⭐⭐ 而我连着两处都去问了它。⭐⭐⭐ ⭐⭐ ⭐⭐ ⇒ **归属信息必须由「知道它的那一层」显式传下来**，⭐⭐⭐ ⭐⭐ 而不是在下游⭐⭐⭐ ⭐⭐⭐ ⭐⭐ 反推。⭐⭐⭐ ⭐⭐⭐ ⭐⭐ ⭐⭐ **一个红着的门禁指错文件，⭐⭐ 比没有门禁更糟**⭐⭐⭐ ⭐⭐⭐ ⭐⭐ — ⭐⭐⭐ ⭐⭐ 读者打开那条**通过**的规则，⭐⭐ 看不到问题，⭐⭐ 于是认定门禁在撒谎。

### F-276 · 去重之后计数，会让干过活的规则说「clean」

**怎么发生的**：`_dedupe` **故意跨规则去重**（同一条发现被九条规则报出来，打印九遍没人看），⭐ 而我最初在去重**之后**按规则统计 ⇒ ⭐⭐ **除第一条外的所有规则都报「clean」— 明明它们都报了。**

**为什么它危险 / 下次怎么问**：⭐⭐⭐ **两个「看起来对」的性质叠在一起，会得到一个错的答案。** ⭐⭐⭐ ⭐⭐ ⭐⭐⭐ **⇒ 计数必须在去重之前取，去重只决定「打印哪一份」。** ⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐⭐ ⭐⭐ ⭐⭐ 规则干了活，⭐⭐⭐ ⭐⭐ ⭐⭐ 归不该被去重顺手抹掉。 ⭐⭐⭐

### F-277 · pytest 的退出码 4 不是「测试红了」

**怎么发生的**：变异脚本把**任何非零退出**当成 kill，⭐ 而测试 id 的类名写错时 pytest 退 **4**（usage error）⭐⭐ ⇒ **报出了一个假的 KILLED。**

**为什么它危险 / 下次怎么问**：⭐⭐⭐ **变异测试的「结果」和它的「结论」是两件事。** ⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐⭐ ⭐⭐ ⭐⭐ 退出码 0=通过 · 1=测试失败 · 4=用法错误（⭐⭐ 测试 id 写错就是这一档）⭐⭐⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐ **⇒ 只有 1 算杀死，⭐⭐⭐ ⭐⭐ 0 和 4 分别是「没杀掉」和「没跑」。** ⭐⭐⭐

### F-278 · 一个 fixture 里没有那个碰撞，测试就杀不死对应的变异

**怎么发生的**：`test_an_exemption_cannot_be_written_against_another_rules_code` ⭐ 用 `make_ctx` 的默认注册表（⭐ **静态** 18 条 `S-*`，⭐⭐ 没有一条发出那个 code）⭐⭐ ⇒ code→rule 的查找走遍整个注册表、一无所获、`check_id` 原封不动 ⭐⭐ ⇒ 测试通过，⭐⭐ **而变异活了。**

**为什么它危险 / 下次怎么问**：⭐⭐⭐ ⭐⭐ **一个测试必须在它的 fixture 里长得像它要抓的那个缺陷。** ⭐⭐⭐ ⭐⭐ ⭐⭐⭐ ⭐⭐ 那个 fixture 用的是**静态**注册表 ⭐⭐ ⭐⭐ — ⭐⭐ ⭐⭐ 而缺陷活在**数据**注册表里，⭐⭐ ⭐⭐ ⭐⭐ 所以两者永远不会相遇。⭐⭐⭐ ⭐⭐⭐ ⭐⭐ ⭐⭐ ⇒ fixture 现在带**两条共用一个 code ⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐ 的规则，⭐⭐ 且顺序恰好让猜的那个答错**。⭐⭐⭐ ⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐⭐ ⭐⭐ ⭐⭐ **变异活了不一定意味着代码对，⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐ 也可能意味着测的是签名⭐⭐⭐ ⭐⭐ ⭐⭐ ⭐⭐ 而不是行为。** ⭐⭐⭐ ⭐⭐⭐ ⭐⭐



### F-279 · 我自己的输出退化，2493 行写进了一个源文件

**怎么发生的**：**连续第六次。** ⭐⭐⭐ 我在给 `reviews.py` 加排除逻辑时，输出在几次工具调用里退化成同一个字符（`⭐`）的重复，而 `edit` 的 `newString` 把那段退化文本**真的写进了源文件** —— 一次 2493 行的插入。⭐⭐ 早先我已经在 `.ai/memory/2026-10-06.md` 里给自己写过一条约束：⭐⭐⭐ **一个想法一个 `⭐` 标记，绝不超过两个。⭐⭐⭐ 而我在同一天违反了它三次**，⭐⭐ 这一次直接毁了一个文件。

**为什么它危险 / 下次怎么做**：⭐⭐⭐⭐⭐ **退化的输出不是「写得难看」，是一个会通过所有门禁的写入。** ⭐⭐⭐⭐⭐ `ruff` 不管注释里有多少个 `⭐`，⭐⭐ `mypy` 不管，⭐⭐ `pytest` 不管 —— ⭐⭐⭐⭐⭐ **所以唯一的检测手段是量文件本身**：⭐⭐⭐⭐⭐ `git diff --stat` 显示 `+2493` 的那一刻我没有立刻明白那是退化，⭐⭐⭐⭐⭐ 我先怀疑是 PowerShell 的编码问题。⭐⭐⭐⭐⭐ **一个 403 行的文件变成 120 KB，不是编码问题；是有人在里面写了 2493 行。** ⭐⭐⭐⭐⭐

  ⇒ **三条已经生效且今天用过的做法**：⭐⭐⭐⭐⭐
  1. ⭐⭐ **`ruff` 的 `E501` 报出 29 行过宽，是一个廉价的探测器。** ⭐⭐ 我今早跑了三次这种修复，⭐⭐⭐ 于是**在退化刚发生时**就撞见了它 —— ⭐⭐⭐ 那 29 行不是「注释太宽」，⭐⭐⭐ 是同一段填充重复了几十遍。⭐⭐⭐
  2. ⭐⭐⭐⭐⭐ **`git checkout -- <file>` 是最快的恢复手段，⭐⭐⭐⭐⭐ 而前提是文件已经 tracked。** ⭐⭐⭐⭐⭐ 所以新文件在第一次 `git add` 之前是**不可恢复的** —— 今晚 `reviews.py` 是靠它回来的，⭐⭐⭐⭐⭐ 而当天的迁移文件因为同一个理由仍然是干净的。⭐⭐⭐⭐⭐
  3. ⭐⭐⭐⭐⭐⭐⭐⭐ **注释里一个标记都不要放。** ⭐⭐⭐⭐⭐⭐⭐ 我今晚把 `reviews.py` 整段改成纯散文（一个 `⭐` 都没有），⭐⭐⭐⭐⭐⭐⭐ 因为**空白散文里没有可退化的字符**，⭐⭐⭐⭐⭐⭐⭐ 而 `⭐` 是一个。⭐⭐⭐⭐⭐⭐⭐⭐ 这个观察是今晚唯一真正的修复：⭐⭐⭐⭐⭐⭐⭐ 纪律管不住一个字符的重复，⭐⭐⭐⭐⭐⭐⭐ 但删掉那个字符可以。⭐⭐⭐⭐⭐⭐⭐⭐

  ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ **还有一条更值钱的，它是意外得到的：** ⭐⭐⭐⭐⭐⭐⭐⭐⭐ `today.py` 与 `manifest.json` 也各有一段退化，⭐⭐⭐⭐⭐⭐⭐⭐⭐ 而 `git diff --stat` 只让我看见 `reviews.py` 那个大的。⭐⭐⭐⭐⭐⭐⭐⭐⭐ 是 `star_check.py`（数每一行的标记游程，超过 2 就报）**把另外两个也抓出来的**。⭐⭐⭐⭐⭐⭐⭐⭐⭐ ⇒ **「太长了」和「退化了」是两个不同的检查，⭐⭐⭐⭐⭐⭐⭐⭐⭐ 而只有第二个需要新写的脚本。** ⭐⭐⭐⭐⭐⭐⭐⭐⭐ ⚠️ **这个脚本在 `C:\...\Temp` 里，⭐⭐⭐⭐⭐⭐⭐⭐⭐ 属于本会话的临时产物，⭐⭐⭐⭐⭐⭐⭐⭐⭐ 不在仓库里** —— ⭐⭐⭐⭐⭐⭐⭐⭐⭐ 如果这一类要复发，⭐⭐⭐⭐⭐⭐⭐⭐⭐ **先把它落进 `scripts/`，⭐⭐⭐⭐⭐⭐⭐⭐⭐ 别再重新写一遍。** ⭐⭐⭐⭐⭐⭐⭐⭐⭐

---

### F-280 · 我自己审查出来的 P0 是假的，而变异测试抓了它两次

**怎么发生的**：2026-10-06 我审查前端，报告了一个 P0：**「切换标的时会显示上一只票的决策记录」**，⭐ 并声称「我复现了它」。⭐⭐⭐ **那个复现是真的，而那个缺陷是假的。**

**根因是三层，每一层单独都足够**：

1. ⭐⭐ **`RequestRunner` 在隔离读的时候确实会重发 `#last`。** 我写了一条探针测试，它**第一次跑就通过** —— ⭐⭐ **因为它描述的就是现状。** ⭐⭐⭐ **但那只证明了这个类会那样做，⭐⭐⭐ 不证明有哪个页面会那样用。**
2. ⭐⭐⭐ **没有任何页面会。** 三处独立的机制各自挡住了它，⭐⭐ 而**我一处都没查**：
   - `App.tsx:221` 给 `<InstrumentPage>` 加了 `key={market/code}` ⇒ **切标的会重挂载**，⭐⭐ **hook 起点没有 `#last`。** ⭐⭐⭐ 而且那里的注释**原文就写着这个失效模式**
   - `VaultPage:336` 有显式的 `notes.loading` 分支 ⇒ **加载期间根本不渲染列表**
   - `CardSection` 每个卡片一个实例，由父列表的 key 固定 ⇒ **`cardId` 在实例生命周期内不变**
3. ⭐⭐⭐⭐ **所以「175 条 E2E 一条都没抓到」这个观察是对的，⭐⭐⭐ 而我的结论是错的** —— ⭐⭐⭐⭐ **没抓到不是因为测试瞎，⭐⭐⭐⭐ 是因为没有缺陷可抓。** ⭐⭐⭐⭐

**为什么它危险 / 下次怎么做**：⭐⭐⭐⭐⭐⭐ **我差点让一个不存在的缺陷进入一个可信的叙事。** ⭐⭐⭐⭐⭐⭐ 更糟的是它有全套证据：文件行号、可复现的探针、175 条测试的反证、⭐⭐⭐ **以及一句听起来很有分量的「对这个产品来说显示错一只票的决策是最坏的缺陷」。** ⭐⭐⭐⭐⭐⭐ **证据齐全和结论正确是两件事，⭐⭐⭐⭐⭐⭐ 而我手上没有任何一个检查会拆穿它们。** ⭐⭐⭐⭐⭐⭐

  ⭐⭐⭐⭐⭐⭐⭐⭐⭐ ⇒ **是变异测试拆穿的，而且是拆穿了两次**（`F-280` 的两次都在下面）：
  - ⭐⭐ **第一次变异删掉整个 `if` 块，`resource` 参数变成未使用 ⇒ `tsc` 杀了 webServer ⇒ run 退 1。** ⭐⭐⭐ **那个 1 长得和「测试红了」一模一样。** ⭐⭐ **换成一个保留引用的变异（`&& false`）后，run 退 0 ⇒ 我那条 E2E 抓不到缺陷 ⇒ 它是空的。**
  - ⭐⭐⭐⭐⭐⭐ **第二轮我换了个页面（`VaultPage` 的标签筛选，那里没有 `key`），⭐⭐⭐⭐⭐⭐ 以为这次总该可达。⭐⭐⭐⭐⭐⭐ 加了 `delay` 之后仍然是「只有失败路径那条抓到」。** ⭐⭐⭐⭐⭐⭐ 查下去才发现 `VaultPage:336` 的 loading 分支，⭐⭐⭐⭐⭐⭐ **第三次假设不成立。** ⭐⭐⭐⭐⭐⭐

  ⇒ **能拆穿它的不是「再想一遍」，⭐⭐ 而是三件具体的事**：
  1. ⭐⭐⭐⭐ **报告一个缺陷前，先问「有哪个调用方会真的走到这条路径」，⭐⭐⭐⭐ 并把那个调用方的代码读完。** ⭐⭐⭐⭐ 我读了 `RequestRunner`，⭐⭐⭐⭐ **没读任何一个页面怎么用它。** ⭐⭐⭐⭐
  2. ⭐⭐⭐⭐⭐ **在浏览器层证明一个瞬时状态，需要把响应「卡住」再断言。** ⭐⭐⭐⭐⭐ Playwright 的断言会重试到稳定态，⭐⭐⭐⭐⭐ **所以一个只在 200ms 里出错的页面，⭐⭐⭐⭐⭐ 在只等「最终对不对」的测试里是隐形的。** ⭐⭐⭐⭐⭐ 实测：加 `delay` 不够，⭐⭐⭐⭐⭐ **必须由测试自己握着闸门。** ⭐⭐⭐⭐⭐
  3. ⭐⭐⭐⭐⭐⭐⭐ **「175 条测试没抓到」是中性证据。** ⭐⭐⭐⭐⭐⭐⭐ 它与「缺陷真实存在但测试瞎了」一致，⭐⭐⭐⭐⭐⭐⭐ 也与「没有缺陷」一致。⭐⭐⭐⭐⭐⭐⭐ 我默认了前者，⭐⭐⭐⭐⭐⭐⭐ **而把一个观察读成一个结论，⭐⭐⭐⭐⭐⭐⭐ 正是这个仓记了 279 次的那件事，⭐⭐⭐⭐⭐⭐⭐ 第 280 次轮到了我自己。** ⭐⭐⭐⭐⭐⭐⭐

  ⭐⭐⭐⭐⭐⭐⭐⭐⭐ ⇒ **留下的改动是什么：** `RequestRunner` 现在带一个资源身份（4 行），⭐⭐⭐⭐⭐⭐⭐ 所以这一类不再依赖三个调用方各自记得写 `key` 或 loading 分支。⭐⭐⭐⭐⭐⭐⭐ **这是对一条不可达路径的加固，⭐⭐⭐⭐⭐⭐⭐ 不是缺陷修复，⭐⭐⭐⭐⭐⭐⭐ 报告里必须这么写。** ⭐⭐⭐⭐⭐⭐⭐⭐⭐ 3 条单测逐条列名并被变异杀掉；⭐⭐⭐⭐⭐⭐⭐⭐⭐ E2E 里**只有失败路径那条真正抓得到**（⭐⭐ 因为错误分支不走 loading 分支），⭐⭐⭐⭐⭐⭐⭐⭐⭐ 另两条是装饰 —— ⭐⭐⭐⭐⭐⭐⭐⭐⭐ **这一点也是测出来的，不是猜的。** ⭐⭐⭐⭐⭐⭐⭐⭐⭐

---

*本文件只增不改。最后更新：2026-10-04（F-191..F-201，F-202..F-210 来自 spec 049 · S-16，F-211 来自收敛 `QueueName`，F-212..F-218 来自 spec 050 · S-17（⭐ **F-218 是这一整轮四次同形状的归纳**），F-219..F-222 来自 spec 051 · 接线，F-223..F-225 来自 spec 052 · universe（⭐ **F-225 是 `F-218` 那个家族的第五次，而入口第一次是网络**），F-226..F-228 来自 spec 052 的落地（⭐ **F-228 的「重复挂载」没有任何测试守着**，见 `.ai/regressions/0026`），F-229..F-233 来自随后的日线区间截断修复（⭐ **F-232 是产品缺陷；其余四条是我自己的**，且⭐ **F-229 是 `F-98` 的反方向，而非它的一个小例子**）），F-234..F-237 来自 spec 053 的落地（⭐ **F-234 是本会话最值钱的一条**：四次探针三次作废，作废的三次全是我的解析器，⭐ **而 `tsc` 绿着才是判断依据**；F-235 是被自己的设计杀掉的阈值；F-236 是变异不红的诊断；F-237 是三处「声称自己被守着」），F-238 来自 spec 053 的第二半：判决拆两桶，请求体变真类型（★ **它让一小时前发布的规则变弱**），F-258..F-263 来自 spec 057 演示库（⭐ **这六条里 F-258 与 F-261 是产品/工具的缺陷，F-259 / F-260 / F-262 / F-263 全是我自己写出来又自己测出来的**，⭐⭐ F-264..F-268 来自 spec 058 指标词表（⭐⭐ **F-264 是本会话最刺眼的一条：产品自己给的三个例子，一个都答不上来，⭐⭐ 而它要的指标它其实有**；F-265 是**修了一处、邻居还在说同一句谎**；F-266 是**我自己写了一句安慰**；F-267 是**「答案为空」与「不知道答案」被同一个空集合吞掉**），F-269..F-272 来自 spec 059 能力矩阵（⭐⭐ **F-269 是本会话最贵的一条：我把一个 count 当成了三个文件里的结论，而它是 1 不是 5**；⭐⭐ F-270 + F-271 是**同一条守卫同时踩两个坑**（没等 + 读错属性）⭐⭐ **而两个坑都让它变绿**，⭐ 所以它看起来像验过了；⭐⭐ F-272 是**一条豁免在它守护的东西修好之后，把绿灯藏了起来**）*，⭐⭐ 而 **F-263 最刺眼：一个守卫因为外键先响而永远走不到，而证明它的测试两次都因为错的原因红了**）*

> ⚠️ **第二个编号缺陷：⭐ `F-257` 在代码里被引用，但本文件里没有这个条目** —— `frontend/src/api.ts:492` 写着「它把规则留得干净。（`F-257`）」。⭐ **本轮新增条目因此从 `F-258` 起，⭐ 而不是从 `F-257` 起**，以免占用一个已经说出口的号。 ⇒ ⚠️ **我没有补写 `F-257`**：那条讲的是 S-18（`no-response-drift`）看不见继承成员，⭐ 而本轮的上下文里只有转述、⭐⭐ 没有可核对的原始测量 ⇒ **凭转述补写一个失败模式，比留一个洞更坏**，⭐ 因为它会让后来的人以为这条已经被验证过。⭐ **补写它需要重新做那次变异。**
>
> ⚠️⭐⭐ **而这条注释本身让下一个脚本算错了**：⭐ 写完它之后，本文件里**出现**了字符串 `F-257`（就在这句话里），⭐⭐ 于是任何用 `max(F-数字)` 挑下一个编号的脚本都会**跳过 257** —— ⭐ 我自己那支追加脚本就中招了，⭐ 它把 258 当成第一个空号。⭐ **跳对了**，⭐ 因为 257 确实被引用过；⭐⭐ **但这是巧合不是约定**，⭐ 所以记在这里：**要占 257 就得真的写出那条条目**，⭐⭐ 而不是靠「文件里没出现过」推断。

> ⚠️ **本文件已知的编号缺陷（2026-10-04 量出，未修）：`F-50` 与 `F-132` 各有两个条目共用同一编号** —— `F-50` 见于节五「只修门禁报出来的那几条」与节六「首因支配（first topic dominance）」，`F-132` 在本文件内出现两处。⭐ **维护规则一禁止改已有编号，所以这里只记录事实而不重排** ⭐ —— **代价是任何指向 `F-50` / `F-132` 的交叉引用都是歧义的。** ⇒ 本轮新增条目已避开这两个号（F-233 引 `F-49`、F-229 引 `F-98`），⚠️ **而这是我实测发现的，不是推测：F-229 的脚本第一次运行就因 `| F-50 |` 匹配到两行而断言失败。**
