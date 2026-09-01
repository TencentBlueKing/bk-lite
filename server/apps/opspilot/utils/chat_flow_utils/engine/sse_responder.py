"""
SSE 响应构建 / 流式内容提取 协作器 (SSEResponderMixin)

F026: 从 ChatFlowEngine 拆出与 SSE/AGUI 响应构建（HTTP 头、错误流）以及
从累积的流式内容中提取最终文本/浏览器步骤相关的逻辑。

重要：这些方法不改变任何对外发出的 SSE/AGUI 事件形态——它们只负责构造
StreamingHttpResponse 外壳，以及在流结束后从已累积内容中“读取”最终文本，
不会修改或新增任何流式事件。AGUI_SKIP_TYPES 由宿主类（ChatFlowEngine）提供。
"""
import json
from typing import Any, List, Optional

from django.http import StreamingHttpResponse

from apps.core.logger import opspilot_logger as logger

_SSE_ACCUMULATE_SKIP_TYPES = frozenset(
    {
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
        "RUN_STARTED",
        "RUN_FINISHED",
        "RUN_ERROR",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_END",
    }
)


def should_accumulate_sse_payload(data: Any) -> bool:
    """Return True when parsed SSE JSON should be kept for final-message extraction."""
    if not isinstance(data, dict):
        return False

    data_type = data.get("type", "")
    if data_type in _SSE_ACCUMULATE_SKIP_TYPES:
        return False
    if data_type == "TEXT_MESSAGE_CONTENT":
        return True
    if data_type == "CUSTOM" and data.get("name") == "browser_step_progress":
        return True
    if data.get("object") == "chat.completion.chunk" or "choices" in data:
        return True
    if not data_type and data.get("object") in ("message", "content", "text"):
        return True
    if not data_type:
        for key in ("content", "message", "text", "delta"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return True
    return False


def parse_sse_chunk_for_accumulation(chunk: str) -> Optional[dict]:
    """Parse an SSE chunk only when it contributes to final message / browser steps."""
    if not chunk.startswith("data: "):
        return None
    data_str = chunk[6:].strip()
    if not data_str or data_str == "[DONE]":
        return None
    try:
        data_json = json.loads(data_str)
    except (json.JSONDecodeError, ValueError):
        return None
    return data_json if should_accumulate_sse_payload(data_json) else None


class SSEResponderMixin:
    """SSE/AGUI 响应构建与流式内容提取协作器。

    依赖宿主类提供：execution_id 属性、AGUI_SKIP_TYPES 类属性。
    """

    def _create_sse_stream_response(self, generate_stream) -> StreamingHttpResponse:
        """创建 SSE 响应"""
        from apps.opspilot.utils.stream_common import make_sse_response

        return make_sse_response(
            generate_stream,
            extra_headers={
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Execution-ID": self.execution_id,
                "Access-Control-Expose-Headers": "X-Execution-ID",
                "Transfer-Encoding": "chunked",
            },
        )

    def _create_error_response(self, error_message: str):
        """创建错误的 StreamingHttpResponse"""
        logger.error(f"[SSE-Engine] {error_message}")

        async def error_gen():
            yield f"data: {json.dumps({'result': False, 'error': error_message})}\n\n"
            yield "data: [DONE]\n\n"

        response = StreamingHttpResponse(error_gen(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        return response

    def _extract_final_message(self, accumulated_content: list) -> str:
        """从累积的流式内容中提取最终消息

        只提取真实的文本内容，过滤掉工具调用相关的事件。

        Args:
            accumulated_content: 累积的数据列表

        Returns:
            最终消息字符串
        """
        if not accumulated_content:
            return ""

        final_msg_parts = []

        for data in accumulated_content:
            if not isinstance(data, dict):
                continue

            data_type = data.get("type", "")
            data_object = data.get("object", "")

            # 跳过 AGUI 协议中的非文本内容事件
            if data_type in self.AGUI_SKIP_TYPES:
                continue

            # 跳过 CUSTOM 类型（如 browser_step_progress），由 _extract_browser_steps 处理
            if data_type == "CUSTOM":
                continue

            # 处理 OpenAI 格式的流式响应
            # 格式: {"choices": [{"delta": {"content": "..."}, ...}], "object": "chat.completion.chunk", ...}
            if data_object == "chat.completion.chunk" or "choices" in data:
                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    continue
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content", "")
                    if content:
                        final_msg_parts.append(content)
                continue

            # 处理 AGUI 协议的文本消息内容
            if data_type == "TEXT_MESSAGE_CONTENT":
                delta = data.get("delta", "")
                if delta:
                    final_msg_parts.append(delta)
                continue

            # 处理其他 SSE 协议格式（非 AGUI）
            # 注意：只有在没有 type 字段时才使用 fallback 逻辑
            if not data_type:
                if data_object in ["message", "content", "text"]:
                    content = data.get("content") or data.get("message") or data.get("text", "")
                    if content:
                        final_msg_parts.append(content)
                    continue

                # 尝试直接提取常见字段（仅用于无 type 的数据）
                for key in ["content", "message", "text", "delta"]:
                    value = data.get(key)
                    if value and isinstance(value, str):
                        final_msg_parts.append(value)
                        break

        final_message = "".join(final_msg_parts) if final_msg_parts else ""

        return final_message

    def _extract_browser_steps(self, accumulated_content: list) -> List[str]:
        """从累积的流式内容中提取 browser_use 步骤信息

        解析 CUSTOM 类型的 browser_step_progress 事件，提取 step_number、next_goal 和 evaluation。
        格式化为纯字符串列表，最后一个元素为最终评估结果。

        Args:
            accumulated_content: 累积的数据列表

        Returns:
            browser_steps 字符串列表，格式: ["step1 xxx", "step2 xxx", ..., "最终结果: xxx"]
        """
        if not accumulated_content:
            return []

        browser_steps = []
        last_evaluation = ""
        for data in accumulated_content:
            if not isinstance(data, dict):
                continue
            if data.get("type") != "CUSTOM" or data.get("name") != "browser_step_progress":
                continue
            value = data.get("value", {})
            if not isinstance(value, dict):
                continue
            step_number = value.get("step_number")
            next_goal = value.get("next_goal", "")
            evaluation = value.get("evaluation", "")
            if step_number is not None and next_goal:
                browser_steps.append(f"步骤{step_number} {next_goal}")
            if evaluation:
                last_evaluation = evaluation

        if last_evaluation:
            browser_steps.append(f"最终结果: {last_evaluation}")

        return browser_steps
