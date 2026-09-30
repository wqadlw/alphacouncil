# 失败模式清单

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

---

## 十、维护规则

1. **本文件只增不改** —— 已有条目的编号与措辞不得变更（可能有别处引用）。
2. **新增条目必须给"自查问法"** —— 只写"别犯 X"没有用。
3. **每条失败模式必须能被归到某个载体**：要么进本文件，要么进 `.ai/checks/static/`，要么进 `.ai/regressions/`。**不能只留在聊天记录里。**
4. **一次真实踩坑后，第一件事是回来加一条。**

---

*本文件只增不改。最后更新：2026-09-26*
