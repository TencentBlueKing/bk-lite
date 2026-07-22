# Historical Superpowers change: 2026-06-05-stargazer-metrics-publish-failure

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-05-stargazer-metrics-publish-failure.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Stargazer fail non-callback collection tasks whenever metric publish is incomplete after bounded retry, so partial NATS delivery can no longer be reported as a successful collection.

**Architecture:** Keep the fix inside `agents/stargazer` and preserve the external `success`/`failed` task contract. Harden `publish_metrics_to_nats()` so it retries a small number of times and raises on any remaining line gap, then move non-callback multi-credential success handling to after publish success so cache state matches final delivery state.

**Tech Stack:** Python 3.12, Sanic, existing shared NATS utilities, Redis-backed `CredentialStateCache`, `uv`, existing `make lint`.

---

## Implementation constraints

- Repository instructions for this area disallow creating new unit test files, so this plan uses **one-line validation commands** plus the existing `make lint` command instead of adding tests.
- Scope stays inside `agents/stargazer/tasks/utils/nats_helper.py` and `agents/stargazer/tasks/handlers/plugin_handler.py`.
- Do not change callback-mode behavior or any server-side CMDB code in this plan.

## File Structure

- Modify: `agents/stargazer/tasks/utils/nats_helper.py` — add bounded retry, explicit incomplete-publish failure semantics, and structured publish-result logging for metrics delivery.
- Modify: `agents/stargazer/tasks/handlers/plugin_handler.py` — move non-callback multi-credential success handling behind publish success, keep failure handling centralized in the existing `except` block.
- Validate against: `agents/stargazer/core/nats_utils.py` — confirms `nats_publish_lines()` currently returns a success count so the helper can detect partial publish.
- Validate against: `agents/stargazer/core/credential_state_cache.py` — confirms `append_result_event()` and `mark_success()` are both triggered by `_handle_multicred_post_execute()`, so call ordering matters.

## Task 1: Harden metrics publish semantics in `nats_helper.py`

**Files:**
- Modify: `agents/stargazer/tasks/utils/nats_helper.py`
- Validate: `agents/stargazer/tasks/utils/nats_helper.py`

- [ ] **Step 1: Add an inline failing validation that reproduces the current partial-success bug**

```bash
cd agents/stargazer && uv run python -c '
import asyncio
from unittest.mock import AsyncMock, patch
from tasks.utils import nats_helper

async def main():
    with patch.object(nats_helper, "convert_prometheus_to_influx", return_value=["cpu value=1 1", "mem value=2 2"]), \
         patch.object(nats_helper, "nats_publish_lines", AsyncMock(return_value=1)):
        try:
            await nats_helper.publish_metrics_to_nats({}, "ignored", {"plugin_name": "mysql"}, "task-3039")
        except Exception as exc:
            assert "incomplete" in str(exc).lower(), exc
            return
        raise AssertionError("publish_metrics_to_nats() accepted 1/2 published lines")

asyncio.run(main())
'
```

Expected: FAIL with `AssertionError: publish_metrics_to_nats() accepted 1/2 published lines`.

- [ ] **Step 2: Implement bounded retry and explicit incomplete-publish failure**

```python
# agents/stargazer/tasks/utils/nats_helper.py
import asyncio
import json
import os
import traceback
from typing import Dict, Any


class MetricsPublishError(RuntimeError):
    def __init__(
        self,
        task_id: str,
        subject: str,
        total_lines: int,
        success_count: int,
        attempts: int,
        reason: str,
    ):
        self.task_id = task_id
        self.subject = subject
        self.total_lines = total_lines
        self.success_count = success_count
        self.attempts = attempts
        self.reason = reason
        super().__init__(
            f"metrics publish incomplete: task_id={task_id}, subject={subject}, "
            f"success={success_count}/{total_lines}, attempts={attempts}, reason={reason}"
        )


def _metrics_publish_retry_times() -> int:
    raw_value = os.getenv("NATS_METRICS_PUBLISH_RETRIES", "2")
    try:
        return max(int(raw_value), 0)
    except ValueError:
        return 2


async def _publish_lines_with_retry(subject: str, influx_lines: list[str], task_id: str) -> int:
    total_lines = len(influx_lines)
    max_retries = _metrics_publish_retry_times()
    last_error = ""

    for attempt in range(1, max_retries + 2):
        try:
            success_count = await nats_publish_lines(subject, influx_lines)
            failed_count = total_lines - success_count
            logger.info(
                f"[NATS Helper] Publish attempt {attempt} finished for task {task_id}: "
                f"{success_count}/{total_lines} lines delivered to '{subject}'"
            )
            if failed_count == 0:
                return success_count
            last_error = f"publish incomplete ({success_count}/{total_lines})"
        except Exception as err:
            success_count = 0
            last_error = f"{type(err).__name__}: {err}"
            logger.warning(
                f"[NATS Helper] Publish attempt {attempt} failed for task {task_id} on '{subject}': {last_error}"
            )

        if attempt <= max_retries:
            await asyncio.sleep(min(attempt * 0.2, 1.0))
            continue

        raise MetricsPublishError(
            task_id=task_id,
            subject=subject,
            total_lines=total_lines,
            success_count=success_count,
            attempts=attempt,
            reason=last_error,
        )
```

```python
# agents/stargazer/tasks/utils/nats_helper.py (inside publish_metrics_to_nats)
success_count = await _publish_lines_with_retry(subject, influx_lines, task_id)
logger.info(
    f"[NATS Helper] Successfully published {success_count}/{total_lines} metrics to '{subject}' for task {task_id}"
)
```

- [ ] **Step 3: Re-run the inline validation to verify the helper now raises**

Run the same command from Step 1.

Expected: PASS with no output, because `publish_metrics_to_nats()` now raises `MetricsPublishError` when `nats_publish_lines()` returns `1` for `2` lines.

- [ ] **Step 4: Add a second inline validation for the retry-success path**

```bash
cd agents/stargazer && uv run python -c '
import asyncio
from unittest.mock import AsyncMock, patch
from tasks.utils import nats_helper

async def main():
    publish_mock = AsyncMock(side_effect=[1, 2])
    with patch.object(nats_helper, "convert_prometheus_to_influx", return_value=["cpu value=1 1", "mem value=2 2"]), \
         patch.object(nats_helper, "nats_publish_lines", publish_mock):
        await nats_helper.publish_metrics_to_nats({}, "ignored", {"plugin_name": "mysql"}, "task-3039")
        assert publish_mock.await_count == 2, publish_mock.await_count

asyncio.run(main())
'
```

Expected: PASS with no output, proving one failed attempt can be retried and recovered before the task is failed.

- [ ] **Step 5: Commit the helper hardening**

```bash
git add agents/stargazer/tasks/utils/nats_helper.py
git commit -m "fix: fail on incomplete metric publish"
```

## Task 2: Move non-callback success handling behind publish success

**Files:**
- Modify: `agents/stargazer/tasks/handlers/plugin_handler.py`
- Validate: `agents/stargazer/tasks/handlers/plugin_handler.py`

- [ ] **Step 1: Add an inline failing validation for the current success-order bug**

```bash
cd agents/stargazer && uv run python -c '
from pathlib import Path

text = Path("tasks/handlers/plugin_handler.py").read_text()
success_block = text[text.index("metrics_data = await collect_service.collect()"):text.index("return {", text.index("metrics_data = await collect_service.collect()"))]
publish_index = success_block.index("await publish_metrics_to_nats")
post_execute_index = success_block.index("await _handle_multicred_post_execute")
assert publish_index < post_execute_index, "non-callback success state is still written before metrics publish"
'
```

Expected: FAIL with `AssertionError: non-callback success state is still written before metrics publish`.

- [ ] **Step 2: Reorder the success path so publish finishes before multi-credential success is written**

```python
# agents/stargazer/tasks/handlers/plugin_handler.py
metrics_data = await collect_service.collect()
execution_result = _build_credential_execution_result(params, metrics_data)

logger.info(f"[Plugin Task] {task_id} completed successfully")

if params.get("callback_subject"):
    await _handle_multicred_post_execute(
        params, task_id, execution_result, CredentialStateCache, get_task_queue
    )
    await publish_callback_to_nats(metrics_data, params, task_id)
else:
    await publish_metrics_to_nats(ctx, metrics_data, params, task_id)
    await _handle_multicred_post_execute(
        params, task_id, execution_result, CredentialStateCache, get_task_queue
    )
```

Implementation notes for this step:

```python
# keep the existing except block unchanged so:
# 1. publish failure still rebuilds a failed execution_result
# 2. failed state continues through the current centralized _handle_multicred_post_execute()
# 3. callback mode keeps its existing sequencing
```

- [ ] **Step 3: Re-run the inline validation to verify the order is corrected**

Run the same command from Step 1.

Expected: PASS with no output, proving the non-callback success path now publishes metrics before writing success state.

- [ ] **Step 4: Add an inline validation that publish failure routes through the existing failed result**

```bash
cd agents/stargazer && uv run python -c '
from pathlib import Path

text = Path("tasks/handlers/plugin_handler.py").read_text()
assert "execution_result = _build_credential_execution_result(params, None, e)" in text
assert "await _handle_multicred_post_execute(params, task_id, execution_result, CredentialStateCache, get_task_queue)" in text
assert "return {" in text and "\"status\": \"failed\"" in text
'
```

Expected: PASS with no output, confirming the failure branch still rebuilds a failed execution result and returns `failed`.

- [ ] **Step 5: Commit the handler ordering fix**

```bash
git add agents/stargazer/tasks/handlers/plugin_handler.py
git commit -m "fix: delay multicred success until publish succeeds"
```

## Task 3: Run final validation and prepare merge-ready diff

**Files:**
- Modify: `agents/stargazer/tasks/utils/nats_helper.py`
- Modify: `agents/stargazer/tasks/handlers/plugin_handler.py`

- [ ] **Step 1: Run the two inline regression checks back to back**

```bash
cd agents/stargazer && uv run python -c '
import asyncio
from unittest.mock import AsyncMock, patch
from tasks.utils import nats_helper

async def validate_partial_failure():
    with patch.object(nats_helper, "convert_prometheus_to_influx", return_value=["cpu value=1 1", "mem value=2 2"]), \
         patch.object(nats_helper, "nats_publish_lines", AsyncMock(return_value=1)):
        try:
            await nats_helper.publish_metrics_to_nats({}, "ignored", {"plugin_name": "mysql"}, "task-3039")
        except Exception as exc:
            assert "incomplete" in str(exc).lower(), exc
            return
        raise AssertionError("partial publish did not fail")

async def validate_retry_success():
    publish_mock = AsyncMock(side_effect=[1, 2])
    with patch.object(nats_helper, "convert_prometheus_to_influx", return_value=["cpu value=1 1", "mem value=2 2"]), \
         patch.object(nats_helper, "nats_publish_lines", publish_mock):
        await nats_helper.publish_metrics_to_nats({}, "ignored", {"plugin_name": "mysql"}, "task-3039")
        assert publish_mock.await_count == 2, publish_mock.await_count

asyncio.run(validate_partial_failure())
asyncio.run(validate_retry_success())
'
```

Expected: PASS with no output.

- [ ] **Step 2: Run the existing Stargazer lint pipeline**

```bash
cd agents/stargazer && make lint
```

Expected: PASS with pre-commit checks succeeding for the touched files.

- [ ] **Step 3: Inspect the final diff for scope control**

```bash
git --no-pager diff -- agents/stargazer/tasks/utils/nats_helper.py agents/stargazer/tasks/handlers/plugin_handler.py
```

Expected: Only the retry/failure semantics in `nats_helper.py` and the success-order change in `plugin_handler.py`.

- [ ] **Step 4: Create the final commit**

```bash
git add agents/stargazer/tasks/utils/nats_helper.py agents/stargazer/tasks/handlers/plugin_handler.py
git commit -m "fix: fail incomplete stargazer metric publish"
```

## Self-review

### Spec coverage

- Publish incomplete after retry must fail the task — covered by Task 1 and Task 3.
- Limited retry for transient NATS issues — covered by Task 1.
- Non-callback multi-credential success must be delayed until publish succeeds — covered by Task 2.
- Callback mode unchanged, CMDB unchanged — enforced by file scope and Task 2 notes.
- Logging/observability improvement — covered by Task 1 implementation step.

### Placeholder scan

- No `TODO` / `TBD` / “implement later” placeholders remain.
- Every code-changing step includes exact code blocks.
- Every validation step includes an exact command and expected outcome.

### Type consistency

- `MetricsPublishError`, `_metrics_publish_retry_times()`, and `_publish_lines_with_retry()` are all introduced in Task 1 before any later task references them.
- Task 2 keeps using the existing `_build_credential_execution_result()` and `_handle_multicred_post_execute()` names exactly as they exist in the current code.

## specs: 2026-06-05-stargazer-metrics-publish-failure-design.md

日期: 2026-06-05
范围: `agents/stargazer` 指标发布链路，重点覆盖 issue #3039
目标: 将“部分指标发布失败”从日志级告警提升为任务级失败语义，阻断残缺指标继续被 CMDB 当作本次采集真相消费。

## 1. 背景与问题

当前 Stargazer 插件采集链路在非回调模式下存在“采集成功但投递不完整仍返回 success”的闭环缺口：

1. `publish_metrics_to_nats()` 将指标转换为 Influx Line Protocol 后调用 `nats_publish_lines()`。
2. 当发布过程中发生部分失败时，helper 当前不会把“发布不完整”提升为上层失败语义。
3. `collect_plugin_task()` 将 NATS 发布视为最终交付步骤，但由于 helper 不会对部分失败形成明确失败结果，任务可能以 `success` 收尾。
4. CMDB 后续会把已进入 VM 的指标集合当作本次采集真相继续做增删改对比；如果进入总线的是残缺集合，就可能触发漏更、错删、关系残缺等后果。

问题本质不是“某条日志没打出来”，而是系统已经知道“本批次没有完整交付”，却仍然给出了可信成功态。

## 2. 目标与非目标

### 2.1 目标

1. 任意未恢复的指标发布缺口都必须让采集任务进入失败态。
2. 对瞬时 NATS 抖动提供有限重试，减少偶发失败放大。
3. 保证多凭据状态缓存不会在最终发布成功前被提前记成 success。
4. 保持现有 callback 模式和 CMDB 对比逻辑不变，用最小改动堵住残缺数据继续流转。
5. 为日志、排障和后续补偿提供明确的失败上下文。

### 2.2 非目标

1. 本轮不引入跨服务的 `PARTIAL_SUCCESS` 新协议。
2. 本轮不改造 CMDB 的 `metrics_cannula` / `contrast()` 逻辑。
3. 本轮不实现复杂补偿队列、持久化重放或幂等去重框架。
4. 本轮不改变 callback 模式下 `publish_callback_to_nats()` 的成功/失败语义。

## 3. 方案对比与选择

### 方案 A: 立即硬失败，无重试

只要首次发布出现异常或成功条数不足，就直接抛错并结束任务。

优点: 语义最直接，改动最小。
缺点: 对瞬时网络抖动过于敏感，容易把可恢复的抖动直接放大成任务失败。

### 方案 B: 有限重试后硬失败（推荐）

首次发布失败时，在 helper 内做小次数、有限边界的重试；只有全部指标最终成功发布才返回成功，否则抛出明确异常，让上层任务失败。

优点: 保持“完整交付才算 success”的严格语义，同时给瞬时故障一个可恢复窗口。
缺点: 比方案 A 多一点状态统计与日志设计。

### 方案 C: 显式 `PARTIAL_SUCCESS`

helper 返回结构化部分成功结果，由上层落成 `PARTIAL_SUCCESS`，并要求下游 CMDB 不消费该批次。

优点: 语义细。
缺点: 需要同时改造任务状态协议、缓存状态、CMDB 消费门禁和补偿流程，超出本次缺陷修复的最小闭环。

最终选择: 方案 B。

## 4. 架构与职责边界

### 4.1 发布 helper 职责

`publish_metrics_to_nats()` 的职责从“尽力推送并记录日志”收敛为“给出明确的批次交付结果”：

1. 将原始指标转换为 line 列表。
2. 统计 `total_lines`、每次发布返回的成功条数、最终失败条数。
3. 在发布结果不完整时抛出明确异常，而不是只打 warning。
4. 输出与任务排障相关的结构化日志：`task_id`、subject、总条数、成功条数、失败条数、重试次数。

该 helper 不负责吞掉异常，也不负责把失败降级成 warning。

### 4.2 任务 handler 职责

`collect_plugin_task()` 在非 callback 模式下必须把“指标完整发布成功”视为任务成功的组成条件：

1. 采集成功但发布失败或发布不完整，任务最终返回 `failed`。
2. 只有采集成功且发布完整成功，任务才返回 `success`。
3. 发布阶段异常由 handler 捕获并进入统一失败收尾逻辑。

这意味着系统语义从“采集成功即 success”收紧为“采集成功且最终交付成功才 success”。

### 4.3 多凭据状态职责

当前 `collect_plugin_task()` 会在发布前调用 `_handle_multicred_post_execute()`，这会导致多凭据缓存可能先被记成 success，再因发布失败进入 except 分支改写为失败。虽然最终状态可能被覆盖，但中间成功事件和状态变更顺序不准确。

本次设计要求：

1. 非 callback 指标发布路径下，成功态的多凭据后处理必须移动到发布成功之后。
2. 失败态仍由统一 except 分支处理，避免成功/失败事件重复或先后颠倒。
3. callback 模式保持现有时序不变。

## 5. 数据流与失败传播

### 5.1 正常路径

1. `CollectionService.collect()` 返回指标文本。
2. `publish_metrics_to_nats()` 转换并发布全部 line。
3. helper 确认最终 `success_count == total_lines`。
4. handler 再写入多凭据 success 状态并返回 `success`。

### 5.2 异常路径

1. 首次发布出现发送异常，或发布完成后发现 `success_count < total_lines`。
2. helper 在本地有限重试窗口内重试当前批次。
3. 如果重试后仍未达到全量成功，helper 抛出发布异常。
4. handler 进入 except 分支，记录失败日志、写入失败态多凭据结果、返回 `failed`。

### 5.3 下游保护效果

由于非 callback 任务不会再把残缺批次宣告为成功，后续依赖成功态继续流转的 CMDB 消费链路将只看到“完整成功的批次”或“明确失败的任务”，从而避免把 NATS 丢失造成的数据缺口误判为真实资产变化。

## 6. 重试与异常模型

### 6.1 重试策略

重试只覆盖 NATS 发布阶段，不覆盖采集阶段。

建议策略：

1. 先进行一次正常发布。
2. 若发布过程中抛出异常，或返回成功数小于总条数，则认定本次尝试失败。
3. 对失败批次做固定小次数重试。
4. 任一次重试只要达到全量成功即可返回成功。
5. 重试耗尽后仍不完整，则抛出异常。

设计约束：

1. 不做无限重试。
2. 不把“部分成功”当成功。
3. 不在 helper 内静默忽略失败 line。

### 6.2 异常语义

为了便于日志与上层判断，发布失败语义分为两类：

1. `publish transport failed`: 连接、发送、超时等导致本次尝试直接失败。
2. `publish incomplete`: 调用完成但成功条数小于总条数。

两类异常在 handler 层统一视为任务失败；区别仅用于日志、告警和后续排障。

## 7. 日志与可观测性

关键日志点：

1. 发布前：记录任务 ID、subject、总条数。
2. 每次尝试结束：记录尝试次数、成功条数、失败条数。
3. 最终成功：记录全量发布成功。
4. 最终失败：记录失败类别、尝试次数、成功/失败计数。

约束：

1. 不打印完整指标 payload。
2. 只输出必要摘要，避免泄露敏感标签或内容。

## 8. 兼容性与影响面

1. 对外任务接口仍保持现有 `success` / `failed` 二值状态，不新增新状态。
2. callback 模式不变，避免扩大本次改动面。
3. CMDB 无需修改即可受益，因为本次修复把错误拦截在 Stargazer 成功态之前。
4. 多凭据路径的行为会更严格：只有最终交付成功才会记 success。

## 9. 验收标准

1. 全量发布成功时，任务返回 `success`。
2. 首次发布失败但重试后补齐时，任务返回 `success`。
3. 重试后仍有任何 line 未成功发布时，任务返回 `failed`。
4. 不允许出现 `success_count < total_lines` 且任务状态为 `success` 的情况。
5. 非 callback 多凭据路径中，不允许在最终发布成功前先写 success 状态。
6. 失败日志必须能看到任务 ID、subject、总条数、成功/失败条数和重试次数。

## 10. 风险与缓解

1. 短时抖动导致失败数上升
- 缓解: 用有限重试覆盖瞬时故障，再决定最终失败。

2. 重试导致重复发送风险
- 缓解: 本轮接受“重试可能导致重复投递”的既有系统语义，不扩展到幂等治理；本次问题优先级是阻断静默残缺成功。

3. 多凭据状态顺序调整带来副作用
- 缓解: 仅调整非 callback 成功路径的 success 写入时机，失败路径仍复用现有统一收尾逻辑。

## 11. 实施范围

建议只改以下位置：

1. `agents/stargazer/tasks/utils/nats_helper.py`
2. `agents/stargazer/tasks/handlers/plugin_handler.py`

不扩展到 server 侧、CMDB 侧和 callback helper。

## 12. 自检结果

1. Placeholder 检查: 无 TBD/TODO 占位。
2. 一致性检查: 目标、职责边界、验收标准一致。
3. 范围检查: 聚焦 Stargazer 指标发布链路，不扩展到跨服务协议改造。
4. 歧义检查: 已明确“有限重试 + 任务级硬失败 + 非 callback 多凭据 success 延后写入”的边界。
