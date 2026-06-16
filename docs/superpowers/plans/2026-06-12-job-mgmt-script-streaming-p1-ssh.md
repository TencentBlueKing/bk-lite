# job_mgmt 脚本执行流式输出 — P1（SSH 手动目标）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 job_mgmt SSH 手动目标（`TargetSource.MANUAL`）的脚本执行支持实时流式输出——前端通过 SSE 实时看到逐行 stdout/stderr，迟到/刷新可回放完整历史。

**Architecture:** Go agent 已按行 publish `streamEvent` 到 NATS 主题 `job.stream.{id}.{target_key}`；新增 JetStream 流 `JOB_LOG_STREAM`（subjects=`job.stream.>`）自动落盘做可回放缓冲。runner 把 SSH 分支由阻塞 `execute_ssh` 改为 `execute_ssh_stream` 并下发主题、收尾发 `done` 哨兵；新增 Django SSE 端点（DRF action）建 JetStream 有序消费者 `DeliverPolicy.ALL`，一条订阅同时拿历史+实时，跑过纯聚合器后以 `text/event-stream` 推给前端。最终全量仍由 RPC 返回写 `execution_results`，流式纯增量、零侵入。

**Tech Stack:** Python 3.12 / Django 4.2 / DRF / NATS (nats-py JetStream) / pytest + pytest-django。后端测试统一用虚拟环境 `D:\app\venv\bkliteserver`。

**约束（硬性）：** 严格 TDD（先写失败测试→看失败→最小实现→重构）；新增/改动的 Python 模块行覆盖率 ≥ 90%（`execution_stream_service.py`、`views/execution.py` 的新增 action、`nats_client/clients.py` 新增函数）。真实 NATS/JetStream 的薄 I/O 胶水标 `# pragma: no cover`，由你本地集成验证。

**测试运行约定（每个测试步骤都用此前缀）：**
```
cd D:\app\github\bk-lite\.claude\worktrees\musing-chatterjee-a480b8\server
& D:\app\venv\bkliteserver\Scripts\Activate.ps1
```
之后用 `uv run pytest ...` 或激活环境内的 `pytest ...`。本计划统一写作 `pytest ...`。

---

## 文件结构

**新建：**
- `server/apps/job_mgmt/services/execution_stream_service.py` — 流式领域逻辑（纯函数 + 聚合器 + async 生成器 + 哨兵发布）。唯一职责：把「NATS 行事件」翻译成「SSE 文本流」并管理结束。
- `server/apps/job_mgmt/tests/test_execution_stream_service_pure.py` — 纯函数/聚合器单测。
- `server/apps/job_mgmt/tests/test_execution_stream_service_async.py` — async 生成器（注入 fake source）单测。
- `server/apps/job_mgmt/tests/test_execution_views_stream.py` — SSE 端点 `_views` 单测。
- `server/apps/job_mgmt/tests/test_script_runner_streaming.py` — runner 流式接线 `_service` 单测。
- `server/nats_client/tests/test_stream_primitives.py` — `publish_raw_sync` / `ensure_stream_sync` 单测（mock nc）。

**修改：**
- `server/nats_client/clients.py` — 新增 `publish_raw` / `publish_raw_sync`、`ensure_stream` / `ensure_stream_sync`、`iter_jetstream_subject`（胶水，pragma no cover）。
- `server/apps/job_mgmt/services/script_execution_runner.py` — SSH 分支改 `execute_ssh_stream`；`_run_via_sidecar` 与 `_handle_dangerous_command` 发 `done` 哨兵；`run()` 前置 `ensure_stream_sync`。
- `server/apps/job_mgmt/views/execution.py` — 新增 `stream` action。

---

## Task 1: 纯辅助函数与常量（topic / SSE 格式 / target_key 解析）

**Files:**
- Create: `server/apps/job_mgmt/services/execution_stream_service.py`
- Test: `server/apps/job_mgmt/tests/test_execution_stream_service_pure.py`

- [ ] **Step 1: Write the failing test**

```python
# server/apps/job_mgmt/tests/test_execution_stream_service_pure.py
import json

import pytest

from apps.job_mgmt.services import execution_stream_service as svc

pytestmark = pytest.mark.unit


def test_build_stream_topic():
    assert svc.build_stream_topic(42, "node-abc") == "job.stream.42.node-abc"
    assert svc.build_stream_topic("7", "5") == "job.stream.7.5"


def test_format_sse_event_is_data_line_with_trailing_blank():
    out = svc.format_sse_event({"line": "héllo", "type": "log"})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    assert json.loads(out[len("data: "):].strip()) == {"line": "héllo", "type": "log"}


def test_format_sse_event_keeps_unicode_unescaped():
    out = svc.format_sse_event({"line": "中文"})
    assert "中文" in out


def test_parse_target_key_strips_prefix():
    assert svc.parse_target_key("job.stream.42.node-abc", 42) == "node-abc"
    assert svc.parse_target_key("job.stream.42.t.5", 42) == "t.5"


def test_parse_target_key_returns_empty_when_no_match():
    assert svc.parse_target_key("other.subject", 42) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_pure.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError: module ... has no attribute 'build_stream_topic'`.

- [ ] **Step 3: Write minimal implementation**

```python
# server/apps/job_mgmt/services/execution_stream_service.py
"""脚本执行流式输出：把 NATS 行事件翻译成 SSE 文本流。"""

import json

# JetStream 回放缓冲配置
JOB_LOG_STREAM_NAME = "JOB_LOG_STREAM"
JOB_LOG_SUBJECTS = ["job.stream.>"]
JOB_LOG_MAX_AGE_SECONDS = 3600
JOB_LOG_MAX_BYTES = 256 * 1024 * 1024

# 结束哨兵类型
DONE_TYPE = "done"


def build_stream_topic(execution_id, target_key) -> str:
    """构造单个目标的流式主题。与 agent publish、SSE 消费过滤保持一致。"""
    return f"job.stream.{execution_id}.{target_key}"


def format_sse_event(payload: dict) -> str:
    """把一条事件序列化为 SSE `data:` 行（保留中文不转义）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def parse_target_key(subject: str, execution_id) -> str:
    """从主题 `job.stream.{id}.{target_key}` 中提取 target_key。"""
    prefix = f"job.stream.{execution_id}."
    if subject.startswith(prefix):
        return subject[len(prefix):]
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_pure.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add server/apps/job_mgmt/services/execution_stream_service.py server/apps/job_mgmt/tests/test_execution_stream_service_pure.py
git commit -m "feat(job_mgmt): 流式输出纯辅助函数(topic/SSE/target_key)"
```

---

## Task 2: 流式聚合器 ExecutionStreamAggregator（结束状态机）

**Files:**
- Modify: `server/apps/job_mgmt/services/execution_stream_service.py`
- Test: `server/apps/job_mgmt/tests/test_execution_stream_service_pure.py`

- [ ] **Step 1: Write the failing test**（追加到 pure 测试文件末尾）

```python
def test_aggregator_emits_every_payload_as_sse():
    agg = svc.ExecutionStreamAggregator(["a", "b"])
    out = agg.process({"target_key": "a", "line": "x"})
    assert out == svc.format_sse_event({"target_key": "a", "line": "x"})


def test_aggregator_not_complete_until_all_targets_done():
    agg = svc.ExecutionStreamAggregator(["a", "b"])
    assert agg.is_complete() is False
    agg.process({"target_key": "a", "type": svc.DONE_TYPE, "status": "success"})
    assert agg.is_complete() is False
    agg.process({"target_key": "b", "type": svc.DONE_TYPE, "status": "failed"})
    assert agg.is_complete() is True


def test_aggregator_done_target_key_is_string_normalized():
    agg = svc.ExecutionStreamAggregator([1, 2])
    agg.process({"target_key": 1, "type": svc.DONE_TYPE, "status": "success"})
    agg.process({"target_key": "2", "type": svc.DONE_TYPE, "status": "success"})
    assert agg.is_complete() is True


def test_aggregator_unknown_done_target_is_ignored_safely():
    agg = svc.ExecutionStreamAggregator(["a"])
    agg.process({"target_key": "zzz", "type": svc.DONE_TYPE, "status": "success"})
    assert agg.is_complete() is False


def test_aggregator_empty_targets_is_immediately_complete():
    agg = svc.ExecutionStreamAggregator([])
    assert agg.is_complete() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_pure.py -k aggregator -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'ExecutionStreamAggregator'`.

- [ ] **Step 3: Write minimal implementation**（追加到 `execution_stream_service.py`）

```python
class ExecutionStreamAggregator:
    """跟踪各目标是否已收到 done 哨兵；所有目标 done 即整体结束。"""

    def __init__(self, target_keys):
        self._pending = {str(k) for k in target_keys}

    def process(self, payload: dict) -> str:
        """处理一条事件：若为 done 哨兵则销账，始终返回其 SSE 文本。"""
        if payload.get("type") == DONE_TYPE:
            self._pending.discard(str(payload.get("target_key", "")))
        return format_sse_event(payload)

    def is_complete(self) -> bool:
        return len(self._pending) == 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_pure.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add server/apps/job_mgmt/services/execution_stream_service.py server/apps/job_mgmt/tests/test_execution_stream_service_pure.py
git commit -m "feat(job_mgmt): 流式聚合器(done 哨兵结束状态机)"
```

---

## Task 3: NATS 原语 — publish_raw_sync / ensure_stream_sync / iter_jetstream_subject

**Files:**
- Modify: `server/nats_client/clients.py`
- Create: `server/nats_client/tests/__init__.py`（空文件，若不存在）
- Create: `server/nats_client/tests/test_stream_primitives.py`

- [ ] **Step 1: Write the failing test**

```python
# server/nats_client/tests/test_stream_primitives.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nats_client import clients

pytestmark = pytest.mark.unit


def test_publish_raw_sync_publishes_plain_json_to_subject():
    nc = MagicMock()
    nc.publish = AsyncMock()
    nc.flush = AsyncMock()
    nc.close = AsyncMock()

    async def _fake_get(*_a, **_k):
        return nc

    with patch.object(clients, "get_nc_client", _fake_get):
        clients.publish_raw_sync("job.stream.1.a", {"type": "done", "status": "success"})

    nc.publish.assert_awaited_once()
    subject, data = nc.publish.await_args.args
    assert subject == "job.stream.1.a"
    assert json.loads(data.decode()) == {"type": "done", "status": "success"}
    nc.close.assert_awaited_once()


def test_ensure_stream_sync_adds_stream_when_absent():
    js = MagicMock()
    js.add_stream = AsyncMock()
    nc = MagicMock()
    nc.jetstream = MagicMock(return_value=js)
    nc.close = AsyncMock()

    async def _fake_get(*_a, **_k):
        return nc

    with patch.object(clients, "get_nc_client", _fake_get):
        clients.ensure_stream_sync("JOB_LOG_STREAM", ["job.stream.>"], 3600, 1024)

    js.add_stream.assert_awaited_once()
    nc.close.assert_awaited_once()


def test_ensure_stream_sync_updates_stream_when_already_exists():
    js = MagicMock()
    js.add_stream = AsyncMock(side_effect=Exception("stream name already in use"))
    js.update_stream = AsyncMock()
    nc = MagicMock()
    nc.jetstream = MagicMock(return_value=js)
    nc.close = AsyncMock()

    async def _fake_get(*_a, **_k):
        return nc

    with patch.object(clients, "get_nc_client", _fake_get):
        clients.ensure_stream_sync("JOB_LOG_STREAM", ["job.stream.>"], 3600, 1024)

    js.update_stream.assert_awaited_once()
    nc.close.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest nats_client/tests/test_stream_primitives.py -v`
Expected: FAIL — `AttributeError: module 'nats_client.clients' has no attribute 'publish_raw_sync'`.

- [ ] **Step 3: Write minimal implementation**（在 `server/nats_client/clients.py` 末尾追加；并把新函数名加入文件顶部 `__all__`）

在 `__all__` 列表追加：`"publish_raw"`, `"publish_raw_sync"`, `"ensure_stream"`, `"ensure_stream_sync"`, `"iter_jetstream_subject"`。

```python
# --- 流式输出原语（job_mgmt 脚本执行实时日志） ---

async def publish_raw(subject: str, payload: dict) -> None:
    """向原始 subject 发布一条扁平 JSON（不走 RPC 的 args/kwargs 包装）。"""
    nc = await get_nc_client()
    try:
        await nc.publish(subject, json.dumps(payload).encode())
        await nc.flush()
    finally:
        await nc.close()


def publish_raw_sync(subject: str, payload: dict) -> None:
    return asyncio.run(publish_raw(subject, payload))


async def ensure_stream(name: str, subjects, max_age: int, max_bytes: int) -> None:
    """幂等声明 JetStream 流：不存在则创建，存在则更新配置。"""
    from nats.js.api import DiscardPolicy, StreamConfig

    nc = await get_nc_client()
    try:
        js = nc.jetstream()
        # 注意：nats-py StreamConfig.max_age 单位以安装版本为准（秒/纳秒），
        # 仅影响保留时长，不影响功能正确性；本地集成时核对一次。
        cfg = StreamConfig(
            name=name,
            subjects=list(subjects),
            max_age=max_age,
            max_bytes=max_bytes,
            discard=DiscardPolicy.OLD,
        )
        try:
            await js.add_stream(cfg)
        except Exception:
            await js.update_stream(cfg)
    finally:
        await nc.close()


def ensure_stream_sync(name: str, subjects, max_age: int, max_bytes: int) -> None:
    return asyncio.run(ensure_stream(name, subjects, max_age, max_bytes))


async def iter_jetstream_subject(filter_subject: str, idle_timeout: float = 300):  # pragma: no cover
    """JetStream 有序消费者：从头回放 + 实时 tail。空闲超时即结束。

    胶水代码，依赖真实 NATS/JetStream，单测以注入 fake source 覆盖上层逻辑；
    本函数本身由本地集成验证。yield (subject, payload_dict)。
    """
    nc = await get_nc_client()
    sub = None
    try:
        js = nc.jetstream()
        sub = await js.subscribe(filter_subject, ordered_consumer=True)
        while True:
            try:
                msg = await sub.next_msg(timeout=idle_timeout)
            except Exception:
                break
            try:
                payload = json.loads(msg.data.decode())
            except json.JSONDecodeError:
                payload = {"line": msg.data.decode(errors="ignore")}
            yield msg.subject, payload
    finally:
        if sub is not None:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        await nc.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest nats_client/tests/test_stream_primitives.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add server/nats_client/clients.py server/nats_client/tests/__init__.py server/nats_client/tests/test_stream_primitives.py
git commit -m "feat(nats): 流式原语 publish_raw/ensure_stream/iter_jetstream_subject"
```

---

## Task 4: done 哨兵发布 + 终态快照生成器

**Files:**
- Modify: `server/apps/job_mgmt/services/execution_stream_service.py`
- Test: `server/apps/job_mgmt/tests/test_execution_stream_service_async.py`

- [ ] **Step 1: Write the failing test**

```python
# server/apps/job_mgmt/tests/test_execution_stream_service_async.py
import asyncio
import json
from unittest.mock import patch

import pytest

from apps.job_mgmt.services import execution_stream_service as svc

pytestmark = pytest.mark.unit


def _collect(async_gen):
    async def _run():
        return [chunk async for chunk in async_gen]
    return asyncio.run(_run())


def _payloads(chunks):
    return [json.loads(c[len("data: "):].strip()) for c in chunks if c.startswith("data: ") and "[DONE]" not in c]


def test_publish_done_sentinel_publishes_expected_payload():
    with patch.object(svc, "publish_raw_sync") as mock_pub:
        svc.publish_done_sentinel(7, "node-x", "success")
    mock_pub.assert_called_once()
    subject, payload = mock_pub.call_args.args
    assert subject == "job.stream.7.node-x"
    assert payload == {"execution_id": "7", "target_key": "node-x", "type": "done", "status": "success"}


def test_snapshot_sse_from_results_emits_stdout_stderr_then_done():
    results = [
        {"target_key": "a", "stdout": "out-a", "stderr": ""},
        {"target_key": "b", "stdout": "out-b", "stderr": "err-b"},
    ]
    chunks = _collect(svc.snapshot_sse_from_results(results))
    assert chunks[-1] == "data: [DONE]\n\n"
    payloads = _payloads(chunks)
    # a: 仅 stdout；b: stdout + stderr
    assert {"target_key": "a", "stream": "stdout", "line": "out-a", "type": "history"} in payloads
    assert {"target_key": "b", "stream": "stderr", "line": "err-b", "type": "history"} in payloads
    assert sum(1 for p in payloads if p["target_key"] == "a") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_async.py -v`
Expected: FAIL — `AttributeError: ... 'publish_done_sentinel'`.

- [ ] **Step 3: Write minimal implementation**（追加到 `execution_stream_service.py`；顶部加导入）

在文件顶部 import 区追加：

```python
from nats_client.clients import publish_raw_sync
```

追加函数：

```python
def publish_done_sentinel(execution_id, target_key, status: str) -> None:
    """目标执行结束时发一条 done 哨兵到该目标主题，驱动 SSE 关闭对应面板。"""
    subject = build_stream_topic(execution_id, target_key)
    payload = {
        "execution_id": str(execution_id),
        "target_key": str(target_key),
        "type": DONE_TYPE,
        "status": status,
    }
    publish_raw_sync(subject, payload)


async def snapshot_sse_from_results(results):
    """终态/降级路径：把已落库的 execution_results 一次性作为历史事件推完即结束。"""
    for r in results:
        target_key = r.get("target_key", "")
        if r.get("stdout"):
            yield format_sse_event(
                {"target_key": target_key, "stream": "stdout", "line": r.get("stdout", ""), "type": "history"}
            )
        if r.get("stderr"):
            yield format_sse_event(
                {"target_key": target_key, "stream": "stderr", "line": r.get("stderr", ""), "type": "history"}
            )
    yield "data: [DONE]\n\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_async.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add server/apps/job_mgmt/services/execution_stream_service.py server/apps/job_mgmt/tests/test_execution_stream_service_async.py
git commit -m "feat(job_mgmt): done 哨兵发布与终态快照 SSE 生成器"
```

---

## Task 5: stream_execution_events async 生成器（注入式，可单测）

**Files:**
- Modify: `server/apps/job_mgmt/services/execution_stream_service.py`
- Test: `server/apps/job_mgmt/tests/test_execution_stream_service_async.py`

- [ ] **Step 1: Write the failing test**（追加到 async 测试文件）

```python
async def _fake_source(items):
    for it in items:
        yield it


def test_stream_events_replays_then_live_then_stops_on_all_done():
    source = _fake_source([
        {"target_key": "a", "stream": "stdout", "line": "hist-1"},
        {"target_key": "a", "stream": "stdout", "line": "live-1"},
        {"target_key": "a", "type": svc.DONE_TYPE, "status": "success"},
        {"target_key": "a", "stream": "stdout", "line": "SHOULD-NOT-APPEAR"},
    ])
    gen = svc.stream_execution_events(1, ["a"], message_source=source)
    chunks = _collect(gen)

    assert chunks[-1] == "data: [DONE]\n\n"
    payloads = _payloads(chunks)
    lines = [p.get("line") for p in payloads if "line" in p]
    assert lines == ["hist-1", "live-1"]  # done 之后的行不再转发
    assert any(p.get("type") == svc.DONE_TYPE for p in payloads)


def test_stream_events_emits_done_when_source_exhausts_without_sentinel():
    # 例如高危拦截/异常路径未发 done：source 自然结束也要收尾 [DONE]
    source = _fake_source([{"target_key": "a", "stream": "stdout", "line": "x"}])
    gen = svc.stream_execution_events(1, ["a", "b"], message_source=source)
    chunks = _collect(gen)
    assert chunks[-1] == "data: [DONE]\n\n"


def test_stream_events_handles_source_error_gracefully():
    async def _boom():
        yield {"target_key": "a", "line": "ok"}
        raise RuntimeError("nats down")

    gen = svc.stream_execution_events(1, ["a"], message_source=_boom())
    chunks = _collect(gen)
    payloads = _payloads(chunks)
    assert any(p.get("type") == "error" for p in payloads)
    assert chunks[-1] == "data: [DONE]\n\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_async.py -k stream_events -v`
Expected: FAIL — `AttributeError: ... 'stream_execution_events'`.

- [ ] **Step 3: Write minimal implementation**（追加到 `execution_stream_service.py`；顶部补 import）

在文件顶部 import 区追加：

```python
from apps.core.logger import job_logger as logger
from nats_client.clients import iter_jetstream_subject
```

追加函数：

```python
async def _default_message_source(execution_id):  # pragma: no cover
    """默认数据源：JetStream 有序消费者，把主题里的 target_key 注入 payload。"""
    filter_subject = f"job.stream.{execution_id}.>"
    async for subject, payload in iter_jetstream_subject(filter_subject):
        tk = parse_target_key(subject, execution_id)
        if "target_key" not in payload and tk:
            payload["target_key"] = tk
        yield payload


async def stream_execution_events(execution_id, target_keys, message_source=None):
    """SSE 主生成器：回放历史 + 实时 tail，所有目标 done（或源耗尽/出错）即收尾。"""
    aggregator = ExecutionStreamAggregator(target_keys)
    if message_source is None:
        message_source = _default_message_source(execution_id)
    try:
        async for payload in message_source:
            yield aggregator.process(payload)
            if aggregator.is_complete():
                break
    except Exception as e:  # 源异常不应让连接 500，转一条 error 事件后正常收尾
        logger.warning(f"[stream_execution_events] 数据源异常 execution_id={execution_id}: {e}")
        yield format_sse_event({"type": "error", "message": str(e)})
    yield "data: [DONE]\n\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/job_mgmt/tests/test_execution_stream_service_async.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add server/apps/job_mgmt/services/execution_stream_service.py server/apps/job_mgmt/tests/test_execution_stream_service_async.py
git commit -m "feat(job_mgmt): SSE 主生成器 stream_execution_events(注入式可测)"
```

---

## Task 6: runner 接线 — execute_ssh_stream + done 哨兵 + ensure_stream

**Files:**
- Modify: `server/apps/job_mgmt/services/script_execution_runner.py`
- Test: `server/apps/job_mgmt/tests/test_script_runner_streaming.py`

> 背景：当前 SSH 分支（`script_execution_runner.py:162-172`）调 `executor.execute_ssh(...)`。改为 `execute_ssh_stream(...)`，多传 `execution_id` 与 `stream_log_topic`；返回值处理逻辑不变。`_run_via_sidecar` 每个目标完成后发 done 哨兵；`_handle_dangerous_command` 拦截时为所有目标发 done 哨兵（避免 SSE 空等）。`run()` 在进入 sidecar 前 `ensure_stream_sync`。

- [ ] **Step 1: Write the failing test**

```python
# server/apps/job_mgmt/tests/test_script_runner_streaming.py
from unittest.mock import MagicMock, patch

import pytest

from apps.job_mgmt.constants import ExecutionStatus, ScriptType, TargetSource
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner

pytestmark = pytest.mark.unit


def _runner():
    return ScriptExecutionRunner(execution_id=99)


def test_ssh_branch_calls_execute_ssh_stream_with_topic():
    runner = _runner()
    target = {"target_id": 5, "name": "host1", "ip": "1.2.3.4"}
    fake_exec = MagicMock()
    fake_exec.execute_ssh_stream.return_value = {"stdout": "hi", "stderr": "", "exit_code": 0}

    with patch("apps.job_mgmt.services.script_execution_runner.Executor", return_value=fake_exec), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False), \
         patch.object(ScriptExecutionRunner, "get_ssh_credentials", return_value={
             "node_id": "region-1", "host": "1.2.3.4", "username": "root",
             "password": "p", "private_key": None, "port": 22,
         }):
        result = runner.execute_script_on_target(
            target, TargetSource.MANUAL, "echo hi", ScriptType.SHELL, 60, 99
        )

    assert fake_exec.execute_ssh_stream.called
    kwargs = fake_exec.execute_ssh_stream.call_args.kwargs
    assert kwargs["stream_log_topic"] == "job.stream.99.5"
    assert kwargs["execution_id"] == "99"
    assert result["status"] == ExecutionStatus.SUCCESS


def test_sidecar_publishes_done_sentinel_per_target():
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.target_source = TargetSource.MANUAL
    execution.script_type = ScriptType.SHELL
    execution.timeout = 60
    target_list = [{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}]

    with patch.object(ScriptExecutionRunner, "execute_script_on_target", return_value={
            "target_key": "5", "name": "h1", "status": ExecutionStatus.SUCCESS}), \
         patch.object(ScriptExecutionRunner, "is_cancelled", return_value=False), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        runner._run_via_sidecar(execution, target_list, "echo hi")

    mock_done.assert_called_once_with(99, "5", ExecutionStatus.SUCCESS)


def test_dangerous_command_publishes_done_for_all_targets():
    runner = _runner()
    execution = MagicMock()
    execution.id = 99
    execution.script_content = "rm -rf /"
    execution.team = [1]
    target_list = [
        {"target_id": 5, "name": "h1", "ip": "1.1.1.1"},
        {"node_id": "n7", "name": "h2", "ip": "2.2.2.2"},
    ]
    check = MagicMock()
    check.can_execute = False
    check.forbidden = [{"rule_name": "rm-rf"}]

    with patch("apps.job_mgmt.services.script_execution_runner.DangerousChecker.check_command", return_value=check), \
         patch("apps.job_mgmt.services.script_execution_runner.publish_done_sentinel") as mock_done:
        handled = runner._handle_dangerous_command(execution, target_list)

    assert handled is True
    done_targets = {c.args[1] for c in mock_done.call_args_list}
    assert done_targets == {"5", "n7"}
    for c in mock_done.call_args_list:
        assert c.args[2] == ExecutionStatus.FAILED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/job_mgmt/tests/test_script_runner_streaming.py -v`
Expected: FAIL — `execute_ssh_stream` 未被调用（当前是 `execute_ssh`）；`publish_done_sentinel` 导入不存在 / 未调用。

- [ ] **Step 3: Write minimal implementation**

3a. 顶部 import 区追加（`script_execution_runner.py`）：

```python
from apps.job_mgmt.services.execution_stream_service import (
    JOB_LOG_MAX_AGE_SECONDS,
    JOB_LOG_MAX_BYTES,
    JOB_LOG_STREAM_NAME,
    JOB_LOG_SUBJECTS,
    build_stream_topic,
    publish_done_sentinel,
)
from nats_client.clients import ensure_stream_sync
```

3b. 在 `execute_script_on_target` 的 SSH 分支（当前 `executor.execute_ssh(...)` 调用）替换为流式调用。把：

```python
                executor = Executor(ssh_creds["node_id"])
                ssh_command = build_heredoc_command(shell, script_content)
                exec_result = executor.execute_ssh(
                    command=ssh_command,
                    host=ssh_creds["host"],
                    username=ssh_creds["username"],
                    password=ssh_creds["password"],
                    private_key=ssh_creds["private_key"],
                    timeout=timeout,
                    port=ssh_creds["port"],
                    fast_fail=True,
                )
```

替换为：

```python
                executor = Executor(ssh_creds["node_id"])
                ssh_command = build_heredoc_command(shell, script_content)
                exec_result = executor.execute_ssh_stream(
                    command=ssh_command,
                    host=ssh_creds["host"],
                    username=ssh_creds["username"],
                    password=ssh_creds["password"],
                    private_key=ssh_creds["private_key"],
                    timeout=timeout,
                    port=ssh_creds["port"],
                    execution_id=str(execution_id),
                    stream_log_topic=build_stream_topic(execution_id, target_key),
                    fast_fail=True,
                )
```

3c. 在 `_run_via_sidecar` 的 `as_completed` 循环里，拿到/构造出 `result` 后补发 done 哨兵。把成功与异常两个分支末尾都补上：

成功分支（`results.append(result)` 之后）：

```python
                    results.append(result)
                    logger.info(f"[{self.task_name}] 目标 {target_info.get('name')} 执行完成: status={result['status']}")
                    publish_done_sentinel(execution.id, result.get("target_key", ""), result.get("status", ExecutionStatus.FAILED))
```

异常分支（`results.append(self.build_target_failed_result(...))` 之后）：

```python
                    failed_result = self.build_target_failed_result(target_info, str(e))
                    results.append(failed_result)
                    publish_done_sentinel(execution.id, failed_result.get("target_key", ""), ExecutionStatus.FAILED)
```

> 注意：异常分支原代码是 `results.append(self.build_target_failed_result(target_info, str(e)))`，需改为先赋值 `failed_result` 再 append，以便取 target_key。

3d. 在 `_handle_dangerous_command` 拦截返回 True 前，为所有目标发 done 哨兵。在 `execution.save(...)` 之后、`return True` 之前插入：

```python
        for t in target_list:
            tk = t.get("node_id") or str(t.get("target_id", ""))
            publish_done_sentinel(execution.id, tk, ExecutionStatus.FAILED)
        return True
```

3e. 在 `run()` 中、进入 `_run_via_sidecar` 之前确保 JetStream 流存在（保证 agent 首行即被捕获回放）。在 `run()` 里 `results = self._run_via_sidecar(...)` 之前插入：

```python
        try:
            ensure_stream_sync(JOB_LOG_STREAM_NAME, JOB_LOG_SUBJECTS, JOB_LOG_MAX_AGE_SECONDS, JOB_LOG_MAX_BYTES)
        except Exception as e:
            logger.warning(f"[{self.task_name}] JetStream 流声明失败(不阻断执行): {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/job_mgmt/tests/test_script_runner_streaming.py -v`
Expected: PASS (3 passed)。

再跑既有 runner 相关回归，确认未破坏：
Run: `pytest apps/job_mgmt/tests/ -k "runner or state_consistency or dangerous" -v`
Expected: 全部 PASS（既有用例不回归）。

- [ ] **Step 5: Commit**

```bash
git add server/apps/job_mgmt/services/script_execution_runner.py server/apps/job_mgmt/tests/test_script_runner_streaming.py
git commit -m "feat(job_mgmt): SSH 脚本执行接入流式(execute_ssh_stream + done 哨兵)"
```

---

## Task 7: SSE 端点（DRF action `stream`）

**Files:**
- Modify: `server/apps/job_mgmt/views/execution.py`
- Test: `server/apps/job_mgmt/tests/test_execution_views_stream.py`

> 路由由 DRF router 自动生成：`GET /api/v1/job_mgmt/api/execution/{pk}/stream/`。鉴权复用 `@HasPermission("job_record-View")` + `get_object()`（org 隔离）。终态执行走快照；非终态走 JetStream 实时；建流失败不阻断（best-effort）。

- [ ] **Step 1: Write the failing test**

```python
# server/apps/job_mgmt/tests/test_execution_views_stream.py
import asyncio
import json
from unittest.mock import patch

import pytest
from django.http import StreamingHttpResponse

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _collect(resp):
    async def _run():
        return [c.decode() if isinstance(c, bytes) else c async for c in resp.streaming_content]
    return asyncio.run(_run())


def _make_execution(status, results=None):
    return JobExecution.objects.create(
        name="t", job_type=JobType.SCRIPT, status=status,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}],
        execution_results=results or [], team=[1],
        created_by="testuser", updated_by="testuser",
    )


def test_stream_terminal_execution_returns_snapshot(api_client):
    execution = _make_execution(
        ExecutionStatus.SUCCESS,
        results=[{"target_key": "5", "stdout": "done-out", "stderr": ""}],
    )
    url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
    resp = api_client.get(url)
    assert isinstance(resp, StreamingHttpResponse)
    assert resp["Content-Type"].startswith("text/event-stream")
    chunks = _collect(resp)
    assert any("done-out" in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


def test_stream_running_execution_uses_live_generator(api_client):
    execution = _make_execution(ExecutionStatus.RUNNING)

    async def _fake_gen(*_a, **_k):
        yield "data: {\"line\": \"live\"}\n\n"
        yield "data: [DONE]\n\n"

    with patch("apps.job_mgmt.views.execution.stream_execution_events", side_effect=lambda *a, **k: _fake_gen()), \
         patch("apps.job_mgmt.views.execution.ensure_stream_sync") as mock_ensure:
        url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
        resp = api_client.get(url)
        assert isinstance(resp, StreamingHttpResponse)
        chunks = _collect(resp)

    mock_ensure.assert_called_once()
    assert any("live" in c for c in chunks)


def test_stream_running_execution_survives_ensure_stream_failure(api_client):
    execution = _make_execution(ExecutionStatus.RUNNING)

    async def _fake_gen(*_a, **_k):
        yield "data: [DONE]\n\n"

    with patch("apps.job_mgmt.views.execution.stream_execution_events", side_effect=lambda *a, **k: _fake_gen()), \
         patch("apps.job_mgmt.views.execution.ensure_stream_sync", side_effect=Exception("js down")):
        url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
        resp = api_client.get(url)
        assert isinstance(resp, StreamingHttpResponse)  # 不抛 500
        _collect(resp)


def test_stream_sets_sse_headers(api_client):
    execution = _make_execution(ExecutionStatus.SUCCESS, results=[])
    url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
    resp = api_client.get(url)
    assert resp["Cache-Control"] == "no-cache"
    assert resp["X-Accel-Buffering"] == "no"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/job_mgmt/tests/test_execution_views_stream.py -v`
Expected: FAIL — action `stream` 不存在（404）/ import 名缺失。

- [ ] **Step 3: Write minimal implementation**

3a. `server/apps/job_mgmt/views/execution.py` 顶部 import 区追加：

```python
from django.http import StreamingHttpResponse

from apps.job_mgmt.services.execution_stream_service import (
    JOB_LOG_MAX_AGE_SECONDS,
    JOB_LOG_MAX_BYTES,
    JOB_LOG_STREAM_NAME,
    JOB_LOG_SUBJECTS,
    snapshot_sse_from_results,
    stream_execution_events,
)
from nats_client.clients import ensure_stream_sync
```

3b. 在 `JobExecutionViewSet` 内（如 `targets` action 附近）新增 action：

```python
    @action(detail=True, methods=["get"])
    @HasPermission("job_record-View")
    def stream(self, request, pk=None):
        """SSE 实时流式输出：非终态走 JetStream 实时回放+tail，终态走结果快照。"""
        execution = self.get_object()
        target_keys = [
            (t.get("node_id") or str(t.get("target_id", "")))
            for t in (execution.target_list or [])
        ]

        if execution.status in ExecutionStatus.TERMINAL_STATES:
            generator = snapshot_sse_from_results(execution.execution_results or [])
        else:
            try:
                ensure_stream_sync(JOB_LOG_STREAM_NAME, JOB_LOG_SUBJECTS, JOB_LOG_MAX_AGE_SECONDS, JOB_LOG_MAX_BYTES)
            except Exception as e:
                logger.warning(f"[stream] JetStream 流声明失败(降级继续): execution_id={execution.id}, error={e}")
            generator = stream_execution_events(execution.id, target_keys)

        response = StreamingHttpResponse(generator, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/job_mgmt/tests/test_execution_views_stream.py -v`
Expected: PASS (4 passed)。

- [ ] **Step 5: Commit**

```bash
git add server/apps/job_mgmt/views/execution.py server/apps/job_mgmt/tests/test_execution_views_stream.py
git commit -m "feat(job_mgmt): 新增脚本执行 SSE 端点 /execution/{id}/stream/"
```

---

## Task 8: 覆盖率校验（≥90%）与收尾

**Files:** 无新增；仅运行与（如需）补测。

- [ ] **Step 1: 运行目标模块覆盖率**

Run:
```
pytest apps/job_mgmt/tests/test_execution_stream_service_pure.py \
       apps/job_mgmt/tests/test_execution_stream_service_async.py \
       apps/job_mgmt/tests/test_execution_views_stream.py \
       apps/job_mgmt/tests/test_script_runner_streaming.py \
       nats_client/tests/test_stream_primitives.py \
       --cov=apps.job_mgmt.services.execution_stream_service \
       --cov=apps.job_mgmt.views.execution \
       --cov=nats_client.clients \
       --cov-report=term-missing
```
Expected: `execution_stream_service.py` 与 `views/execution.py` 行覆盖率 ≥ 90%（标 `# pragma: no cover` 的 `iter_jetstream_subject` / `_default_message_source` 不计入）。`nats_client.clients` 仅新增函数需覆盖，老函数 miss 属既有范围，可用更聚焦的 `--cov` 仅看新增（见下）。

- [ ] **Step 2: 若某新增模块 < 90%，按 term-missing 行号补最小测试**

针对 miss 行补一条直达该分支的单测（例如 `snapshot` 中 stdout 为空只发 stderr 的分支、`stream_execution_events` 自定义 `message_source=None` 的默认分支用 monkeypatch `_default_message_source` 覆盖）。补后回到 Step 1 重跑直至达标。

示例（覆盖 `message_source is None` 默认分支而不触真实 NATS）：

```python
def test_stream_events_uses_default_source_when_none(monkeypatch):
    async def _fake_default(execution_id):
        yield {"target_key": "a", "type": svc.DONE_TYPE, "status": "success"}
    monkeypatch.setattr(svc, "_default_message_source", _fake_default)
    chunks = _collect(svc.stream_execution_events(1, ["a"]))
    assert chunks[-1] == "data: [DONE]\n\n"
```
（加入 `test_execution_stream_service_async.py`。）

- [ ] **Step 3: 全量回归 job_mgmt**

Run: `pytest apps/job_mgmt/tests/ -q`
Expected: 全绿，无 warning 噪声。

- [ ] **Step 4: 最终提交**

```bash
git add server/apps/job_mgmt/tests/
git commit -m "test(job_mgmt): 流式输出 P1 覆盖率补齐(≥90%)"
```

---

## 自查（Self-Review）

**Spec 覆盖映射：**
- §4.1 主题约定 → Task 1 `build_stream_topic` / `parse_target_key`。
- §4.1 done 哨兵 → Task 4 `publish_done_sentinel` + Task 6 runner 发哨兵。
- §4.2 JetStream 流声明 → Task 3 `ensure_stream_sync` + Task 6 `run()` 前置 + Task 7 端点前置。
- §5 P1 SSH 接线 → Task 6 `execute_ssh_stream`。
- §6 SSE 端点（鉴权/终态快照/实时/降级/清理）→ Task 7（鉴权=`HasPermission`+`get_object`；终态=snapshot；实时=stream_execution_events；降级=ensure 失败不阻断 + 源异常转 error 事件；清理=`iter_jetstream_subject` finally）。
- §6 历史回放+实时一条订阅 → Task 5 聚合器 + Task 3 `DeliverPolicy.ALL` 有序消费者。
- §9 测试分层与 ≥90% → 各 Task 的 `_pure`/`_service`/`_views` + Task 8 覆盖率门。
- §4 最终落库不变 → Task 6 仅改调用名，返回值映射逻辑保持。

**占位符扫描：** 无 TBD/TODO；每个代码步骤含完整代码。

**类型/名称一致性核对：** `build_stream_topic`、`format_sse_event`、`parse_target_key`、`ExecutionStreamAggregator.process/is_complete`、`publish_done_sentinel(execution_id, target_key, status)`、`snapshot_sse_from_results(results)`、`stream_execution_events(execution_id, target_keys, message_source=None)`、`ensure_stream_sync(name, subjects, max_age, max_bytes)`、`publish_raw_sync(subject, payload)`、常量 `JOB_LOG_STREAM_NAME/JOB_LOG_SUBJECTS/JOB_LOG_MAX_AGE_SECONDS/JOB_LOG_MAX_BYTES/DONE_TYPE` —— 全计划前后一致。

**范围：** 仅 P1（SSH）。本地执行（P2，需改 Go agent）与 Ansible（P3）不在本计划内，按 spec 分阶段单独成计划。

---

## 本地验证场景（实现完成后交付，你执行）

启动三件套（见 spec §10 命令；均用 `D:\app\venv\bkliteserver`）：uvicorn(:8011) + celery worker + nats_listener，且环境内有可达 NATS(JetStream 开启) 与已注册 SSH agent。

1. **实时滚动**：对一个 MANUAL/SSH 目标快速执行一个分段输出脚本（如 `for i in 1 2 3; do echo line-$i; sleep 1; done`），详情页应逐行实时滚出。
2. **迟到看历史**：脚本执行到一半再打开 `GET /api/execution/{id}/stream/`，应先回放已产生的行再续实时。
3. **多目标并发**：选 2+ SSH 目标，按 target 分面板各自滚动、互不串扰，全部 done 后连接关闭。
4. **终态快照**：执行结束后再打开端点，直接吐 `execution_results` 历史 + `[DONE]`，不建消费者。
5. **降级**：临时关闭/隔离 JetStream，端点不应 500；执行仍正常落库，最终结果可见。
6. **高危拦截**：执行含高危命令的脚本，端点应很快收到各目标 done(failed) 并收尾，不空等。
