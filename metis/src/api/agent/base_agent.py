import json as json_util
import uuid
from datetime import datetime
from typing import Dict, Any, Callable, Optional

from loguru import logger
from sanic.response import ResponseStream


class BaseAgent:
    
    @staticmethod
    def _create_sse_message(chat_id: str, model: str, created: int,
                            delta_content: str = None, finish_reason: str = None) -> dict:
        """构建 SSE 消息块"""
        message = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant"} if delta_content is None and finish_reason is None else {},
                "finish_reason": finish_reason
            }]
        }

        if delta_content is not None:
            message["choices"][0]["delta"]["content"] = delta_content

        return message

    @staticmethod
    async def _write_sse(response: ResponseStream, data: dict):
        """写入 SSE 格式数据"""
        content = f"data: {json_util.dumps(data, ensure_ascii=False)}\n\n"
        await response.write(content.encode('utf-8'))

    @staticmethod
    async def stream_response_handler(workflow, body, response: ResponseStream, 
                                    content_processor: Optional[Callable[[str, dict], str]] = None):
        """通用流式响应处理器
        
        Args:
            workflow: Agent workflow 实例
            body: 请求体
            response: ResponseStream 实例
            content_processor: 可选的内容处理函数，接收 (content, context) 返回处理后的内容
                             context 包含: {'chat_id', 'model', 'created', 'chunk'}
        """
        chat_id = str(uuid.uuid4())
        created = int(datetime.now().timestamp())

        try:
            # 发送初始消息
            await BaseAgent._write_sse(
                response,
                BaseAgent._create_sse_message(chat_id, body.model, created)
            )

            # 流式处理
            result = await workflow.stream(body)
            async for chunk in result:
                # 使用新的 filter_messages 方法处理消息
                content = await workflow.filter_messages(chunk)
                
                if not content:
                    continue
                    
                # 如果有自定义内容处理器，则使用它
                if content_processor:
                    context = {
                        'chat_id': chat_id,
                        'model': body.model,
                        'created': created,
                        'chunk': chunk
                    }
                    content = content_processor(content, context)
                    if not content:  # 处理器可能返回空内容
                        continue
                
                # 发送内容
                await BaseAgent._write_sse(
                    response,
                    BaseAgent._create_sse_message(chat_id, body.model, created,
                                                delta_content=content)
                )

            # 发送结束标记
            await BaseAgent._write_sse(
                response,
                BaseAgent._create_sse_message(chat_id, body.model, created,
                                            finish_reason="stop")
            )
            await response.write("data: [DONE]\n\n".encode('utf-8'))

            logger.info(f"流式响应完成，问题: {body.user_message}")

        except Exception as e:
            logger.error(f"流式响应失败，问题: {body.user_message}, 错误: {e}")
            raise
