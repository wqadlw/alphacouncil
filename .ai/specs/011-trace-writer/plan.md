# Plan · Spec 011 trace 写入器

> ⚠️ 按项目纪律，本文件对审查者隐藏。

## 技术方案

### `core/trace.py`（新）

```python
_current_trace: ContextVar[Trace | None] = ContextVar("current_trace", default=None)

class Trace:                       # 句柄，不代表落盘格式
    id, _writer, _file_lock(每 Trace 顺序写，无需锁——请求内串行)
    def observation(self, name, *, status="ok", error_code=None, meta=None) -> ContextManager
    def score(self, name, value) -> None        # 写 scores/YYYY-MM-DD.jsonl
    def close(self, status) -> None             # 写 trace 的结束 observation? 不——trace 行在 start 写，end 写一条 kind:"trace_end"

class TraceWriter:
    def __init__(self, root: Path, *, clock=datetime.now(UTC), run_id_factory=...)
    def start(self, name: str) -> Trace         # 建 YYYY-MM-DD/<run_id>.jsonl，写 trace 行
    def record(self, trace_id, payload: dict)   # append 一行；任何异常 → warn 吞掉
```

- `run_id = f"{utc_millis()}-{secrets.token_hex(4)}"`（毫秒 + 4 字节随机，唯一且可读）。
- duration_ms 由 observation 的 context manager 计（monotonic 时钟——测时长，不测墙钟）。
- 上下文管理器 `_active` set/reset contextvar；`current_trace()` 供路由器读取。
- 所有磁盘写包在 try/except OSError → structlog warn（FR-4）。
- **脱敏靠调用点纪律 + 测试**：writer 本身只写调用方给的 meta；中间件只传 payload 的 sha256 前 12 位与字节数；测试断言原文不出现在文件。

### `api/app.py` 中间件

```python
writer = TraceWriter(resolved.traces_dir)
app.state.trace_writer = writer

@app.middleware("http")
async def trace_requests(request, call_next):
    with writer.start(f"{request.method} {request.scope.get('route')…}") as trace:  # route 模板在响应前可用 route.path；用 request.url.path 兜底
        token = set_current(trace)
        try:
            response = await call_next(request)
            trace.meta(http_status=response.status_code, payload_hash=…, payload_bytes=…)
            return response
        finally:
            reset(token)
```

- name 用 `request.scope.get("route").path`（响应期已有）否则 `request.url.path`。
- 请求体哈希：中间件里 `await request.body()` 会消费流——FastAPI 的 call_next 之后 body 仍可读？为避免干扰，**只哈希响应体**与请求的查询串长度；请求体哈希由写路径的仓储层调用点补（本轮不做，FR-5 只承诺响应/查询参数不入文）。——简化：中间件不读 body，脱敏由"根本不碰 body"保证。

### `providers/router.py`

`__init__(..., tracer: TraceHook | None = None)`；`_route` 内 call(provider) 包：

```python
hook = self._tracer.observation(f"provider:{provider.name}", dataset=dataset.value) if self._tracer else nullcontext-ish
```

tracer 协议：`observation(name, **meta) -> ContextManager`（无当前 trace 时由 writer 侧返回 no-op）。`default_router(tracer=None)` 透传；`app.py` 装配 `default_router(cache=SqliteCache(...), tracer=writer.hook)`。

### `core/config.py`

`traces_dir: Path = Field(default_factory=lambda: default_database_path().parent / "traces")`

## 测试

`tests/unit/test_trace.py`（新）：
- AC-1 文件布局 + 首行 trace + observation 字段/时长
- AC-2 两次运行两文件、append 不重写（首行字节不变）
- AC-3 TestClient /health 产生 trace；POST 决策后文件无理由原文、有 payload 哈希与状态
- AC-4 路由器有/无 trace 上下文两种取数
- 写失败吞掉（目录不可写 → 请求照常）
- 全文件行均为合法 JSON（json.loads 每行）

## 风险

| 风险 | 对策 |
|---|---|
| 中间件读 body 破坏流 | 不读 body；脱敏靠"不碰" |
| contextvar 在线程池的传播 | FastAPI 的 sync 路由在线程池中运行，contextvars 会被 copy——`set_current` 在中间件（事件循环）设置后，sync 依赖与 handler 拿到的是同一 context 副本；provider 调用发生在 handler 内 → 可见。测试实测这条链 |
| trace 文件膨胀 | 每请求一文件 + 按日目录；个人级频次 |
