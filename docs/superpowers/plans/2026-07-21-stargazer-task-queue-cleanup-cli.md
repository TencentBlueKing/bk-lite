# Stargazer 任务队列清理 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Stargazer 提供容器内长期运维 CLI，以 dry-run 默认、显式 apply、受限 in-progress 清理、删除前备份和并发漂移保护安全解除 ARQ 队列堵塞。

**Architecture:** 将 Redis 目标识别、备份和 `WATCH/MULTI/EXEC` 删除放入同步核心服务 `core/task_queue_cleanup.py`，将参数、连接、输出和退出码放入薄入口 `scripts/clear_task_queue.py`。测试使用内存 fake Redis/pipeline 验证行为，不连接真实 Redis；CLI 通过依赖注入入口测试参数与错误映射。

**Tech Stack:** Python 3.12、redis-py 5+、ARQ 常量、argparse、pytest、Black、isort、flake8。

## Global Constraints

- 默认必须 dry-run，只有 `--apply` 修改 Redis。
- 默认只选被 `task:running:*`/`task:dedupe:*` 引用、仍在 `arq:queue` 且不在 in-progress 的阻塞 job。
- `--all-pending` 才选择默认 ARQ 队列全部安全待执行 job。
- `--include-in-progress` 必须与 `--worker-stopped`、`--apply` 同时使用，并只扩展到相关 job。
- 正式删除前必须创建 `0700` 目录与 `0600` DUMP 备份；备份失败零删除。
- 删除必须使用 `WATCH/MULTI/EXEC`；并发变化返回状态漂移，禁止按过期计划删除。
- 禁止 `KEYS`、`FLUSHDB`、HTTP 清理接口、自动停 Worker、跳过备份和通配符删除。
- 输出与日志不得包含 Redis 密码、任务 payload 或 DUMP 内容。
- 仅修改本需求相关 Stargazer 文件；测试先 RED 后 GREEN。

---

## File Structure

- Create `agents/stargazer/core/task_queue_cleanup.py`：不可变计划/结果类型、目标扫描、备份、指纹复核和事务删除。
- Create `agents/stargazer/scripts/__init__.py`：声明运维脚本包。
- Create `agents/stargazer/scripts/clear_task_queue.py`：固定容器 CLI 入口、参数验证、Redis 连接、输出和退出码。
- Create `agents/stargazer/tests/test_task_queue_cleanup.py`：核心服务行为与安全边界测试。
- Create `agents/stargazer/tests/test_task_queue_cleanup_cli.py`：CLI 参数、JSON、退出码和 import path 合同。
- Modify `agents/stargazer/README.md`：服务器、Docker、Kubernetes 运维 runbook。
- Modify `agents/stargazer/tests/test_dependency_lock_contract.py`：镜像内脚本路径合同。

---

### Task 1: 清理计划与目标选择

**Files:**
- Create: `agents/stargazer/core/task_queue_cleanup.py`
- Create: `agents/stargazer/tests/test_task_queue_cleanup.py`

**Interfaces:**
- Produces: `CleanupPlan`, `CleanupStateError`, `build_cleanup_plan(redis_client, *, all_pending: bool, include_in_progress: bool) -> CleanupPlan`
- Consumes: redis-py 同步 client 的 `scan_iter/get/zrange/zscore/exists/type`。

- [ ] **Step 1: 写默认目标选择失败测试**

在 `tests/test_task_queue_cleanup.py` 建立只实现读 API 的 `FakeRedis`，并锁定以下行为：

```python
def test_default_plan_selects_only_marker_referenced_queued_jobs():
    redis_client = FakeRedis(
        queue={b"queued-blocker": 1000.0, b"unrelated": 2000.0},
        strings={
            b"task:running:task-1": b"queued-blocker",
            b"task:dedupe:key-1": b"queued-blocker",
            b"task:running:task-2": b"running-job",
            b"arq:in-progress:running-job": b"1",
        },
    )

    plan = build_cleanup_plan(
        redis_client,
        all_pending=False,
        include_in_progress=False,
    )

    assert plan.selected_job_ids == (b"queued-blocker",)
    assert plan.protected_job_ids == (b"running-job",)
    assert plan.marker_keys == (
        b"task:dedupe:key-1",
        b"task:running:task-1",
    )
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
cd agents/stargazer
uv run pytest tests/test_task_queue_cleanup.py::test_default_plan_selects_only_marker_referenced_queued_jobs -q
```

Expected: FAIL，`ModuleNotFoundError: core.task_queue_cleanup`。

- [ ] **Step 3: 实现不可变计划和默认选择**

实现以下公共结构和常量：

```python
from dataclasses import dataclass

from arq.constants import (
    default_queue_name,
    in_progress_key_prefix,
    job_key_prefix,
    retry_key_prefix,
)

RUNNING_PATTERN = "task:running:*"
DEDUPE_PATTERN = "task:dedupe:*"


class CleanupStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class CleanupPlan:
    all_pending: bool
    include_in_progress: bool
    selected_job_ids: tuple[bytes, ...]
    protected_job_ids: tuple[bytes, ...]
    marker_items: tuple[tuple[bytes, bytes], ...]
    queue_scores: tuple[tuple[bytes, float], ...]
    fingerprint: tuple[tuple[str, str, str], ...]

    @property
    def marker_keys(self) -> tuple[bytes, ...]:
        return tuple(key for key, _job_id in self.marker_items)
```

`build_cleanup_plan` 必须：

```python
def build_cleanup_plan(redis_client, *, all_pending, include_in_progress):
    queue_items = tuple(redis_client.zrange(default_queue_name, 0, -1, withscores=True))
    queue_scores = {normalize_bytes(job_id): float(score) for job_id, score in queue_items}
    marker_items = read_marker_items(redis_client)
    in_progress = {
        job_id
        for job_id in set(queue_scores) | set(marker_items.values())
        if redis_client.exists(f"{in_progress_key_prefix}{job_id.decode()}")
    }
    base_candidates = (
        set(queue_scores)
        if all_pending
        else set(marker_items.values()) & set(queue_scores)
    )
    related_in_progress = in_progress & (set(queue_scores) | set(marker_items.values()))
    selected = base_candidates - in_progress
    if include_in_progress:
        selected |= related_in_progress
    protected = related_in_progress - selected
    selected_markers = tuple(
        sorted((key, job_id) for key, job_id in marker_items.items() if job_id in selected)
    )
    selected_markers = tuple(
        sorted((key, job_id) for key, job_id in marker_items.items() if job_id in selected)
    )
    selected_scores = tuple(
        sorted((job_id, queue_scores[job_id]) for job_id in selected if job_id in queue_scores)
    )
    return CleanupPlan(
        all_pending=all_pending,
        include_in_progress=include_in_progress,
        selected_job_ids=tuple(sorted(selected)),
        protected_job_ids=tuple(sorted(protected)),
        marker_items=selected_markers,
        queue_scores=selected_scores,
        fingerprint=build_state_fingerprint(redis_client, selected, selected_markers),
    )
```

所有 SCAN 使用 `scan_iter(match=pattern, count=500)`；key/value 正规化为 bytes；遇到 `arq:queue` 非 `zset/none`、marker 非 `string` 或空 job ID 时抛 `CleanupStateError`，禁止猜测。

- [ ] **Step 4: 运行默认测试确认 GREEN**

Run:

```bash
uv run pytest tests/test_task_queue_cleanup.py::test_default_plan_selects_only_marker_referenced_queued_jobs -q
```

Expected: `1 passed`。

- [ ] **Step 5: 写 `--all-pending` 与 in-progress RED 测试**

增加：

```python
def test_all_pending_selects_unreferenced_queue_jobs():
    plan = build_cleanup_plan(
        redis_with_queue(b"referenced", b"unreferenced"),
        all_pending=True,
        include_in_progress=False,
    )
    assert plan.selected_job_ids == (b"referenced", b"unreferenced")


def test_default_plan_never_selects_in_progress_job():
    plan = build_cleanup_plan(
        redis_with_referenced_in_progress_job(b"running-job"),
        all_pending=False,
        include_in_progress=False,
    )
    assert plan.selected_job_ids == ()
    assert plan.protected_job_ids == (b"running-job",)


def test_include_in_progress_selects_only_related_jobs():
    redis_client = redis_with_referenced_in_progress_job(b"running-job")
    redis_client.strings[b"arq:in-progress:unrelated"] = b"1"
    plan = build_cleanup_plan(
        redis_client,
        all_pending=False,
        include_in_progress=True,
    )
    assert plan.selected_job_ids == (b"running-job",)
    assert b"unrelated" not in plan.selected_job_ids


def test_plan_rejects_wrong_redis_types():
    redis_client = FakeRedis(queue_type=b"list")
    with pytest.raises(CleanupStateError, match="arq:queue"):
        build_cleanup_plan(redis_client, all_pending=False, include_in_progress=False)


def test_plan_uses_scan_instead_of_keys():
    redis_client = FakeRedis()
    build_cleanup_plan(redis_client, all_pending=False, include_in_progress=False)
    assert redis_client.keys_calls == 0
    assert redis_client.scan_patterns == [b"task:running:*", b"task:dedupe:*"]
```

关键断言：`all_pending=True` 选择所有非 in-progress queue members；`include_in_progress=True` 只选择 queue/marker 相关锁，不纳入无关 `arq:in-progress:unrelated`。

- [ ] **Step 6: 运行新增测试确认 RED 后补齐最小实现**

Run:

```bash
uv run pytest tests/test_task_queue_cleanup.py -q
```

Expected before implementation: 新增行为断言 FAIL；补齐后全部 PASS。

- [ ] **Step 7: 提交 Task 1**

```bash
git add agents/stargazer/core/task_queue_cleanup.py agents/stargazer/tests/test_task_queue_cleanup.py
git commit -m "feat(stargazer): 生成队列清理计划"
```

---

### Task 2: 安全备份、漂移检测与精准删除

**Files:**
- Modify: `agents/stargazer/core/task_queue_cleanup.py`
- Modify: `agents/stargazer/tests/test_task_queue_cleanup.py`

**Interfaces:**
- Consumes: Task 1 `CleanupPlan` 与同一 Redis client。
- Produces: `CleanupBackupError`, `CleanupDriftError`, `CleanupExecutionError`, `CleanupResult`, `create_cleanup_backup(redis_client, plan, *, backup_dir: Path, redis_db: int) -> Path`, `apply_cleanup_plan(redis_client, plan) -> CleanupResult`。

- [ ] **Step 1: 写备份权限与内容 RED 测试**

```python
def test_backup_is_created_with_restricted_permissions(tmp_path):
    redis_client = redis_with_one_selected_job()
    plan = build_cleanup_plan(redis_client, all_pending=False, include_in_progress=False)

    backup_path = create_cleanup_backup(redis_client, plan, backup_dir=tmp_path / "backups")

    assert stat.S_IMODE(backup_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    assert payload["queue_scores"] == {"queued-blocker": 1000.0}
    assert payload["marker_items"]["task:running:task-1"] == "queued-blocker"
    assert payload["keys"]["arq:job:queued-blocker"]["dump"]
    assert "password" not in json.dumps(payload).lower()
```

- [ ] **Step 2: 运行备份测试确认 RED**

Run:

```bash
uv run pytest tests/test_task_queue_cleanup.py::test_backup_is_created_with_restricted_permissions -q
```

Expected: FAIL，`create_cleanup_backup` 尚不存在。

- [ ] **Step 3: 实现受限备份**

实现：

```python
class CleanupBackupError(RuntimeError):
    pass


def create_cleanup_backup(redis_client, plan, *, backup_dir, redis_db):
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    backup_path = backup_dir / f"stargazer-task-queue-{utc_timestamp()}-{secrets.token_hex(4)}.json"
    payload = build_backup_payload(redis_client, plan, redis_db=redis_db)
    fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, sort_keys=True)
            file_obj.flush()
            os.fsync(file_obj.fileno())
    except Exception as exc:
        backup_path.unlink(missing_ok=True)
        raise CleanupBackupError("failed to write cleanup backup") from exc
    return backup_path
```

目标键严格为选中 job 的 `arq:job:`、`arq:retry:`、按计划允许的 `arq:in-progress:` 和选中 marker。每个存在键保存 base64 DUMP、PTTL 和 Redis type；不得保存密码、host 明文或人类可读 payload。

- [ ] **Step 4: 运行备份测试确认 GREEN**

Run:

```bash
uv run pytest tests/test_task_queue_cleanup.py::test_backup_is_created_with_restricted_permissions -q
```

Expected: PASS。

- [ ] **Step 5: 写零删除、漂移和精准事务 RED 测试**

增加以下完整行为；每个测试都在调用后断言 `redis_client.write_calls == []` 或精确目标集合：

```python
def test_backup_failure_performs_no_redis_writes(tmp_path, monkeypatch):
    redis_client, plan = selected_plan_fixture()
    monkeypatch.setattr(os, "open", Mock(side_effect=OSError("read only")))
    with pytest.raises(CleanupBackupError):
        create_cleanup_backup(redis_client, plan, backup_dir=tmp_path, redis_db=1)
    assert redis_client.write_calls == []


def test_apply_rejects_queue_score_drift_without_deleting():
    redis_client, plan = selected_plan_fixture()
    redis_client.queue[b"queued-blocker"] = 9999.0
    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)
    assert redis_client.write_calls == []


def test_apply_rejects_marker_value_drift_without_deleting():
    redis_client, plan = selected_plan_fixture()
    redis_client.strings[b"task:running:task-1"] = b"replacement"
    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)
    assert redis_client.write_calls == []


def test_watch_error_is_reported_as_drift():
    redis_client, plan = selected_plan_fixture(watch_error=True)
    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)
    assert redis_client.committed_writes == []


def test_apply_deletes_only_selected_job_keys_and_markers():
    redis_client, plan = selected_plan_fixture(with_unrelated_keys=True)
    result = apply_cleanup_plan(redis_client, plan)
    assert result.deleted_job_count == 1
    assert b"unrelated-job" in redis_client.queue
    assert b"arq:result:queued-blocker" in redis_client.strings
    assert b"host_remote:callback:1" in redis_client.strings
    assert b"credential:state:1" in redis_client.strings
```

精准删除测试必须预置无关 queue job、result、callback 和 credential key，并断言它们全部保留。

- [ ] **Step 6: 实现 `WATCH/MULTI/EXEC`**

```python
@dataclass(frozen=True)
class CleanupResult:
    deleted_job_count: int
    deleted_marker_count: int
    remaining_queue_jobs: int


def apply_cleanup_plan(redis_client, plan):
    watch_keys = (default_queue_name, *plan.target_keys)
    try:
        with redis_client.pipeline() as pipe:
            pipe.watch(*watch_keys)
            current = build_cleanup_plan(
                pipe,
                all_pending=plan.all_pending,
                include_in_progress=plan.include_in_progress,
            )
            if current.fingerprint != plan.fingerprint:
                pipe.unwatch()
                raise CleanupDriftError("cleanup target state changed")
            pipe.multi()
            if plan.selected_job_ids:
                pipe.zrem(default_queue_name, *plan.selected_job_ids)
            if plan.target_keys:
                pipe.delete(*plan.target_keys)
            pipe.execute()
    except WatchError as exc:
        raise CleanupDriftError("cleanup target state changed") from exc
    except CleanupDriftError:
        raise
    except Exception as exc:
        raise CleanupExecutionError("cleanup transaction failed") from exc
    return CleanupResult(
        deleted_job_count=len(plan.selected_job_ids),
        deleted_marker_count=len(plan.marker_items),
        remaining_queue_jobs=redis_client.zcard(default_queue_name),
    )
```

`target_keys` 不包含 `arq:result:*`；只有 `plan.include_in_progress` 时才包含选中 job 的 in-progress key。

- [ ] **Step 7: 运行 Task 2 测试并提交**

```bash
uv run pytest tests/test_task_queue_cleanup.py -q
git add agents/stargazer/core/task_queue_cleanup.py agents/stargazer/tests/test_task_queue_cleanup.py
git commit -m "feat(stargazer): 安全备份并清理队列"
```

Expected: 全部 PASS。

---

### Task 3: 容器 CLI、参数安全门与稳定输出

**Files:**
- Create: `agents/stargazer/scripts/__init__.py`
- Create: `agents/stargazer/scripts/clear_task_queue.py`
- Create: `agents/stargazer/tests/test_task_queue_cleanup_cli.py`

**Interfaces:**
- Consumes: Task 1/2 核心服务和 `core.redis_config.REDIS_CONFIG`。
- Produces: `_build_parser() -> argparse.ArgumentParser`, `run(argv: Sequence[str], *, redis_factory=Redis) -> int`, `main() -> None`。

- [ ] **Step 1: 写 CLI 参数 RED 测试**

```python
@pytest.mark.parametrize(
    "argv",
    [
        ["--include-in-progress", "--apply"],
        ["--include-in-progress", "--worker-stopped"],
    ],
)
def test_include_in_progress_requires_apply_and_worker_confirmation(argv, capsys):
    assert cli.run(argv, redis_factory=unexpected_redis_factory) == 2
    assert "include-in-progress" in capsys.readouterr().err
```

另写 `test_default_cli_is_dry_run_and_does_not_create_backup`，断言无参数只调用 `build_cleanup_plan`，不调用 backup/apply。

- [ ] **Step 2: 运行测试确认 RED**

```bash
uv run pytest tests/test_task_queue_cleanup_cli.py -q
```

Expected: FAIL，CLI 模块不存在。

- [ ] **Step 3: 实现参数、连接和执行编排**

入口文件必须先把项目根加入 `sys.path`，然后导入 core：

```python
STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))
```

参数：

```python
parser.add_argument("--apply", action="store_true")
parser.add_argument("--all-pending", action="store_true")
parser.add_argument("--include-in-progress", action="store_true")
parser.add_argument("--worker-stopped", action="store_true")
parser.add_argument(
    "--backup-dir",
    type=Path,
    default=Path("/tmp/stargazer-task-queue-backups"),
)
parser.add_argument("--json", action="store_true")
```

`run` 流程：验证参数 → 创建 Redis client → PING → build plan → 输出 dry-run；apply 时 create backup → apply plan → 输出结果。已知异常映射为设计中的 `2..6`；未知异常不得输出 traceback 中的 Redis URL/密码，只输出稳定错误码和脱敏消息。

- [ ] **Step 4: 写 JSON、退出码和路径合同 RED 测试**

```python
def test_json_output_has_stable_safe_schema(capsys):
    assert cli.run(["--json"], redis_factory=safe_fake_redis_factory) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == EXPECTED_JSON_KEYS
    assert "password" not in json.dumps(payload).lower()


def test_redis_connection_failure_returns_three_without_secret(capsys):
    assert cli.run([], redis_factory=failing_redis_factory("secret-value")) == 3
    assert "secret-value" not in capsys.readouterr().err


def test_backup_failure_returns_four(monkeypatch):
    monkeypatch.setattr(cli, "create_cleanup_backup", Mock(side_effect=CleanupBackupError()))
    assert cli.run(["--apply"], redis_factory=safe_fake_redis_factory) == 4


def test_drift_returns_five(monkeypatch):
    monkeypatch.setattr(cli, "apply_cleanup_plan", Mock(side_effect=CleanupDriftError()))
    assert cli.run(["--apply"], redis_factory=safe_fake_redis_factory) == 5


def test_transaction_failure_returns_six(monkeypatch):
    monkeypatch.setattr(cli, "apply_cleanup_plan", Mock(side_effect=CleanupExecutionError()))
    assert cli.run(["--apply"], redis_factory=safe_fake_redis_factory) == 6
def test_absolute_script_path_can_import_core():
    result = subprocess.run(
        [sys.executable, str(STARGAZER_ROOT / "scripts" / "clear_task_queue.py"), "--help"],
        cwd="/",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
```

JSON keys必须固定为设计文档列出的 schema；job ID 允许输出，payload/password/DUMP 禁止输出。

- [ ] **Step 5: 补齐最小实现并验证 GREEN**

```bash
uv run pytest tests/test_task_queue_cleanup_cli.py -q
uv run pytest tests/test_task_queue_cleanup.py tests/test_task_queue_cleanup_cli.py -q
```

Expected: 全部 PASS，stderr/stdout 无秘密。

- [ ] **Step 6: 提交 Task 3**

```bash
git add agents/stargazer/scripts agents/stargazer/tests/test_task_queue_cleanup_cli.py
git commit -m "feat(stargazer): 增加队列清理 CLI"
```

---

### Task 4: 运维文档、镜像合同与最终门禁

**Files:**
- Modify: `agents/stargazer/README.md`
- Modify: `agents/stargazer/tests/test_dependency_lock_contract.py`
- Verify: all Task 1-3 files

**Interfaces:**
- Consumes: 完整 CLI 命令和退出码。
- Produces: 可复制的 Docker/Kubernetes runbook 与镜像路径回归合同。

- [ ] **Step 1: 写镜像路径 RED 测试**

```python
def test_docker_context_contains_task_queue_cleanup_cli() -> None:
    cli_path = STARGAZER_ROOT / "scripts" / "clear_task_queue.py"
    dockerfile = _logical_dockerfile()

    assert cli_path.is_file()
    assert "ADD . ." in dockerfile
```

在 CLI 尚未被纳入预期位置或 Dockerfile 复制策略变化时必须失败。

- [ ] **Step 2: 运行镜像合同并确认结果**

```bash
uv run pytest tests/test_dependency_lock_contract.py::test_docker_context_contains_task_queue_cleanup_cli -q
```

Expected: PASS；若因路径/复制合同缺失而 RED，只做最小修复。

- [ ] **Step 3: 更新 README 运维 runbook**

新增章节必须包含：

```bash
# dry-run
docker exec <stargazer-container> \
  python /app/scripts/clear_task_queue.py

# 清默认阻塞目标
docker exec <stargazer-container> \
  python /app/scripts/clear_task_queue.py --apply

# 清全部待执行
docker exec <stargazer-container> \
  python /app/scripts/clear_task_queue.py --all-pending --apply

# Worker 已停止后包含相关 in-progress
docker exec <stargazer-container> \
  python /app/scripts/clear_task_queue.py \
  --all-pending --include-in-progress --worker-stopped --apply
```

同时写明：先暂停下发；in-progress 前停止全部 Worker；备份位于 `/tmp/stargazer-task-queue-backups` 且可能包含敏感 DUMP；复制出容器后按敏感制品管理；禁止 `FLUSHDB`；Kubernetes 用 `kubectl exec` 等价执行。

- [ ] **Step 4: 跑定向行为测试**

```bash
uv run pytest \
  tests/test_task_queue_cleanup.py \
  tests/test_task_queue_cleanup_cli.py \
  tests/test_dependency_lock_contract.py \
  tests/test_collect_multicred.py \
  -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 跑 host running/dedupe 回归**

```bash
uv run pytest \
  tests/test_host_collector.py::TestWorkerRunningFlag \
  tests/test_host_collector.py::TestHostRemoteRuntime \
  -q
```

Expected: 全部 PASS。

- [ ] **Step 6: 跑格式与静态门禁**

```bash
uv run black --check \
  core/task_queue_cleanup.py \
  scripts/clear_task_queue.py \
  tests/test_task_queue_cleanup.py \
  tests/test_task_queue_cleanup_cli.py \
  tests/test_dependency_lock_contract.py

uv run isort --check-only \
  core/task_queue_cleanup.py \
  scripts/clear_task_queue.py \
  tests/test_task_queue_cleanup.py \
  tests/test_task_queue_cleanup_cli.py \
  tests/test_dependency_lock_contract.py

uv run flake8 \
  core/task_queue_cleanup.py \
  scripts/clear_task_queue.py \
  tests/test_task_queue_cleanup.py \
  tests/test_task_queue_cleanup_cli.py \
  tests/test_dependency_lock_contract.py

git diff --check
```

Expected: 全部退出 `0`，无格式、导入顺序或尾随空白问题。

- [ ] **Step 7: 手工 CLI dry-run 烟测**

只对明确的测试 Redis 或空本地 Redis 执行，禁止对未知生产实例运行：

```bash
REDIS_HOST=localhost REDIS_PORT=6379 REDIS_DB=15 \
python scripts/clear_task_queue.py --json
```

Expected: 输出合法 JSON、`dry_run=true`，退出 `0`，不创建备份、不修改 Redis。

- [ ] **Step 8: 提交 Task 4**

```bash
git add agents/stargazer/README.md agents/stargazer/tests/test_dependency_lock_contract.py
git commit -m "docs(stargazer): 补充队列清理运维手册"
```

---

## Final Verification

- [ ] `git status --short` 仅显示预期文件或为空。
- [ ] `git diff --check` 通过。
- [ ] 全部定向测试、running/dedupe 回归、Black、isort、flake8 通过。
- [ ] `python /app/scripts/clear_task_queue.py` 的路径与 README 一致。
- [ ] dry-run 无 Redis 写入；所有 apply 先备份。
- [ ] 项目 memory 记录 RED、GREEN、失败尝试和最终验证证据。
