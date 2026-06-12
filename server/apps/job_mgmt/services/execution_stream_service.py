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
