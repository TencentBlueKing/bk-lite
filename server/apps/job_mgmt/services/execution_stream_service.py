# server/apps/job_mgmt/services/execution_stream_service.py
"""脚本执行流式输出：把 NATS 行事件翻译成 SSE 文本流。"""

import json

from apps.core.logger import job_logger as logger
from nats_client.clients import iter_jetstream_subject, publish_raw_sync

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


async def _default_message_source(execution_id):  # pragma: no cover
    """默认数据源：JetStream 有序消费者，把主题里的 target_key 注入 payload。"""
    filter_subject = f"job.stream.{execution_id}.>"
    logger.info("[stream] 订阅 JetStream 回放主题: %s", filter_subject)
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
    logger.info("[stream] 开始流式输出: execution_id=%s targets=%s", execution_id, list(target_keys))
    count = 0
    completed = False
    try:
        async for payload in message_source:
            count += 1
            yield aggregator.process(payload)
            if aggregator.is_complete():
                completed = True
                break
    except Exception as e:  # 源异常不应让连接 500，转一条 error 事件后正常收尾
        logger.warning(f"[stream_execution_events] 数据源异常 execution_id={execution_id}: {e}")
        yield format_sse_event({"type": "error", "message": str(e)})
    logger.info(
        "[stream] 结束流式输出: execution_id=%s 转发事件数=%s 全部目标完成=%s", execution_id, count, completed
    )
    yield "data: [DONE]\n\n"
