# AlphaCouncil · 前端

这是 AlphaCouncil 的界面层。**当前只实现了 17 项功能中的 D1（关注池）一个切片**，
其余界面尚不存在 —— 这份 README 描述的是这一片，不是整个产品。

## 为什么前端不只是「把 API 画出来」

产品的机制要落在界面上，否则它就是一个普通的 CRUD 表单。这一片里有四处是刻意的：

| 位置 | 行为 | 为什么 |
|---|---|---|
| 提交按钮 | 理由为空时 `disabled`，并提示「这是唯一不能跳过的一步」 | 关注理由是知识层的第一条锚点，不能是可选字段 |
| 移除操作 | 成功文案是「记录没有被删除 —— 只是追加了一条「不再关注」」 | append-only 是产品承诺，界面必须说人话，不能让人以为数据没了 |
| 加载失败 | 显示「后端未启动时会出现这一行 —— 它不会静默显示成「空」」 | 空池子和拉取失败是两件完全不同的事，不能长得一样 |
| 页脚 | 「它不显示收益率，也不给你推荐」 | 红线 9 / 红线 1 的界面级落地 |

## 设计 token

`src/index.css` 里的 `@theme` 是唯一的颜色来源（机构研报风）：

```
paper #FBFAF8 · ink #0E1A26 · navy #1E3A5F · brass #9A7B4F
rule（0.5px 分隔线）· up #C0392B（涨）· down #1E7A46（跌）· warn
```

八条可检查的界面规则（衬线只用于标题 · 数字一律 `tabular-nums` · 涨跌色+符号双编码 ·
0.5px hairline 代替阴影 · 分类用左侧 2px 竖线而非圆角胶囊 · 信息密度优先 ·
颜色只承载意义 · 空状态是一句事实陈述）都落在这一个文件里，改样式先改它。

## 跑起来

```bash
npm install
npm run dev        # http://127.0.0.1:5173
```

需要后端在 `:8000` 上（见仓库根 README）。`/api` 由 Vite 代理到后端，
配置在 `vite.config.ts`。

> ⚠️ `vite.config.ts` 里显式写了 `server.host: '127.0.0.1'`。
> Vite 默认绑的是 `localhost`，在 Node 18+ 上会解析成 IPv6 的 `::1`，
> 于是任何走 `127.0.0.1` 的请求（包括它自己的代理）都会看到「端口没开」。
> **不要删掉这一行。**

## 检查

```bash
npm run typecheck  # tsc -b
npm run lint       # oxlint
npm run build      # tsc -b && vite build
```

`src/App.tsx` 里有一条**刻意保留**的 lint 警告（`set-state-in-effect`）。
它指向的是正确但更远的答案 —— TanStack Query —— 而不是一个 bug：
在 effect 里发请求正是这个规则存在的那个合法场景。留着是因为，
把它静音就等于把「数据层该换了」这个信号也一起藏掉了。

## 已知与规格的差距

- lint 用的是 `oxlint`，前端规格要求 **Biome**
- 组件是手写的，规格要求 **shadcn/ui**
- 数据获取还是手写 `useEffect`，规格要求 **TanStack Query**
- 测试（Vitest / Playwright）与 CI 接入**都还没有**
