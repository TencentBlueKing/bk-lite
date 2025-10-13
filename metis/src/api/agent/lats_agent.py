import json
import uuid
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass
from enum import Enum

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


# ==================== 数据模型 ====================

class SearchPhase(Enum):
    """搜索阶段"""
    INITIALIZING = "initializing"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    SEARCHING = "searching"
    TOOL_CALLING = "tool_calling"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


@dataclass
class SearchStats:
    """搜索统计"""
    iteration: int = 0
    best_score: float = 0.0
    solutions_found: int = 0


# ==================== SSE 格式化器 ====================

class LatsSSEFormatter:
    """LATS Agent SSE 消息格式化"""

    # 工具友好名称映射
    TOOL_NAMES = {
        "naive_rag_search": "知识库搜索",
        "web_search": "网络搜索",
        "search_tool": "搜索工具",
        "analysis_tool": "分析工具"
    }

    def __init__(self, chat_id: str, model: str):
        self.chat_id = chat_id
        self.model = model
        self.created_time = int(datetime.now().timestamp())
        self.start_time = datetime.now()
        self.stats = SearchStats()
        self._sequence = 0

    def _create_sse(self, content: str = None, finish_reason: str = None,
                    metadata: Dict[str, Any] = None) -> str:
        """创建 SSE 消息"""
        self._sequence += 1

        response = {
            "id": self.chat_id,
            "object": "chat.completion.chunk",
            "created": self.created_time,
            "model": self.model,
            "choices": [{
                "delta": {"role": "assistant"},
                "index": 0,
                "finish_reason": finish_reason
            }]
        }

        if content:
            response["choices"][0]["delta"]["content"] = content

        if metadata:
            response["metis_metadata"] = {
                **metadata, "sequence": self._sequence}

        return f"data: {json.dumps(response, ensure_ascii=False, separators=(',', ':'))}\n\n"

    def format_phase(self, phase: str, content: str) -> str:
        """格式化阶段消息"""
        return self._create_sse(content, metadata={"phase": phase})

    def format_content(self, content: str) -> str:
        """格式化内容消息"""
        return self._create_sse(content) if content else ""

    def format_tool_call(self, tool_name: str) -> str:
        """格式化工具调用"""
        display_name = self.TOOL_NAMES.get(tool_name, tool_name)
        return self.format_phase(
            "tool_calling",
            f"\n🔧 **调用 {display_name}**\n\n💡 正在搜索相关信息..."
        )

    def format_evaluation(self, score: float, reflection: str = None) -> str:
        """格式化评估结果"""
        emoji = "🌟" if score >= 9 else "⭐" if score >= 8 else "✨" if score >= 6 else "💡"
        status = "🎯" if score >= 9 else "👍" if score >= 7 else "📈"

        content = f"\n{status} **评分：{score}/10** {emoji}\n"
        if reflection:
            content = f"\n📝 **{reflection[:600]}**\n" + content

        self.stats.best_score = max(self.stats.best_score, score)
        return self.format_phase("evaluating", content)

    def format_iteration(self, iteration: int) -> str:
        """格式化搜索迭代"""
        self.stats.iteration = iteration
        return self.format_phase(
            "searching",
            f"\n\n---\n\n🌳 **搜索迭代 #{iteration}**\n\n🔍 探索新的解决方案路径..."
        )

    def format_candidates(self, evaluations: List[Dict[str, Any]]) -> str:
        """格式化候选评估"""
        if not evaluations:
            return ""

        best_score = max(e.get("score", 0) for e in evaluations)
        solutions = sum(1 for e in evaluations if e.get(
            "found_solution", False))

        self.stats.best_score = max(self.stats.best_score, best_score)
        self.stats.solutions_found = solutions

        content = f"\n📊 **评估 {len(evaluations)} 个候选方案**\n\n"
        content += f"🏆 最高评分：**{best_score}/10**\n"

        if solutions > 0:
            content += f"✅ 找到 **{solutions}** 个解决方案\n"

        # 展示前3个最佳候选
        top = sorted(evaluations, key=lambda x: x.get(
            "score", 0), reverse=True)[:3]
        content += "\n🔝 **优秀候选：**\n"
        for i, c in enumerate(top, 1):
            status = "🎯" if c.get("found_solution") else "💡"
            content += f"   {status} #{i}: {c.get('score', 0)}/10\n"

        return self.format_phase("evaluating", content)

    def format_completion(self) -> str:
        """格式化完成消息"""
        elapsed = int((datetime.now() - self.start_time).total_seconds())

        content = f"\n\n---\n\n🎊 **LATS 搜索完成！**\n\n"
        content += f"📊 **统计：**\n"
        content += f"   • 迭代轮次：{self.stats.iteration}\n"
        content += f"   • 最佳评分：{self.stats.best_score}/10\n"
        content += f"   • 执行时间：{elapsed}秒\n"

        return self._create_sse(content, finish_reason="stop", metadata={
            "phase": "completed",
            "stats": {
                "iterations": self.stats.iteration,
                "best_score": self.stats.best_score,
                "execution_time": f"{elapsed}秒"
            }
        })

    def format_error(self, error: str) -> str:
        """格式化错误消息"""
        return self._create_sse(
            f"\n❌ **搜索遇到问题**\n\n🔧 {error}\n\n💡 请稍后重试",
            finish_reason="error"
        )


# ==================== SSE 处理器 ====================

class LatsSSEHandler:
    """LATS SSE 流式处理"""

    def __init__(self, chat_id: str, model: str):
        self.formatter = LatsSSEFormatter(chat_id, model)
        self.final_answer_started = False

    async def send(self, res, message: str) -> None:
        """发送 SSE 消息"""
        if message:
            await res.write(message.encode('utf-8'))

    async def handle_flow(self, res, workflow, body) -> None:
        """处理搜索流程"""
        try:
            # 初始化
            await self.send(res, self.formatter.format_phase(
                "initializing",
                "🔍 **启动 LATS 智能搜索**\n\n💡 分析问题并生成多个候选解决方案"
            ))

            # 处理流
            iteration = 0
            async for chunk in await workflow.stream(body):
                await self._process_chunk(res, chunk, iteration)

                if self._is_new_iteration(chunk):
                    iteration += 1

            # 完成
            await self._send_completion(res)

        except Exception as e:
            logger.error(f"处理出错: {e}", exc_info=True)
            await self.send(res, self.formatter.format_error(str(e)))

    async def _process_chunk(self, res, chunk, iteration: int) -> None:
        """处理数据块"""
        # 最终状态
        if self._is_final_state(chunk):
            await self._handle_final_state(res, chunk)
            return

        # 评估结果
        if self._is_evaluation(chunk):
            await self._handle_evaluation(res, chunk)
            return

        # 节点转换
        if self._is_node_transition(chunk):
            await self._handle_node(res, chunk, iteration)
            return

        # 消息流
        if self._is_message_stream(chunk):
            await self._handle_message(res, chunk)

    async def _handle_final_state(self, res, chunk) -> None:
        """处理最终状态"""
        root = chunk.get('root')
        messages = chunk.get('messages', [])

        if not (root and messages):
            return

        # 展示反思
        if hasattr(root, 'reflection') and root.reflection:
            reflection = root.reflection
            if hasattr(reflection, 'reflections') and reflection.reflections:
                await self.send(res, self.formatter.format_content(
                    "\n🧠 **深度分析过程**\n\n"
                ))
                await self.send(res, self.formatter.format_evaluation(
                    reflection.score,
                    reflection.reflections
                ))

        # 解决方案状态
        if hasattr(root, 'is_solved') and root.is_solved:
            score = root.reflection.score if hasattr(
                root, 'reflection') else 10
            await self.send(res, self.formatter.format_phase(
                "solution_found",
                f"\n🎉 **找到高质量解决方案！**\n\n🌟 评分：**{score}/10**"
            ))

        # 最终答案
        if not self.final_answer_started:
            await self.send(res, self.formatter.format_phase(
                "finalizing",
                "\n\n---\n\n✨ **整理最终答案**\n\n"
            ))
            self.final_answer_started = True

        # 输出内容
        if messages:
            final_msg = messages[-1]
            if hasattr(final_msg, 'content') and final_msg.content:
                if not self._is_system_or_user_msg(final_msg):
                    content = self._format_ai_content(final_msg.content)
                    await self.send(res, self.formatter.format_content(
                        f"\n📋 **最终解答**\n\n{content}\n\n"
                    ))

    async def _handle_evaluation(self, res, chunk) -> None:
        """处理评估"""
        if 'initial_evaluation' in chunk:
            eval_data = chunk['initial_evaluation']
            score = eval_data.get('score', 0)
            reflection = eval_data.get('reflections', '')

            await self.send(res, self.formatter.format_content(
                "\n🧠 **分析初始方案...**\n\n"
            ))
            await self.send(res, self.formatter.format_evaluation(score, reflection))

        elif 'evaluation_results' in chunk:
            await self.send(res, self.formatter.format_candidates(
                chunk['evaluation_results']
            ))

    async def _handle_node(self, res, chunk, iteration: int) -> None:
        """处理节点转换"""
        node_name = next(iter(chunk.keys()))

        handlers = {
            "generate_initial_response": "🤔 **生成初始回答...**",
            "expand": lambda: self.formatter.format_iteration(iteration + 1),
            "tools": lambda: self._handle_tool_node(chunk[node_name]),
            "reflect": "🔍 **评估方案质量...**",
        }

        handler = handlers.get(node_name)
        if callable(handler):
            msg = handler()
        elif handler:
            msg = self.formatter.format_content(f"\n{handler}\n\n")
        else:
            msg = None

        if msg:
            await self.send(res, msg)

    def _handle_tool_node(self, node_data) -> str:
        """处理工具节点"""
        tool_name = "知识库搜索"
        if isinstance(node_data, dict) and 'name' in node_data:
            tool_name = self.formatter.TOOL_NAMES.get(
                node_data['name'],
                node_data['name']
            )
        return self.formatter.format_tool_call(tool_name)

    async def _handle_message(self, res, chunk) -> None:
        """处理消息流"""
        message = chunk[0] if chunk else None
        if not message or self._is_system_or_user_msg(message):
            return

        if hasattr(message, 'content') and message.content:
            content = message.content

            # 处理 reflection JSON
            if self._contains_reflection_json(content):
                await self._handle_reflection_json(res, content)
            else:
                await self.send(res, self.formatter.format_content(content))

    async def _handle_reflection_json(self, res, content: str) -> None:
        """处理包含 reflection 的 JSON"""
        try:
            parts = content.split('{', 1)
            if len(parts) == 2:
                normal = parts[0].strip()
                json_part = '{' + parts[1]

                if normal:
                    await self.send(res, self.formatter.format_content(normal))

                data = json.loads(json_part)
                score = data.get('score', 0)
                reflection = data.get('reflections', '')

                if reflection:
                    await self.send(res, self.formatter.format_evaluation(
                        score, reflection
                    ))
        except:
            await self.send(res, self.formatter.format_content(content))

    async def _send_completion(self, res) -> None:
        """发送完成消息"""
        await self.send(res, self.formatter.format_completion())

        end = {
            "id": self.formatter.chat_id,
            "object": "chat.completion.chunk",
            "created": self.formatter.created_time,
            "model": self.formatter.model,
            "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
        }

        await res.write(f"data: {json.dumps(end, ensure_ascii=False)}\n\n".encode('utf-8'))
        await res.write("data: [DONE]\n\n".encode('utf-8'))

    # ==================== 工具方法 ====================

    @staticmethod
    def _is_final_state(chunk) -> bool:
        return isinstance(chunk, dict) and 'messages' in chunk and 'root' in chunk

    @staticmethod
    def _is_evaluation(chunk) -> bool:
        return isinstance(chunk, dict) and (
            'evaluation_results' in chunk or 'initial_evaluation' in chunk
        )

    @staticmethod
    def _is_node_transition(chunk) -> bool:
        return isinstance(chunk, dict) and len(chunk) == 1

    @staticmethod
    def _is_message_stream(chunk) -> bool:
        return isinstance(chunk, (tuple, list)) and len(chunk) > 0

    @staticmethod
    def _is_new_iteration(chunk) -> bool:
        return isinstance(chunk, dict) and 'expand' in chunk

    @staticmethod
    def _is_system_or_user_msg(message) -> bool:
        msg_type = type(message).__name__
        return msg_type in ['SystemMessage', 'HumanMessage']

    @staticmethod
    def _contains_reflection_json(content: str) -> bool:
        try:
            return ('"reflections"' in content and
                    '"score"' in content and
                    '"found_solution"' in content and
                    content.strip().startswith('{') and
                    content.strip().endswith('}'))
        except:
            return False

    @staticmethod
    def _format_ai_content(content: str) -> str:
        """格式化 AI 内容"""
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        return '\n\n'.join(lines)


# ==================== 流式响应入口 ====================

async def stream_lats_response(workflow, body: Dict[str, Any], chat_id: str,
                               model: str, res) -> None:
    """LATS Agent 流式响应"""
    handler = LatsSSEHandler(chat_id, model)
    await handler.handle_flow(res, workflow, body)
