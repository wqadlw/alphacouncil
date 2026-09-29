# 回归 0011 · 一个 P0 规则的标题比它的实现覆盖得宽

**发现**：2026-09-29，spec 042（S-01 覆盖 socket 与 SMTP）——
⭐ **不是被测试抓到的，是被一个还没写的需求照出来的**
**状态**：已修 · 规则已覆盖全部出口 · 产品代码已按规则重构

---

## 一、现象

S-01 的 docstring 第一句是：

> **S-01 — no raw HTTP outside the one entry point.**
> **Defect guarded:** constitution 7.8 / 4.5. Rate limiting has to be *a function*…

而宪法 §7.8 说的是「**外部调用**必须走唯一入口」。

⭐ **规则的标题、docstring、宪法和门禁清单，四处都写着「全部出口」。
而实现只覆盖了 HTTP。**

两个具体的洞，都是早就存在的：

| | 什么时候进来的 | 有没有被拦 |
|---|---|---|
| `notify/email.py` 的 `smtplib` | **spec 033**（早于本规则被改写） | ❌ 一声不响 |
| socket（10030 端口，私有协议） | 还不存在 —— `spec 041` 实测 BaoStock 时才提出 | ❌ 一声不响 |

⭐ 「在 `providers/` 的邻居里开一个 socket」不会被报出来 —— 不标记、不评审、不限流。

## 二、为什么一年都没人发现

⭐ **因为规则的名字和它做的事看起来是一致的。**

读 docstring 的人会认为「唯一入口」已经做到了；读门禁清单的人会看到 S-01 那一行是绿的；
⭐ **而实际上它只管一种传输。**

⚠️ 这和 `regressions/0005` 是同一族：⭐ **一个断言的**措辞**比它守护的东西宽**，
于是读的人得到一个比真相乐观的印象。

## 三、⭐ 收紧的方向：不是「加一个例外」，是「把口径换成出口」

修法不是给 `smtplib` 加一条豁免，而是：

1. 规则从「HTTP 模块」扩成「**网络传输**模块」，
   加 `socket` / `ssl` / `smtplib` / `ftplib` / `imaplib` / `poplib` / `http.client` /
   `urllib.request` / `xmlrpc.client`
2. ⭐ **匹配精确的点分模块名，绝不匹配顶层包**

第 2 条是被自己的代码逼出来的：

```python
# alphacouncil/domain/card.py:29
from urllib.parse import urlparse
```

⭐ **`urllib` 这一个包里同时装着纯字符串解析器和网络客户端**，
而 `domain/card.py` 用前者读卡片出处。
用 `name.split(".")[0]` 匹配会把**本项目的 provenance 代码**报成出口。

⚠️ **而这和 ADR-0031 是同一个错误形状**：那里用**目录**代替了**模块**，
这里用**顶层包**代替了**具体能力**。⭐ 粗粒度的名字代替细粒度的能力，两次。

## 四、⭐ 修规则的过程中，改出了产品代码

把 `smtplib` 纳入射程后，规则在**真实代码**上报了两条：

```
smtplib.SMTP_SSL(...) constructed in `send_email`
smtplib.SMTP(...)      constructed in `send_email`
```

⭐ **而 `notify/email.py` 是 spec 033 写的、当时是绿的。**

原代码在**重试循环里内联**开启会话：

```python
for attempt in range(1, max_attempts + 1):
    smtp = None
    try:
        if security == "ssl":
            smtp = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            smtp = smtplib.SMTP(host, port, timeout=10)
            if security == "starttls":
                smtp.ehlo(); smtp.starttls(); smtp.ehlo()   # ⭐ 第二次 ehlo
```

⭐ 所以「**开一个会话**」和「**重试**」是同一句话。
而那个第二次 `ehlo` 是整个文件最微妙的一行，**却埋在一个重试会重新进入的分支里**。

改成 `_smtp_session(host, port, security)` 工厂之后：
* 规则成立，**而且规则没有为了成立而被放宽**
* 重试循环回到它该管的事 —— 重试
* ⭐ 第二次 `ehlo` 有了**恰好一个**位置

## 五、⭐ 变异检查的两次存活，两次都是真缺口

| # | 变异 | 结果 | 缺的是什么测试 |
|---|---|---|---|
| 1 | 前缀匹配回来了（且集合里有 `urllib`） | **SURVIVED** | ⭐ 我写的变异**方向错了** —— `split[0]` 得到 `urllib`，而 `urllib` 不在集合里，所以变异不产生缺陷 |
| 2 | `smtplib.SMTP` 从构造器清单里删掉 | **SURVIVED** | ⭐ **真缺口**：没有任何测试断言「SMTP 构造器在清单里」 |

⭐ **第一个存活暴露的是我自己的测量错误**：要复现这个缺陷需要**同时**改两处
（集合里加 `urllib` + 换回前缀匹配），而**单条变异做不到** ——
⭐ **一个合取缺陷没有单点可破**，所以它必须由两条**分开**的测试守着
（`test_matching_is_not_a_prefix_match` + `test_a_prefix_rule_would_have_failed_that`）。

⭐ **第二个是真缺口，而且形状很清楚**：
「允许的形状被覆盖了」**不能**证明「其余形状也被覆盖」。
只有一条测试断言了工厂内的合法形态，真实代码的测试断言全树安静，
⭐ **两者都不能发现构造器清单被清空。**

## 六、教训

1. ⭐ **一条规则的标题/docstring 是断言，而断言可以比它守护的东西宽。**
   四处文档都写「全部出口」，实现只管一种传输 ⇒ **要么改实现，要么改标题；
   两者都不改，读的人就得到一个比真相乐观的印象。**
2. ⭐ **粗粒度的名字不能代替细粒度的能力** —— 目录代替模块（ADR-0031）、
   顶层包代替具体能力（本次）。两次的错误形状完全一样。
3. ⭐ **「合法形态有测试」不等于「非法形态被拦住了」。**
   前者证明允许的路能走，后者证明别的路走不通。
4. ⭐ **扩大一条规则的射程，先拿它跑一遍真实代码。**
   它在两小时内报出了两处一年前就该被报出来的地方。

## 七、相关

* `failure-modes.md` F-120 · F-121 · F-122
* `ADR-0031`（目录 → 模块）· `regressions/0005`（断言比真相宽）
* `spec 042`
