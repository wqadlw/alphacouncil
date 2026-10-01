/**
 * 歧义代码：读者输入 `000001` 之后能不能往前走（spec 047）
 *
 * ⭐⭐⭐ **这个 spec 的第一句是一个已量到的死结，不是设想。**
 *
 * ```
 *   POST /api/v1/watchlist {"ticker":"000001","reason":"…"}
 *     -> 400 {"code":"DATA_SOURCE_TICKER_AMBIGUOUS",
 *             "message":"000001 exists on sh / sz — choose one"}
 * ```
 *
 * 一行**英文**报错，在一个中文产品上，说「choose one」——
 * **而界面上没有任何东西可以选。** 而 `GET /api/v1/instruments/resolve` 从 D1 落地
 * 起就在正确回答（`{"status":"ambiguous","candidates":["sh","sz"]}`），
 * **在 `frontend/src` 里一个调用者都没有。** `api.ts` 自己的注释点名了这个 case：
 * 「a code like `000001` is *both* the Shanghai Composite and Ping An Bank」。
 *
 * 所以本文件断言的是**接通了**，而每一条都是量出来的形状，不是想象的。
 *
 * ⚠️ **这里没有断言「选完之后更顺手」这类主观判断。** 有的全是可量的：
 * 请求发了几次、请求体里 `market` 是什么、理由还在不在、按钮那句字是什么。
 */

import { expect, test } from '@playwright/test'
import {
  UNUSABLE_TICKER,
  ambiguousTicker,
  poolQuotes,
  poolRows,
  recordedEvent,
  resolvedTicker,
  routeApi,
} from './fixtures'

/** Every POST the page made, as the bodies it sent. */
function watchWrites(page: Parameters<typeof routeApi>[0]) {
  const bodies: Record<string, unknown>[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/v1/watchlist')) {
      const raw = request.postData()
      if (raw) bodies.push(JSON.parse(raw) as Record<string, unknown>)
    }
  })
  return bodies
}

test.describe('关注池 · 歧义代码（spec 047）', () => {
  test.beforeEach(async ({ page }) => {
    await routeApi(page, {
      'GET /api/v1/watchlist': poolRows(),
      'GET /api/v1/watchlist/quotes': poolQuotes(),
      // ⭐ **The resolver is stubbed by default as the *unambiguous* answer**, because
      // that is the shape every other test in this file needs — a test that is about
      // ambiguity must ask for it explicitly rather than get it by accident.
      'GET /api/v1/instruments/resolve': resolvedTicker(),
      'POST /api/v1/watchlist': recordedEvent(),
      'POST /api/v1/watchlist/remove': recordedEvent(),
    })
  })

  test('A1 · 歧义代码给出可选的市场，且此刻不写入', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/instruments/resolve': ambiguousTicker() })
    const writes = watchWrites(page)
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('000001')
    await page.locator('form input').nth(1).fill('探针：歧义时不应该写入')
    await page.locator('form button[type="submit"]').click()

    const chooser = page.getByTestId('pool-ambiguity')
    await expect(chooser).toBeVisible()
    await expect(page.getByTestId('pool-market-sh')).toBeVisible()
    await expect(page.getByTestId('pool-market-sz')).toBeVisible()

    // ⭐ **「此刻不写入」是这一条的一半。** 只断言「按钮出现了」的测试会让一个
    // 边问边写的实现通过 —— 而那种实现在读者还没选的时候就替他决定了一个市场。
    expect(writes, 'chooser 出现时一个 POST 都不该发').toHaveLength(0)
  })

  test('A3 · 选择器明说这个产品没有名称数据', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/instruments/resolve': ambiguousTicker() })
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('000001')
    await page.locator('form input').nth(1).fill('探针：文案')
    await page.locator('form button[type="submit"]').click()

    // ⭐ **`InstrumentDetailRead.name` 对每个标的都是 `None`**（实测 sh/000001、
    // sz/000001、sh/600519），所以选择器只能给市场。**它必须说出来** ——
    // 一个不解释的歧义提示，读者会以为是产品坏了。
    await expect(page.getByTestId('pool-ambiguity-question')).toContainText('没有标的名数据')
    await expect(page.getByTestId('pool-ambiguity-question')).toContainText('它不能替你选')
    // 而它说的是「你选的是市场，不是哪一个标的」——
    // 这一点必须落在字面上，因为读者最容易误以为选完就知道自己选了什么。
    await expect(page.getByTestId('pool-ambiguity-question')).toContainText('不是哪一个标的')
  })

  test('A2 · 点哪个市场，写进去的就是哪个；选本身不写', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/instruments/resolve': ambiguousTicker() })
    const writes = watchWrites(page)
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('000001')
    await page.locator('form input').nth(1).fill('探针：选市场之后写什么')
    await page.locator('form button[type="submit"]').click()
    await page.getByTestId('pool-ambiguity').waitFor()

    await page.getByTestId('pool-market-sz').click()

    // ⭐ **`aria-pressed` rather than a class name**: the pressed state is a fact a
    // screen reader reads, so pinning it means the test fails if it stops being one.
    await expect(page.getByTestId('pool-market-sz')).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByTestId('pool-market-sh')).toHaveAttribute('aria-pressed', 'false')
    // And the button says what the next press will do — a permanent record should be
    // the second deliberate act, not the first click.
    await expect(page.locator('form button[type="submit"]')).toHaveText('按这个市场写入')

    // ⭐ **Choosing must not write.** Measured: before `V-19`/`type="button"` this is
    // where the POST happened — the market buttons were submitting the form.
    expect(writes, '选择市场不写入').toHaveLength(0)

    await page.locator('form button[type="submit"]').click()
    await expect(page.getByText(/已记录（事件 #99）/)).toBeVisible()
    expect(writes).toHaveLength(1)
    expect(writes[0]).toMatchObject({ ticker: '000001', market: 'sz' })
  })

  test('A5 · 选择期间理由原文还在（它必填，且半年后要面对）', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/instruments/resolve': ambiguousTicker() })
    await page.goto('/#/pool')

    const reason = '这段话半年后我要能一字不差地复述'
    await page.locator('form input').first().fill('000001')
    await page.locator('form input').nth(1).fill(reason)
    await page.locator('form button[type="submit"]').click()
    await page.getByTestId('pool-ambiguity').waitFor()
    await page.getByTestId('pool-market-sh').click()

    // ⭐ **这条是整个设计顺序的理由。** 「先 POST 失败、再问」的写法也能接通，
    // 但读者为了选一个市场要把这段话重打一遍 —— 拿产品里最贵的一栏去换一个本来
    // 可以避免的错误。
    await expect(page.locator('form input').nth(1)).toHaveValue(reason)
  })

  test('A4 · 不歧义时只写一次，market 用服务端给的那个', async ({ page }) => {
    const writes = watchWrites(page)
    const resolves: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/instruments/resolve')) resolves.push(request.url())
    })
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('600519')
    await page.locator('form input').nth(1).fill('探针：不歧义的时候只写一次')
    await page.locator('form button[type="submit"]').click()
    await expect(page.getByText(/已记录（事件 #99）/)).toBeVisible()

    // ⭐ **Counting requests, not just checking the body.** 「resolve 之后又 POST 了
    // 两次」和「POST 一次」对读者没有区别，对这个门禁有区别。
    expect(resolves).toHaveLength(1)
    expect(writes).toHaveLength(1)
    expect(writes[0]).toMatchObject({ ticker: '600519', market: 'sh' })
    // And no chooser on the happy path.
    await expect(page.getByTestId('pool-ambiguity')).toHaveCount(0)
  })

  test('A6 · 不是一个代码时走服务端那句，且不给市场选择器', async ({ page }) => {
    // ⭐ **`{ status, body }`, not a bare `400`.** The first version of this line
    // passed the bare number, and the assertion then received
    // 「请求被拒绝（HTTP 400）」 — **which is correct behaviour for an empty 400**,
    // because `request()` has no sentence to show. That is the fixture lying about
    // the server rather than the product being wrong, and the shape of the failure is
    // the reason this note exists: a stubbed empty error reads exactly like a broken
    // error handler.
    await routeApi(page, {
      'GET /api/v1/instruments/resolve': { status: 400, body: UNUSABLE_TICKER },
    })
    const writes = watchWrites(page)
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('zzz')
    await page.locator('form input').nth(1).fill('探针：这不是一个代码')
    await page.locator('form button[type="submit"]').click()

    // ⭐ **The server's sentence, verbatim.** Spec 047 §3.4 keeps it untranslated on
    // purpose: translating it here means a frontend table of error codes that can
    // drift from `api/errors.py`, and `S-05` guards the other two sources, not this
    // one. So the test pins the *pass-through*, which is the thing the decision was
    // about.
    await expect(page.getByTestId('pool-form-error')).toContainText(
      'is not a six-digit code',
    )
    await expect(page.getByTestId('pool-ambiguity')).toHaveCount(0)
    expect(writes).toHaveLength(0)
  })

  test('A7 · 解析请求失败时不写入，且说清没写入', async ({ page }) => {
    // A transport-level failure: no body at all. Silently falling through to the
    // write would re-introduce the English DATA_SOURCE_TICKER_AMBIGUOUS sentence
    // with no chooser — the exact defect, one step later.
    await page.route('**/api/v1/instruments/resolve*', (route) => route.abort())
    const writes = watchWrites(page)
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('000001')
    await page.locator('form input').nth(1).fill('探针：解析断了')
    await page.locator('form button[type="submit"]').click()

    await expect(page.getByTestId('pool-form-error')).toBeVisible()
    expect(writes, '解析失败时绝不能写入').toHaveLength(0)
    await expect(page.getByTestId('pool-ambiguity')).toHaveCount(0)
  })

  test('改了代码，之前解析出来的市场作废', async ({ page }) => {
    await routeApi(page, { 'GET /api/v1/instruments/resolve': ambiguousTicker() })
    await page.goto('/#/pool')

    await page.locator('form input').first().fill('000001')
    await page.locator('form input').nth(1).fill('探针：改了代码')
    await page.locator('form button[type="submit"]').click()
    await page.getByTestId('pool-ambiguity').waitFor()
    await page.getByTestId('pool-market-sh').click()
    await expect(page.getByTestId('pool-market-chosen')).toBeVisible()

    // ⭐ **`300338` → `600519` with `sh` still pinned would write 600519 into the
    // Shanghai market on the strength of an answer given about a different code.**
    // The resolution is a claim about the text above it, so editing invalidates it.
    await page.locator('form input').first().fill('600519')
    await expect(page.getByTestId('pool-ambiguity')).toHaveCount(0)
    await expect(page.getByTestId('pool-market-chosen')).toHaveCount(0)
    await expect(page.locator('form button[type="submit"]')).toHaveText('加入关注池')
  })

  test('UNUSABLE_TICKER 那个信封的形状与服务端一致（防止 fixture 自己漂移）', async ({
    page,
  }) => {
    await routeApi(page, {
      'GET /api/v1/instruments/resolve': { status: 400, body: UNUSABLE_TICKER },
    })
    await page.goto('/#/pool')
    await page.locator('form input').first().fill('zzz')
    await page.locator('form input').nth(1).fill('探针：信封形状')
    await page.locator('form button[type="submit"]').click()

    // The five-field envelope, and the client reads `message` from it.
    expect(UNUSABLE_TICKER).toHaveProperty('severity')
    expect(UNUSABLE_TICKER).toHaveProperty('code')
    expect(UNUSABLE_TICKER).toHaveProperty('message')
    expect(UNUSABLE_TICKER).toHaveProperty('target')
    expect(UNUSABLE_TICKER).toHaveProperty('fix')
    await expect(page.getByTestId('pool-form-error')).toContainText(
      String(UNUSABLE_TICKER.message),
    )
  })
})