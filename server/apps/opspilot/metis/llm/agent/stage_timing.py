"""DeepAgent 阶段耗时：区分规划模型慢、构图慢，还是规划拆步不合理。

运维检索：`event=deepagent_stage_timing`

- `stage=planning` 且 `duration_ms ≈ model_call_ms`：规划 LLM 慢
- `stage=planning` 且寒暄却 `step_count>0`：规划拆步不合理
- `stage=compile_graph` 很大：构图 / 工具加载慢
- `stage=lightweight_reply` / `plan_step` / `planned_summary` 很大：当步模型或工具慢
- `stage=agui_run` 远大于以上之和：流式组装 / astream_events 在节点返回后空转
"""

from __future__ import annotations

import time

from apps.core.logger import opspilot_logger as logger

STAGE_TIMING_LOG = (
    "event=deepagent_stage_timing stage=%s duration_ms=%s thread_id=%s "
    "step_count=%s step_index=%s tool_count=%s retry_count=%s replan_count=%s "
    "model_call_ms=%s summary_ran=%s"
)
_THREAD_ID_MAX_LEN = 80


def monotonic_ms() -> float:
    return time.monotonic()


def elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def bound_thread_id(value: object) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if not text:
        return "-"
    return text if len(text) <= _THREAD_ID_MAX_LEN else text[:_THREAD_ID_MAX_LEN]


def log_stage_timing(
    stage: str,
    duration_ms: int,
    *,
    thread_id: object = "-",
    step_count: int = 0,
    step_index: int = 0,
    tool_count: int = 0,
    retry_count: int = 0,
    replan_count: int = 0,
    model_call_ms: int = 0,
    summary_ran: int = 0,
) -> None:
    logger.info(
        STAGE_TIMING_LOG,
        stage,
        int(duration_ms),
        bound_thread_id(thread_id),
        int(step_count),
        int(step_index),
        int(tool_count),
        int(retry_count),
        int(replan_count),
        int(model_call_ms),
        int(summary_ran),
    )
