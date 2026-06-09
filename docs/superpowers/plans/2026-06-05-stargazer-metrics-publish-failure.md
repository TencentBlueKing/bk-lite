# Stargazer Metrics Publish Failure Implementation Plan

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
