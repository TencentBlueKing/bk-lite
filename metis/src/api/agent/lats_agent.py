import json
import uuid
from datetime import datetime
from typing import Dict, Any

from loguru import logger
from sanic import Blueprint, json as sanic_json
from sanic_ext import validate
from sanic.response import ResponseStream

from neco.sanic.auth.api_auth import auth
from neco.llm.agent.lats_agent import LatsAgentRequest, LatsAgentGraph
from src.services.agent_service import AgentService

lats_agent_router = Blueprint("lats_agent_router", url_prefix="/agent")


@lats_agent_router.post("/invoke_lats_agent")
@auth.login_required
@validate(json=LatsAgentRequest)
async def invoke_lats_agent(request, body: LatsAgentRequest):
    """同步调用 LATS Agent"""
    try:
        graph = LatsAgentGraph()
        AgentService.prepare_request(body)

        logger.info(f"执行 LATS Agent: {body.user_message}")
        result = await graph.execute(body)

        logger.info(f"执行成功，评分: {getattr(result, 'score', 'N/A')}")
        return sanic_json(result.model_dump())

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        return sanic_json({"error": "执行失败，请稍后重试"}, status=500)


@lats_agent_router.post("/invoke_lats_agent_sse")
@auth.login_required
@validate(json=LatsAgentRequest)
async def invoke_lats_agent_sse(request, body: LatsAgentRequest):
    """流式调用 LATS Agent"""
    try:
        workflow = LatsAgentGraph()
        AgentService.prepare_request(body)
        chat_id = str(uuid.uuid4())

        logger.info(f"启动 LATS SSE: {body.user_message}, chat_id: {chat_id}")

        return ResponseStream(
            lambda res: stream_lats_response(
                workflow, body, chat_id, body.model, res),
            content_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*"
            }
        )

    except Exception as e:
        logger.error(f"SSE 启动失败: {e}", exc_info=True)
        return sanic_json({"error": "启动失败，请稍后重试"}, status=500)


async def stream_lats_response(workflow, body: Dict[str, Any], chat_id: str, model: str, res) -> None:
    """LATS Agent 流式响应"""
    created = int(datetime.now().timestamp())
    sent_contents = set()
    iteration_count = 0
    has_shown_tool_complete = False

    try:
        logger.info(f"[LATS SSE] 开始流式处理，chat_id: {chat_id}")

        # 开始消息
        start_content = "🎯 **正在分析您的请求...**\n"
        await _write_sse_data(res, chat_id, created, model, start_content)
        sent_contents.add(start_content)

        stream_iter = await workflow.stream(body)

        async for chunk in stream_iter:
            if not chunk:
                continue

            # 处理最终状态
            if _is_final_state(chunk):
                await _handle_final_state(res, chunk, chat_id, created, model, sent_contents)
                continue

            # 处理字典类型的 chunk（节点转换和评估结果）
            if isinstance(chunk, dict):
                # 1. 检测评估结果（在 expand 之后）
                if 'evaluation_results' in chunk:
                    eval_results = chunk['evaluation_results']
                    if eval_results and iteration_count > 0:
                        best_score = max(e.get('score', 0)
                                         for e in eval_results)
                        solutions = sum(1 for e in eval_results if e.get(
                            'found_solution', False))
                        content = f"📊 评估完成 - 最高分: {best_score}/10"
                        if solutions > 0:
                            content += f" | ✅ 找到 {solutions} 个解决方案"
                        content += "\n"
                        if content not in sent_contents:
                            await _write_sse_data(res, chat_id, created, model, content)
                            sent_contents.add(content)
                    continue

                # 2. 检测节点（单键字典）
                node_keys = list(chunk.keys())
                if len(node_keys) == 1:
                    node_name = node_keys[0]

                    # expand 节点（树搜索扩展）
                    if node_name == 'expand':
                        iteration_count += 1
                        content = f"\n🌳 **搜索迭代 {iteration_count}** - 探索新方案\n"
                        logger.info(
                            f"[LATS SSE] 检测到 expand 节点，当前迭代: {iteration_count}")
                        if content not in sent_contents:
                            await _write_sse_data(res, chat_id, created, model, content)
                            sent_contents.add(content)
                        continue

                    # generate_initial_response 节点
                    elif node_name == 'generate_initial_response':
                        content = "🤔 **生成初始方案...**\n"
                        if content not in sent_contents:
                            await _write_sse_data(res, chat_id, created, model, content)
                            sent_contents.add(content)
                        continue

                    # reflect 节点（评估）
                    elif node_name == 'reflect':
                        content = "🔍 **评估方案质量...**\n"
                        if content not in sent_contents:
                            await _write_sse_data(res, chat_id, created, model, content)
                            sent_contents.add(content)
                        continue

                    # tools 节点
                    elif node_name == 'tools':
                        tool_name = _get_tool_name(chunk[node_name])
                        content = f"🔧 正在使用 **{tool_name}**\n"
                        if content not in sent_contents:
                            await _write_sse_data(res, chat_id, created, model, content)
                            sent_contents.add(content)
                        continue

            # 处理消息流
            if isinstance(chunk, (tuple, list)) and len(chunk) > 0:
                message = chunk[0]
                if not message:
                    continue

                message_type = type(message).__name__

                # AIMessageChunk - 流式内容直接输出
                if message_type == "AIMessageChunk":
                    if hasattr(message, 'content') and message.content:
                        await _write_sse_data(res, chat_id, created, model, message.content)
                    continue

                # AIMessage - 过滤评分等内容
                elif message_type == "AIMessage":
                    content = _extract_ai_content(message)
                    if content and content not in sent_contents:
                        await _write_sse_data(res, chat_id, created, model, content)
                        sent_contents.add(content)

                # ToolMessage - 显示工具执行完成
                elif message_type == "ToolMessage":
                    if not has_shown_tool_complete:
                        tool_name = _get_tool_name(message)
                        content = f"✅ **{tool_name}** 执行完成\n"
                        if content not in sent_contents:
                            await _write_sse_data(res, chat_id, created, model, content)
                            sent_contents.add(content)
                            has_shown_tool_complete = True

        # 完成消息
        if iteration_count > 0:
            completion_content = f"\n✨ **搜索完成！** 共 {iteration_count} 轮迭代\n"
        else:
            completion_content = "\n✨ **任务完成！**\n"

        await _write_sse_data(res, chat_id, created, model, completion_content)

        # 发送结束标志
        await _write_sse_end(res, chat_id, created, model)

        logger.info(
            f"[LATS SSE] 流式处理完成，chat_id: {chat_id}，迭代: {iteration_count}轮")

    except Exception as e:
        logger.error(f"[LATS SSE] 处理出错: {str(e)}", exc_info=True)
        error_content = f"\n❌ **处理遇到问题**\n"
        await _write_sse_data(res, chat_id, created, model, error_content, finish_reason="stop")


async def _write_sse_data(res, chat_id: str, created: int, model: str, content: str, finish_reason: str = None):
    """写入SSE数据"""
    response = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "delta": {"role": "assistant", "content": content},
            "index": 0,
            "finish_reason": finish_reason
        }]
    }
    json_str = json.dumps(response, ensure_ascii=False, separators=(',', ':'))
    await res.write(f"data: {json_str}\n\n".encode('utf-8'))


async def _write_sse_end(res, chat_id: str, created: int, model: str):
    """写入SSE结束标志"""
    end_response = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
    }
    json_str = json.dumps(
        end_response, ensure_ascii=False, separators=(',', ':'))
    await res.write(f"data: {json_str}\n\n".encode('utf-8'))
    await res.write("data: [DONE]\n\n".encode('utf-8'))


async def _handle_final_state(res, chunk, chat_id: str, created: int, model: str, sent_contents: set):
    """处理最终状态"""
    messages = chunk.get('messages', [])
    if not messages:
        return

    final_msg = messages[-1]
    if hasattr(final_msg, 'content') and final_msg.content:
        msg_type = type(final_msg).__name__
        if msg_type not in ['SystemMessage', 'HumanMessage']:
            content = _format_content(final_msg.content)
            if content and content not in sent_contents:
                await _write_sse_data(res, chat_id, created, model, content)
                sent_contents.add(content)


def _extract_ai_content(message) -> str:
    """提取AI消息内容"""
    try:
        if not hasattr(message, 'content'):
            return ""

        content = message.content.strip()
        if not content:
            return ""

        # 跳过评分和JSON内容
        if any(keyword in content for keyword in ['"reflections"', '"score"', '"found_solution"', "评分：", "/10"]):
            return ""

        # 跳过过短内容
        if len(content) < 15:
            return ""

        return content

    except Exception as e:
        logger.debug(f"[LATS SSE] 提取内容失败: {e}")
        return ""


def _get_tool_name(data) -> str:
    """获取工具名称"""
    try:
        if isinstance(data, dict) and 'name' in data:
            tool_mapping = {
                "naive_rag_search": "知识库搜索",
                "web_search": "网络搜索",
            }
            return tool_mapping.get(data['name'], data['name'])

        if hasattr(data, 'name') and data.name:
            return data.name

        return "工具"
    except Exception:
        return "工具"


def _format_content(content: str) -> str:
    """格式化内容"""
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    return '\n\n'.join(lines)


def _is_final_state(chunk) -> bool:
    """判断是否为最终状态"""
    return isinstance(chunk, dict) and 'messages' in chunk and 'root' in chunk
