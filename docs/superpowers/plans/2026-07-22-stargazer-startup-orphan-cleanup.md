# Stargazer Startup Orphan Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sanic 正常启动后异步执行一次全局选主、资源有界、原子且 fail-open 的孤儿 running/dedupe marker 清理。

**Architecture:** 新建独立异步核心服务负责配置、Redis 锁、两阶段扫描和 Lua 原子删除；`TaskQueue` 生命周期只创建、持有和取消后台任务。自动模式只删除明确孤儿 marker，现有人工 CLI 的 pending/in-progress、备份和恢复语义保持不变。

**Tech Stack:** Python 3.12、Sanic 24.6、ARQ/redis-py asyncio、Redis Lua、pytest/pytest-asyncio。

## Global Constraints

- 多个 Stargazer 容器和每容器多个 Sanic worker 共享同一 Redis；同一时刻最多一个自动清理器工作。
- `after_server_start` 只调度后台 task，不等待清理完成。
- 只删除 `task:running:*`、`task:dedupe:*` 中明确孤儿的 marker；不得删除 queue、job、retry、result、in-progress 或其他 key。
- 候选必须经过第一次检查、默认 5 秒等待、Lua 原子二次确认。
- 默认开启；最大检查 10,000 个 marker；总预算 30 秒；锁 TTL 60 秒。
- Redis、配置、超时、锁竞争和单 marker 错误全部 fail-open，只记录脱敏结构化日志。
- 保留现有 `scripts/clear_task_queue.py`、DUMP 备份和恢复能力，不新增 HTTP 接口。
- 新功能严格执行 TDD；触及代码 Black/isort/flake8 通过，相关测试覆盖率不低于 75%。

---

## File Structure

- Create: `agents/stargazer/core/task_queue_startup_cleanup.py` — 配置、结果模型、分布式锁、扫描、两阶段确认、Lua 删除和锁释放。
- Modify: `agents/stargazer/core/task_queue.py` — 在 Sanic 生命周期中非阻塞创建、记录和取消后台任务。
- Create: `agents/stargazer/tests/test_task_queue_startup_cleanup.py` — 核心服务、资源边界和生命周期单元测试。
- Modify: `agents/stargazer/tests/test_task_queue_cleanup_redis_integration.py` — 真实 Redis 的锁和竞态验证。
- Modify: `agents/stargazer/tests/test_dependency_lock_contract.py` — 镜像/Runbook 自动清理能力合同。
- Modify: `agents/stargazer/README.md` — 默认行为、环境变量、日志、关闭方式和人工 CLI 边界。

---

### Task 1: 异步孤儿 marker 清理核心服务

**Files:**
- Create: `agents/stargazer/core/task_queue_startup_cleanup.py`
- Create: `agents/stargazer/tests/test_task_queue_startup_cleanup.py`

**Interfaces:**
- Consumes: 异步 Redis 客户端，支持 `set/get/exists/zscore/scan_iter/eval`。
- Produces: `StartupCleanupConfig.from_env()`、`StartupCleanupResult`、`cleanup_startup_orphan_markers(redis, config, *, sleep=asyncio.sleep)`。

- [ ] **Step 1: 编写配置和结果模型的失败测试**

```python
def test_startup_cleanup_config_uses_safe_defaults():
    config = StartupCleanupConfig.from_env({})
    assert config.enabled is True
    assert config.confirm_delay_seconds == 5
    assert config.max_markers == 10_000
    assert config.timeout_seconds == 30


@pytest.mark.parametrize(
    "env",
    [
        {"TASK_QUEUE_STARTUP_ORPHAN_CONFIRM_DELAY_SECONDS": "-1"},
        {"TASK_QUEUE_STARTUP_ORPHAN_MAX_MARKERS": "0"},
        {"TASK_QUEUE_STARTUP_ORPHAN_TIMEOUT_SECONDS": "not-a-number"},
    ],
)
def test_startup_cleanup_config_rejects_unsafe_values(env):
    with pytest.raises(StartupCleanupConfigError):
        StartupCleanupConfig.from_env(env)
```

- [ ] **Step 2: 运行配置测试确认 RED**

Run:

```bash
cd agents/stargazer
./.venv/bin/pytest tests/test_task_queue_startup_cleanup.py -q
```

Expected: 测试收集因 `core.task_queue_startup_cleanup` 不存在而失败。

- [ ] **Step 3: 实现最小配置和结果接口**

```python
@dataclass(frozen=True)
class StartupCleanupConfig:
    enabled: bool = True
    confirm_delay_seconds: float = 5
    max_markers: int = 10_000
    timeout_seconds: float = 30
    lock_ttl_seconds: int = 60

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "StartupCleanupConfig": ...


@dataclass(frozen=True)
class StartupCleanupResult:
    status: Literal["success", "skipped", "warning"]
    reason: str | None
    scanned: int
    candidates: int
    deleted: int
    preserved: int
    errors: int
    truncated: bool
```

布尔值只接受 `true/false/1/0/yes/no/on/off`；负 delay、非正 max/timeout，或 `timeout_seconds >= lock_ttl_seconds` 时抛 `StartupCleanupConfigError`，禁止用不确定配置执行删除。

- [ ] **Step 4: 增加锁、删除边界和两阶段竞态失败测试**

```python
@pytest.mark.asyncio
async def test_cleanup_deletes_only_confirmed_orphan_markers(fake_redis):
    fake_redis.strings.update({
        b"task:running:orphan": b"orphan-job",
        b"task:dedupe:queued": b"queued-job",
        b"task:running:active": b"active-job",
        b"credential:state:1": b"keep",
    })
    fake_redis.queue[b"queued-job"] = 1000.0
    fake_redis.strings[b"arq:in-progress:active-job"] = b"1"

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=0),
    )

    assert result.deleted == 1
    assert b"task:running:orphan" not in fake_redis.strings
    assert b"task:dedupe:queued" in fake_redis.strings
    assert b"task:running:active" in fake_redis.strings
    assert fake_redis.strings[b"credential:state:1"] == b"keep"


@pytest.mark.asyncio
async def test_second_phase_preserves_marker_when_job_becomes_active(fake_redis):
    fake_redis.strings[b"task:dedupe:key"] = b"job-1"

    async def activate_during_delay(_seconds):
        fake_redis.queue[b"job-1"] = 2000.0

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=activate_during_delay,
    )

    assert result.deleted == 0
    assert result.preserved == 1
    assert b"task:dedupe:key" in fake_redis.strings
```

同一测试文件还必须覆盖：marker 值被替换、非 string marker、锁未获得、扫描上限、timeout、单 marker Lua 错误、只按 token 释放锁。Fake Redis 必须实现异步 `set/get/exists/zscore/scan_iter/eval`，并记录所有写命令，测试需断言唯一业务写入是符合条件 marker 的 `DEL`。

- [ ] **Step 5: 运行核心行为测试确认 RED**

Run:

```bash
./.venv/bin/pytest tests/test_task_queue_startup_cleanup.py -q
```

Expected: 接口存在，但锁、扫描或 Lua 行为断言失败。

- [ ] **Step 6: 实现分布式锁、有界扫描和 Lua 原子删除**

模块固定常量：

```python
LOCK_KEY = b"stargazer:maintenance:startup-orphan-cleanup"
QUEUE_KEY = b"arq:queue"
MARKER_PATTERNS = (b"task:running:*", b"task:dedupe:*")
IN_PROGRESS_PREFIX = b"arq:in-progress:"
```

原子删除脚本必须只有一个写操作：

```lua
local marker_value = redis.call('GET', KEYS[1])
if marker_value ~= ARGV[1] then
    return 0
end
if redis.call('ZSCORE', KEYS[2], ARGV[1]) then
    return 0
end
if redis.call('EXISTS', KEYS[3]) ~= 0 then
    return 0
end
return redis.call('DEL', KEYS[1])
```

锁释放脚本必须先比较 token：

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

核心流程使用 `asyncio.timeout(config.timeout_seconds)`；`SCAN` 每批 `count=500`，`scanned` 达到 `max_markers` 后停止；第一次确认只保存 `(marker_key, job_id)`；所有候选统一 `await sleep(confirm_delay_seconds)` 后逐个执行 Lua。错误 marker 保留并增加 `errors`，不得扩大删除范围。

结果状态固定映射如下，禁止调用方猜测：

```python
# lock 未获得
StartupCleanupResult(status="skipped", reason="lock_not_acquired", ...)
# 达到扫描上限
StartupCleanupResult(status="warning", reason="limit_reached", truncated=True, ...)
# 超过总预算
StartupCleanupResult(status="warning", reason="timeout", ...)
# 至少一个 marker 检查失败，但其余候选已安全处理
StartupCleanupResult(status="warning", reason="marker_errors", errors=n, ...)
# 无异常完成，包括没有候选
StartupCleanupResult(status="success", reason=None, ...)
```

Redis 连接、锁获取或无法安全分类的全局异常向上抛出，由 Task 2 的生命周期包装器转换成固定 `reason=redis_error` 告警；异常原文不得进入日志。锁释放必须位于 `finally`，且释放失败不得触发第二次删除或阻碍 Sanic。

- [ ] **Step 7: 运行核心测试确认 GREEN**

Run:

```bash
./.venv/bin/pytest tests/test_task_queue_startup_cleanup.py -q
```

Expected: 全部通过。

- [ ] **Step 8: 提交核心服务**

```bash
git add agents/stargazer/core/task_queue_startup_cleanup.py \
  agents/stargazer/tests/test_task_queue_startup_cleanup.py
git commit -m "feat(stargazer): 自动清理孤儿任务标记"
```

---

### Task 2: Sanic 非阻塞生命周期接入

**Files:**
- Modify: `agents/stargazer/core/task_queue.py:89-140`
- Modify: `agents/stargazer/tests/test_task_queue_startup_cleanup.py`

**Interfaces:**
- Consumes: Task 1 的 `StartupCleanupConfig.from_env()`、`cleanup_startup_orphan_markers(redis, config)` 和 `StartupCleanupResult`。
- Produces: `TaskQueue._startup_cleanup_task: asyncio.Task | None`、`TaskQueue._run_startup_cleanup()`。

- [ ] **Step 1: 编写生命周期失败测试**

```python
def test_task_queue_registers_non_blocking_startup_cleanup_listener():
    app = Sanic("StartupCleanupLifecycle")
    queue = TaskQueue(app)
    listeners = {
        (listener.event, listener.listener.__name__)
        for listener in app._future_listeners
    }
    assert ("after_server_start", "start_orphan_cleanup") in listeners
    assert ("after_server_stop", "stop_task_queue") in listeners
    assert queue._startup_cleanup_task is None


@pytest.mark.asyncio
async def test_start_listener_schedules_without_waiting(monkeypatch):
    blocker = asyncio.Event()
    app = Sanic("StartupCleanupNonBlocking")
    queue = TaskQueue(app)
    queue.pool = AsyncMock()

    async def cleanup(*_args, **_kwargs):
        await blocker.wait()

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    start_listener = next(
        item.listener
        for item in app._future_listeners
        if item.event == "after_server_start"
        and item.listener.__name__ == "start_orphan_cleanup"
    )

    await start_listener(app, None)

    assert queue._startup_cleanup_task is not None
    assert not queue._startup_cleanup_task.done()
```

补充失败测试：feature flag=false 不创建 task；后台异常只记录 `event=task_queue_startup_cleanup status=warning`；日志不包含 job ID、异常原文或 Redis 密码；stop listener 会 cancel/await 后台 task 再关闭 pool。

- [ ] **Step 2: 运行生命周期测试确认 RED**

Run:

```bash
./.venv/bin/pytest tests/test_task_queue_startup_cleanup.py -q
```

Expected: 缺少 listener、task 字段或取消逻辑而失败。

- [ ] **Step 3: 实现非阻塞 listener 和脱敏日志**

在 `TaskQueue.__init__` 增加：

```python
self._startup_cleanup_task: Optional[asyncio.Task] = None
```

生命周期使用以下结构，不在 listener 内 await 清理：

```python
@self.app.listener("after_server_start")
async def start_orphan_cleanup(app, loop):
    try:
        config = StartupCleanupConfig.from_env()
    except StartupCleanupConfigError:
        logger.warning(
            "event=task_queue_startup_cleanup status=warning reason=invalid_config"
        )
        return
    if not config.enabled:
        logger.info(
            "event=task_queue_startup_cleanup status=skipped reason=disabled"
        )
        return
    self._startup_cleanup_task = asyncio.create_task(
        self._run_startup_cleanup(config),
        name="stargazer-startup-orphan-cleanup",
    )
```

`_run_startup_cleanup()` 捕获所有异常，只输出固定 reason；成功日志只使用 `StartupCleanupResult` 的计数字段。`after_server_stop` 先 cancel/await `_startup_cleanup_task`，吞掉 `CancelledError`，再执行现有健康检查取消和 Redis pool 关闭。

- [ ] **Step 4: 运行生命周期和既有 TaskQueue 测试确认 GREEN**

Run:

```bash
./.venv/bin/pytest \
  tests/test_task_queue_startup_cleanup.py \
  tests/test_collect_multicred.py \
  tests/test_host_collector.py::TestWorkerRunningFlag \
  tests/test_host_collector.py::TestHostRemoteRuntime \
  -q
```

Expected: 全部通过；现有 enqueue/TTL/host callback 行为不变。

- [ ] **Step 5: 提交生命周期接入**

```bash
git add agents/stargazer/core/task_queue.py \
  agents/stargazer/tests/test_task_queue_startup_cleanup.py
git commit -m "feat(stargazer): 启动后异步回收孤儿标记"
```

---

### Task 3: 真实 Redis 竞态、Runbook 与最终门禁

**Files:**
- Modify: `agents/stargazer/tests/test_task_queue_cleanup_redis_integration.py`
- Modify: `agents/stargazer/tests/test_dependency_lock_contract.py`
- Modify: `agents/stargazer/README.md:270-340`

**Interfaces:**
- Consumes: Task 1/2 的环境变量、锁 key、核心清理入口和结构化日志事件。
- Produces: 可部署 Runbook 和真实 Redis 并发回归证据。

- [ ] **Step 1: 编写真实 Redis 和 Runbook 失败测试**

先将现有临时 Redis 进程 fixture 拆成共享 socket fixture，并增加异步客户端；同步备份/恢复测试继续复用原客户端：

```python
from redis.asyncio import Redis as AsyncRedis


@pytest.fixture
def redis_server_socket(tmp_path):
    redis_server = shutil.which("redis-server")
    if redis_server is None:
        pytest.skip("redis-server is not installed")
    socket_path = Path("/tmp") / (
        f"stargazer-redis-{secrets.token_hex(6)}.sock"
    )
    process = subprocess.Popen(
        [
            redis_server,
            "--save", "",
            "--appendonly", "no",
            "--port", "0",
            "--unixsocket", str(socket_path),
            "--unixsocketperm", "700",
            "--dir", str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    probe = Redis(unix_socket_path=str(socket_path), db=15)
    try:
        for _attempt in range(100):
            try:
                if probe.ping():
                    break
            except RedisConnectionError:
                time.sleep(0.01)
        else:
            diagnostics = process.stderr.read() if process.poll() is not None else ""
            pytest.fail(f"temporary redis-server did not start: {diagnostics}")
        yield socket_path
    finally:
        probe.close()
        process.terminate()
        process.wait(timeout=5)
        socket_path.unlink(missing_ok=True)


@pytest_asyncio.fixture
async def real_async_redis(redis_server_socket):
    client = AsyncRedis(
        unix_socket_path=str(redis_server_socket),
        db=15,
        decode_responses=False,
    )
    await client.flushdb()
    try:
        yield client
    finally:
        await client.aclose()
```

现有同步 `real_redis` fixture 改为从 `redis_server_socket` 构造 `Redis`，测试前后执行 `flushdb()`，不得再自行启动第二个 Redis 进程。

```python
@pytest.mark.asyncio
async def test_real_redis_second_phase_preserves_reactivated_job(real_async_redis):
    await real_async_redis.set(b"task:dedupe:key", b"job-1", ex=600)

    async def reactivate(_seconds):
        await real_async_redis.zadd(b"arq:queue", {b"job-1": 1000.0})

    result = await cleanup_startup_orphan_markers(
        real_async_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=reactivate,
    )

    assert result.deleted == 0
    assert await real_async_redis.get(b"task:dedupe:key") == b"job-1"


def test_runbook_documents_startup_orphan_cleanup_toggle():
    readme = README_PATH.read_text(encoding="utf-8")
    assert "TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED=false" in readme
    assert "只删除明确孤儿" in readme
    assert "不影响 Sanic 启动" in readme
```

真实 Redis 还必须覆盖：两个清理器并发仅一个获取锁；第一次扫描后 marker 值被替换；原子 Lua 只删除 marker；非本实例 token 不能释放锁。

- [ ] **Step 2: 运行新增测试确认 RED**

Run:

```bash
./.venv/bin/pytest \
  tests/test_task_queue_cleanup_redis_integration.py \
  tests/test_dependency_lock_contract.py::test_docker_context_and_runbook_expose_task_queue_cleanup_cli \
  -q
```

Expected: Runbook 断言及新增真实 Redis 自动清理断言失败。

- [ ] **Step 3: 更新 README 运维说明**

README 必须明确写出：

```text
- 自动任务在 Sanic 可用后后台运行，不阻塞启动。
- 多副本通过共享 Redis 锁选主。
- 自动模式只删除明确孤儿 marker，不删除任何 pending/in-progress/job/result。
- 默认开启；紧急关闭：TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED=false。
- 默认确认等待 5 秒、最大 10000、总预算 30 秒。
- status=warning 只表示自动恢复未完成，服务仍继续运行；复杂堵塞使用人工 CLI dry-run。
```

- [ ] **Step 4: 运行真实 Redis 与文档合同确认 GREEN**

Run:

```bash
./.venv/bin/pytest \
  tests/test_task_queue_cleanup_redis_integration.py \
  tests/test_dependency_lock_contract.py::test_docker_context_and_runbook_expose_task_queue_cleanup_cli \
  -q
```

Expected: 全部通过。在 macOS Codex 沙箱禁止 Unix socket bind 时，必须在已批准的沙箱外本地临时 Redis 中复跑；临时 Redis 关闭持久化，测试结束后终止进程并删除 socket。

- [ ] **Step 5: 运行完整相关回归**

Run:

```bash
./.venv/bin/pytest \
  tests/test_task_queue_startup_cleanup.py \
  tests/test_task_queue_cleanup.py \
  tests/test_task_queue_cleanup_cli.py \
  tests/test_task_queue_cleanup_redis_integration.py \
  tests/test_dependency_lock_contract.py \
  tests/test_collect_multicred.py \
  tests/test_host_collector.py::TestWorkerRunningFlag \
  tests/test_host_collector.py::TestHostRemoteRuntime \
  -q
```

Expected: 全部通过。既有 `test_locked_sync_rejects_stale_lockfile_offline` 若在沙箱内触发 uv/SystemConfiguration panic，按已记录环境约束在沙箱外单独复跑，不得忽略业务失败。

- [ ] **Step 6: 运行触及文件静态门禁**

Run:

```bash
black --check --line-length 79 \
  core/task_queue_startup_cleanup.py core/task_queue.py \
  tests/test_task_queue_startup_cleanup.py \
  tests/test_task_queue_cleanup_redis_integration.py \
  tests/test_dependency_lock_contract.py
isort --check-only --profile black --line-length 79 \
  core/task_queue_startup_cleanup.py core/task_queue.py \
  tests/test_task_queue_startup_cleanup.py \
  tests/test_task_queue_cleanup_redis_integration.py \
  tests/test_dependency_lock_contract.py
flake8 \
  core/task_queue_startup_cleanup.py core/task_queue.py \
  tests/test_task_queue_startup_cleanup.py \
  tests/test_task_queue_cleanup_redis_integration.py \
  tests/test_dependency_lock_contract.py
git diff --check
```

Expected: 全部退出 0。`make lint` 当前因 Stargazer 缺少 `.pre-commit-config.yaml` 已有独立问题 #0730，本变更不扩大范围修复该基线问题。

- [ ] **Step 7: 提交 Runbook 和集成验证**

```bash
git add agents/stargazer/README.md \
  agents/stargazer/tests/test_dependency_lock_contract.py \
  agents/stargazer/tests/test_task_queue_cleanup_redis_integration.py
git commit -m "docs(stargazer): 补充启动孤儿标记清理说明"
```

- [ ] **Step 8: 请求独立代码审查并修复所有 Critical/Important**

审查范围为本计划开始前的 HEAD 到最终 HEAD，重点检查：Lua 删除边界、共享 Redis 锁、Sanic 非阻塞生命周期、停止取消、资源上限、日志脱敏和人工 CLI 回归。修复后重新执行 Step 5、Step 6。
