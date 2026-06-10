"""
SSE 响应构建 / 流式内容提取 协作器 (SSEResponderMixin)

F026: 从 ChatFlowEngine 拆出与 SSE/AGUI 响应构建（HTTP 头、错误流）以及
从累积的流式内容中提取最终文本/浏览器步骤相关的逻辑。

重要：这些方法不改变任何对外发出的 SSE/AGUI 事件形态——它们只负责构造
StreamingHttpResponse 外壳，以及在流结束后从已累积内容中“读取”最终文本，
不会修改或新增任何流式事件。AGUI_SKIP_TYPES 由宿主类（ChatFlowEngine）提供。
"""
import json
from typing import Any, List

from django.http import StreamingHttpResponse

from apps.core.logger import opspilot_logger as logger


class SSEResponderMixin:
    """SSE/AGUI 响应构建与流式内容提取协作器。

    依赖宿主类提供：execution_id 属性、AGUI_SKIP_TYPES 类属性。
    """

    def _create_sse_stream_response(self, generate_stream) -> StreamingHttpResponse:
        """创建 SSE 响应"""
        response = StreamingHttpResponse(generate_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "Cache-Control"
        response["X-Execution-ID"] = self.execution_id
        response["Access-Control-Expose-Headers"] = "X-Execution-ID"
        response["Transfer-Encoding"] = "chunked"
        return response

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
