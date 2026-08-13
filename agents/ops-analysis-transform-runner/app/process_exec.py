"""Run transform in a killable child process so timeouts truly stop work."""

from __future__ import annotations

import multiprocessing as mp
from queue import Empty
from typing import Any

from app.executor import TransformRuntimeError, execute_transform
from app.script_guard import ScriptValidationError


def _child_main(
    script: str,
    rows: list[Any],
    params: dict[str, Any],
    result_queue: mp.Queue,
) -> None:
    try:
        rows_out = execute_transform(script, rows, params)
        result_queue.put({"ok": True, "rows": rows_out})
    except ScriptValidationError as exc:
        result_queue.put({"ok": False, "code": exc.code, "message": str(exc), "kind": "script"})
    except TransformRuntimeError as exc:
        result_queue.put({"ok": False, "code": exc.code, "message": str(exc), "kind": "runtime"})
    except Exception as exc:  # noqa: BLE001
        result_queue.put(
            {
                "ok": False,
                "code": "transform_internal_error",
                "message": "转换内部错误",
                "kind": "internal",
                "detail": str(exc)[:200],
            }
        )


def run_transform_in_process(
    script: str,
    rows: list[Any],
    params: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Execute transform in a child process; kill and reap on timeout.

    Returns a result dict. Caller must release concurrency only after this returns
    (process is no longer alive).
    """
    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(
        target=_child_main,
        args=(script, rows, params if isinstance(params, dict) else {}, result_queue),
    )
    proc.start()
    try:
        # Drain while the child is alive. Waiting for process exit first can
        # deadlock when the Queue pipe fills with an otherwise valid result.
        outcome = result_queue.get(timeout=timeout_seconds)
    except Empty:
        was_alive = proc.is_alive()
        if was_alive:
            proc.kill()
        proc.join(5)
        if was_alive:
            return {"ok": False, "code": "transform_timeout", "message": "转换执行超时", "kind": "timeout"}
        return {
            "ok": False,
            "code": "transform_internal_error",
            "message": "转换结果丢失",
            "kind": "internal",
        }

    proc.join(5)
    if proc.is_alive():
        proc.kill()
        proc.join(5)
    if proc.exitcode not in (0, None):
        return {
            "ok": False,
            "code": "transform_internal_error",
            "message": "转换进程异常退出",
            "kind": "internal",
        }
    return outcome
