# server/apps/job_mgmt/services/execution_stream_service.py
"""脚本执行流式输出：把 NATS 行事件翻译成 SSE 文本流。"""

import json

from nats_client.clients import publish_raw_sync

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
