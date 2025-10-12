from loguru import logger
from sanic import Blueprint, json
from sanic_ext import validate
from sanic.response import ResponseStream
import uuid

from neco.sanic.auth.api_auth import auth
from src.services.agent_service import AgentService
import json
from datetime import datetime
from typing import Dict, Any, List
from enum import Enum
from dataclasses import dataclass
import json
from typing import Dict, Any, List
from datetime import datetime
from neco.llm.agent.lats_agent import *
from loguru import logger

lats_agent_router = Blueprint("lats_agent_router", url_prefix="/agent")


@lats_agent_router.post("/invoke_lats_agent")
@auth.login_required
@validate(json=LatsAgentRequest)
async def invoke_lats_agent(request, body: LatsAgentRequest):
    """
    调用 LATS Agent 同步接口

    返回完整的搜索结果
    """
    try:
        # 初始化 LATS 图和服务
        graph = LatsAgentGraph()
        AgentService.prepare_request(body)

        logger.info(f"执行 LATS Agent，用户问题: [{body.user_message}]")

        # 执行搜索
        result = await graph.execute(body)

        # 返回结果
        response_content = result.model_dump()
        logger.info(f"LATS Agent 执行成功，评分: {getattr(result, 'score', 'N/A')}")

        return json(response_content)

    except Exception as e:
        logger.error(f"LATS Agent 执行失败: {str(e)}", exc_info=True)
        return json({"error": "执行失败，请稍后重试"}, status=500)


@lats_agent_router.post("/invoke_lats_agent_sse")
@auth.login_required
@validate(json=LatsAgentRequest)
async def invoke_lats_agent_sse(request, body: LatsAgentRequest):
    """
    调用 LATS Agent 流式接口

    提供实时的搜索过程反馈
    """
    try:
        # 初始化组件
        workflow = LatsAgentGraph()
        AgentService.prepare_request(body)
        chat_id = str(uuid.uuid4())

        logger.info(
            f"启动 LATS Agent SSE，用户问题: [{body.user_message}], chat_id: {chat_id}")

        # 返回流式响应
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
        logger.error(f"LATS Agent SSE 启动失败: {str(e)}", exc_info=True)
        return json({"error": "启动失败，请稍后重试"}, status=500)


class SearchPhase(Enum):
    """搜索阶段枚举"""
    INITIALIZING = "initializing"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    SEARCHING = "searching"
    TOOL_CALLING = "tool_calling"
    SOLUTION_FOUND = "solution_found"
    COMPLETED = "completed"


@dataclass
class SearchStats:
    """搜索统计信息"""
    iteration: int = 0
    nodes_explored: int = 0
    best_score: float = 0.0
    solutions_found: int = 0


class LatsSSEFormatter:
    """LATS Agent SSE 格式化器 - 优化版本"""

    def __init__(self, chat_id: str, model: str):
        self.chat_id = chat_id
        self.model = model
        self.created_time = int(datetime.now().timestamp())
        self.start_time = datetime.now()
        self.stats = SearchStats()
        self._message_sequence = 0  # 添加消息序列号，确保顺序

    def _create_sse_response(self, content: str = None, finish_reason: str = None,
                             metadata: Dict[str, Any] = None) -> str:
        """创建 SSE 响应数据"""
        self._message_sequence += 1

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
                **metadata,
                "sequence": self._message_sequence  # 添加序列号
            }

        json_str = json.dumps(
            response, ensure_ascii=False, separators=(',', ':'))
        return f"data: {json_str}\n\n"

    def format_initialization(self) -> str:
        """格式化初始化"""
        content = "🔍 **启动 LATS 智能搜索**\n\n💡 分析问题并生成多个候选解决方案"
        return self._create_sse_response(content, metadata={"phase": "initializing"})

    def format_initial_generation(self) -> str:
        """格式化初始生成"""
        content = "\n\n---\n\n🌱 **生成初始解决方案**\n\n🎯 构建第一个候选回答\n\n"
        return self._create_sse_response(content, metadata={"phase": "generating"})

    def format_tool_execution(self, tool_name: str) -> str:
        """格式化工具执行"""
        tool_display = self._get_tool_display_name(tool_name)
        content = f"\n🔧 **调用 {tool_display}**\n\n💡 正在搜索相关信息..."
        return self._create_sse_response(content, metadata={"phase": "tool_calling", "tool": tool_name})

    def format_thinking_process(self, thought: str) -> str:
        """格式化思考过程"""
        # 清理思考内容，避免过长
        cleaned_thought = thought.strip()
        if len(cleaned_thought) > 800:
            cleaned_thought = cleaned_thought[:800] + "..."

        content = f"\n� **{cleaned_thought}**\n"
        return self._create_sse_response(content, metadata={"phase": "thinking"})

    def format_reflection(self, reflection: str, score: float = None) -> str:
        """格式化反思过程"""
        # 清理反思内容
        cleaned_reflection = reflection.strip()
        if len(cleaned_reflection) > 600:
            cleaned_reflection = cleaned_reflection[:600] + "..."

        content = f"\n📝 **质量评估**\n\n{cleaned_reflection}\n"
        if score is not None:
            emoji = "🌟" if score >= 9 else "⭐" if score >= 8 else "✨" if score >= 6 else "💡"
            status_emoji = "🎯" if score >= 9 else "👍" if score >= 7 else "📈"
            content += f"\n{status_emoji} **评分：{score}/10** {emoji}\n"
        return self._create_sse_response(content, metadata={"phase": "reflecting", "score": score})

    def format_initial_evaluation(self, score: float) -> str:
        """格式化初始评估"""
        self.stats.best_score = score
        emoji = "🌟" if score >= 8 else "⭐" if score >= 6 else "💡"

        content = f"\n📊 **初始评估完成** {emoji}\n\n"
        content += f"📈 评分：**{score}/10**\n"

        # 根据评分决定下一步行动
        if score >= 9:
            content += f"🎉 **高质量方案！无需进一步搜索**"
        elif score >= 7:
            content += f"✨ **良好方案，考虑优化空间**"
        else:
            content += f"🚀 **开始树搜索优化...**"

        return self._create_sse_response(content, metadata={"phase": "evaluating", "score": score})

    def format_search_iteration(self, iteration: int) -> str:
        """格式化搜索迭代"""
        self.stats.iteration = iteration

        content = f"\n\n---\n\n🌳 **搜索迭代 #{iteration}**\n\n"
        content += f"🔍 探索新的解决方案路径..."

        return self._create_sse_response(content, metadata={
            "phase": "searching",
            "iteration": iteration
        })

    def format_candidates_evaluation(self, evaluations: List[Dict[str, Any]]) -> str:
        """格式化候选方案评估（简化版）"""
        if not evaluations:
            return ""

        best_score = max(e.get("score", 0) for e in evaluations)
        solutions_count = sum(
            1 for e in evaluations if e.get("found_solution", False))

        self.stats.best_score = max(self.stats.best_score, best_score)
        self.stats.solutions_found = solutions_count

        content = f"\n📊 **评估 {len(evaluations)} 个候选方案**\n\n"
        content += f"🏆 最高评分：**{best_score}/10**\n"

        if solutions_count > 0:
            content += f"✅ 找到 **{solutions_count}** 个解决方案\n"

        # 只显示前3个最佳候选
        top_candidates = sorted(
            evaluations, key=lambda x: x.get("score", 0), reverse=True)[:3]
        content += f"\n🔝 **优秀候选：**\n"
        for i, candidate in enumerate(top_candidates, 1):
            score = candidate.get("score", 0)
            status = "🎯" if candidate.get("found_solution", False) else "💡"
            content += f"   {status} #{i}: {score}/10\n"

        return self._create_sse_response(content, metadata={
            "phase": "evaluating",
            "best_score": best_score,
            "solutions_found": solutions_count
        })

    def format_solution_found(self, score: float) -> str:
        """格式化找到解决方案"""
        content = f"\n🎉 **找到高质量解决方案！**\n\n"
        content += f"🌟 最终评分：**{score}/10**\n"
        content += f"🔄 搜索迭代：{self.stats.iteration} 轮\n\n"
        content += f"🎯 **生成最终答案...**"

        return self._create_sse_response(content, metadata={
            "phase": "solution_found",
            "final_score": score
        })

    def format_final_answer_start(self) -> str:
        """格式化开始生成最终答案"""
        content = "\n\n---\n\n✨ **整理最终答案**\n\n📝 基于搜索结果生成完整回答"
        return self._create_sse_response(content, metadata={"phase": "finalizing"})

    def format_content(self, content: str) -> str:
        """格式化内容输出"""
        # 保护原始内容，只做基本清理
        if not content:
            return ""

        # 移除可能的控制字符，但保持内容完整
        cleaned_content = content.replace('\x00', '').strip()

        # 不截断内容，保持完整性
        return self._create_sse_response(cleaned_content)

    def format_completion(self) -> str:
        """格式化完成"""
        execution_time = datetime.now() - self.start_time
        time_str = f"{int(execution_time.total_seconds())}秒"

        content = f"\n\n---\n\n🎊 **LATS 搜索完成！**\n\n"
        content += f"📊 **搜索统计：**\n"
        content += f"   • 迭代轮次：{self.stats.iteration}\n"
        content += f"   • 最佳评分：{self.stats.best_score}/10\n"
        content += f"   • 执行时间：{time_str}\n"

        return self._create_sse_response(content, finish_reason="stop", metadata={
            "phase": "completed",
            "stats": {
                "iterations": self.stats.iteration,
                "best_score": self.stats.best_score,
                "execution_time": time_str
            }
        })

    def format_error(self, error_msg: str) -> str:
        """格式化错误"""
        content = f"\n❌ **搜索遇到问题**\n\n🔧 {error_msg}\n\n💡 请稍后重试"
        return self._create_sse_response(content, finish_reason="error")

    def _get_tool_display_name(self, tool_name: str) -> str:
        """获取工具友好显示名称"""
        tool_names = {
            "naive_rag_search": "知识库搜索",
            "web_search": "网络搜索",
            "search_tool": "搜索工具",
            "analysis_tool": "分析工具"
        }
        return tool_names.get(tool_name, tool_name)

    # 保持向后兼容的方法
    def format_initial_generation_start(self) -> str:
        return self.format_initial_generation()

    def format_final_content(self, content: str) -> str:
        return self.format_content(content)

    def format_tool_call_start(self, tool_name: str, description: str = None) -> str:
        return self.format_tool_execution(tool_name)

    def format_candidates_evaluation_results(self, evaluations: List[Dict[str, Any]]) -> str:
        return self.format_candidates_evaluation(evaluations)

    def format_search_iteration(self, iteration: int) -> str:
        """格式化搜索迭代"""
        self.stats.iteration = iteration

        content = f"\n\n---\n\n🌳 **搜索迭代 #{iteration}**\n\n"
        content += f"🔍 探索新的解决方案路径..."

        return self._create_sse_response(content, metadata={
            "phase": "searching",
            "iteration": iteration
        })

    def format_candidates_evaluation(self, evaluations: List[Dict[str, Any]]) -> str:
        """格式化候选方案评估（简化版）"""
        if not evaluations:
            return ""

        best_score = max(e.get("score", 0) for e in evaluations)
        solutions_count = sum(
            1 for e in evaluations if e.get("found_solution", False))

        self.stats.best_score = max(self.stats.best_score, best_score)
        self.stats.solutions_found = solutions_count

        content = f"\n📊 **评估 {len(evaluations)} 个候选方案**\n\n"
        content += f"🏆 最高评分：**{best_score}/10**\n"

        if solutions_count > 0:
            content += f"✅ 找到 **{solutions_count}** 个解决方案\n"

        # 只显示前3个最佳候选
        top_candidates = sorted(
            evaluations, key=lambda x: x.get("score", 0), reverse=True)[:3]
        content += f"\n🔝 **优秀候选：**\n"
        for i, candidate in enumerate(top_candidates, 1):
            score = candidate.get("score", 0)
            status = "🎯" if candidate.get("found_solution", False) else "💡"
            content += f"   {status} #{i}: {score}/10\n"

        return self._create_sse_response(content, metadata={
            "phase": "evaluating",
            "best_score": best_score,
            "solutions_found": solutions_count
        })

    def format_solution_found(self, score: float) -> str:
        """格式化找到解决方案"""
        content = f"\n\n🎉 **找到高质量解决方案！**\n\n"
        content += f"🌟 最终评分：**{score}/10**\n"
        content += f"🔄 搜索迭代：{self.stats.iteration} 轮\n\n"
        content += f"🎯 **生成最终答案...**"

        return self._create_sse_response(content, metadata={
            "phase": "solution_found",
            "final_score": score
        })

    def format_final_answer_start(self) -> str:
        """格式化开始生成最终答案"""
        content = "\n\n---\n\n✨ **整理最终答案**\n\n📝 基于搜索结果生成完整回答"
        return self._create_sse_response(content, metadata={"phase": "finalizing"})

    def format_content(self, content: str) -> str:
        """格式化内容输出"""
        return self._create_sse_response(content)

    def format_completion(self) -> str:
        """格式化完成"""
        execution_time = datetime.now() - self.start_time
        time_str = f"{int(execution_time.total_seconds())}秒"

        content = f"\n\n---\n\n🎊 **LATS 搜索完成！**\n\n"
        content += f"📊 **搜索统计：**\n"
        content += f"   • 迭代轮次：{self.stats.iteration}\n"
        content += f"   • 最佳评分：{self.stats.best_score}/10\n"
        content += f"   • 执行时间：{time_str}\n"

        return self._create_sse_response(content, finish_reason="stop", metadata={
            "phase": "completed",
            "stats": {
                "iterations": self.stats.iteration,
                "best_score": self.stats.best_score,
                "execution_time": time_str
            }
        })

    def format_error(self, error_msg: str) -> str:
        """格式化错误"""
        content = f"\n\n❌ **搜索遇到问题**\n\n🔧 {error_msg}\n\n💡 请稍后重试"
        return self._create_sse_response(content, finish_reason="error")

    def _get_tool_display_name(self, tool_name: str) -> str:
        """获取工具友好显示名称"""
        tool_names = {
            "naive_rag_search": "知识库搜索",
            "web_search": "网络搜索",
            "search_tool": "搜索工具",
            "analysis_tool": "分析工具"
        }
        return tool_names.get(tool_name, tool_name)

    # 保持向后兼容的方法
    def format_initial_generation_start(self) -> str:
        return self.format_initial_generation()

    def format_final_content(self, content: str) -> str:
        return self.format_content(content)

    def format_tool_call_start(self, tool_name: str, description: str = None) -> str:
        return self.format_tool_execution(tool_name)

    def format_candidates_evaluation_results(self, evaluations: List[Dict[str, Any]]) -> str:
        return self.format_candidates_evaluation(evaluations)


class LatsSSEHandler:
    """LATS SSE 处理器 - 优化版本"""

    def __init__(self, chat_id: str, model: str):
        self.chat_id = chat_id
        self.model = model
        self.formatter = LatsSSEFormatter(chat_id, model)
        self.is_final_answer_started = False
        # 移除输出锁和消息去重机制，简化处理逻辑

    async def send_sse(self, res, message: str) -> None:
        """发送 SSE 消息（简化版本）"""
        if not message:
            return

        try:
            await res.write(message.encode('utf-8'))
            # 提取消息内容的前50个字符用于日志
            content_preview = message[:50].replace('\n', ' ').strip()
            logger.info(f"[LATS SSE] 发送消息: {content_preview}...")
        except Exception as e:
            logger.error(f"[LATS SSE] 发送消息失败: {e}")

    async def handle_search_flow(self, res, workflow, body) -> None:
        """处理搜索流程"""
        try:
            logger.info(f"[LATS SSE] 开始处理搜索流程，chat_id: {self.chat_id}")

            # 发送初始化消息
            await self.send_sse(res, self.formatter.format_initialization())
            await self.send_sse(res, self.formatter.format_initial_generation())

            # 处理搜索流
            iteration_count = 0
            async for chunk in await workflow.stream(body):
                await self.process_chunk(res, chunk, iteration_count)

                # 检查是否是新的迭代
                if self._is_new_iteration(chunk):
                    iteration_count += 1

            # 发送完成消息
            await self.send_completion(res)

            logger.info(f"[LATS SSE] 搜索流程处理完成，chat_id: {self.chat_id}")

        except Exception as e:
            logger.error(f"[LATS SSE] 处理出错: {str(e)}", exc_info=True)
            await self.send_sse(res, self.formatter.format_error(str(e)))

    async def process_chunk(self, res, chunk, iteration_count: int) -> None:
        """处理数据块"""
        try:
            chunk_type = type(chunk).__name__
            logger.debug(f"[LATS SSE] 处理chunk: {chunk_type}")

            # 如果是字典类型，记录其键
            if isinstance(chunk, dict):
                keys = list(chunk.keys())
                logger.debug(f"[LATS SSE] 字典chunk键: {keys}")

            # 处理最终状态
            if self._is_final_state(chunk):
                logger.info(f"[LATS SSE] 检测到最终状态")
                await self.handle_final_state(res, chunk)
                return

            # 处理评估结果
            if self._is_evaluation_results(chunk):
                logger.info(f"[LATS SSE] 检测到评估结果")
                if 'evaluation_results' in chunk:
                    await self.handle_evaluation_results(res, chunk['evaluation_results'])
                elif 'initial_evaluation' in chunk:
                    await self.handle_initial_evaluation(res, chunk['initial_evaluation'])
                return

            # 处理节点转换
            if self._is_node_transition(chunk):
                await self.handle_node_transition(res, chunk, iteration_count)

                # 特殊处理：如果是generate_initial_response节点完成，检查是否有evaluation数据
                node_name = next(iter(chunk.keys()))
                if node_name == "generate_initial_response" and isinstance(chunk[node_name], dict):
                    node_data = chunk[node_name]
                    # 检查是否包含initial_evaluation
                    if 'initial_evaluation' in node_data:
                        await self.handle_initial_evaluation(res, node_data['initial_evaluation'])
                return

            # 处理消息流
            if self._is_message_stream(chunk):
                await self.handle_message_stream(res, chunk)
                return

            # 处理其他可能的数据类型
            if isinstance(chunk, dict):
                await self.handle_dict_chunk(res, chunk)
            else:
                logger.warning(f"[LATS SSE] 未处理的chunk类型: {chunk_type}")

        except Exception as e:
            logger.error(f"[LATS SSE] 处理chunk出错: {e}", exc_info=True)

    async def handle_dict_chunk(self, res, chunk: dict) -> None:
        """处理字典类型的数据块"""
        # 检查是否包含思考或反思内容
        if 'thought' in chunk or 'thinking' in chunk:
            thought_content = chunk.get('thought') or chunk.get('thinking', '')
            if thought_content:
                await self.send_sse(res, self.formatter.format_thinking_process(str(thought_content)))

        elif 'reflection' in chunk:
            reflection_content = chunk.get('reflection', '')
            score = chunk.get('score')
            if reflection_content:
                await self.send_sse(res, self.formatter.format_reflection(str(reflection_content), score))

        # 检查是否是Reflection对象的字典表示
        elif 'reflections' in chunk and 'score' in chunk:
            reflection_content = chunk.get('reflections', '')
            score = chunk.get('score')
            found_solution = chunk.get('found_solution', False)

            if reflection_content:
                await self.send_sse(res, self.formatter.format_thinking_process(
                    f"**方案分析**\n\n{reflection_content}"
                ))

                status = "✅ 找到解决方案！" if found_solution else "📝 继续优化中"
                await self.send_sse(res, self.formatter.format_reflection(
                    f"{reflection_content}\n\n{status}", score
                ))

    def _is_final_state(self, chunk) -> bool:
        """检查是否为最终状态"""
        return isinstance(chunk, dict) and 'messages' in chunk and 'root' in chunk

    def _is_evaluation_results(self, chunk) -> bool:
        """检查是否为评估结果"""
        return isinstance(chunk, dict) and ('evaluation_results' in chunk or 'initial_evaluation' in chunk)

    def _is_node_transition(self, chunk) -> bool:
        """检查是否为节点转换"""
        return isinstance(chunk, dict) and len(chunk) == 1

    def _is_message_stream(self, chunk) -> bool:
        """检查是否为消息流"""
        return isinstance(chunk, (tuple, list)) and len(chunk) > 0

    def _is_new_iteration(self, chunk) -> bool:
        """检查是否为新迭代"""
        return (isinstance(chunk, dict) and 'expand' in chunk) or \
               (self._is_node_transition(chunk) and 'expand' in chunk)

    async def handle_final_state(self, res, chunk) -> None:
        """处理最终状态"""
        root_node = chunk.get('root')
        messages = chunk.get('messages', [])

        logger.info(
            f"[LATS SSE] 处理最终状态 - root_node存在: {root_node is not None}, messages数量: {len(messages)}")

        if not (root_node and messages):
            logger.warning(f"[LATS SSE] 最终状态缺少必要数据")
            return

        # 强制展示初始评估的思考过程（确保一定会显示）
        if hasattr(root_node, 'reflection') and root_node.reflection:
            reflection = root_node.reflection
            logger.info(
                f"[LATS SSE] 找到reflection，评分: {getattr(reflection, 'score', 'N/A')}")

            # 先展示思考过程分析提示
            await self.send_sse(res, self.formatter.format_content(
                "\n🧠 **Agent 深度分析过程**\n\n"
            ))

            # 展示详细的思考过程
            if hasattr(reflection, 'reflections') and reflection.reflections:
                await self.send_sse(res, self.formatter.format_thinking_process(
                    f"**问题分析与方案评估**\n\n{reflection.reflections}"
                ))
                await self.send_sse(res, self.formatter.format_reflection(
                    reflection.reflections, reflection.score
                ))

            # 展示评估结果
            await self.send_sse(res, self.formatter.format_initial_evaluation(reflection.score))

        # 检查是否找到解决方案
        if hasattr(root_node, 'is_solved') and root_node.is_solved:
            # 获取最佳评分
            best_score = 10  # 默认高分
            if hasattr(root_node, 'reflection') and root_node.reflection:
                best_score = root_node.reflection.score

            logger.info(f"[LATS SSE] 找到解决方案，评分: {best_score}")
            await self.send_sse(res, self.formatter.format_solution_found(best_score))

        # 开始最终答案
        if not self.is_final_answer_started:
            logger.info(f"[LATS SSE] 开始输出最终答案")
            await self.send_sse(res, self.formatter.format_final_answer_start())
            self.is_final_answer_started = True

        # 输出最终内容
        if messages:
            final_message = messages[-1]
            logger.info(f"[LATS SSE] 最终消息类型: {type(final_message).__name__}")

            if hasattr(final_message, 'content') and final_message.content:
                # 记录日志，帮助调试
                logger.info(
                    f"[LATS SSE] 准备输出最终答案，内容长度: {len(final_message.content)}")

                # 格式化最终答案，确保清晰展示
                content = final_message.content

                # 过滤掉系统消息和用户消息
                if self._is_system_or_user_message(final_message):
                    logger.warning(f"[LATS SSE] 最终消息为系统/用户消息，已过滤")
                    return

                if content.strip():  # 确保内容不为空
                    # 使用优化的格式化方法
                    formatted_content = self._format_ai_content(content)
                    final_output = f"\n\n✨ **最终解答**\n\n{formatted_content}\n\n"
                    await self.send_sse(res, self.formatter.format_content(final_output))
                else:
                    logger.warning(f"[LATS SSE] 最终消息内容为空")
            else:
                logger.warning(f"[LATS SSE] 最终消息没有content属性或content为空")
        else:
            logger.warning(f"[LATS SSE] 没有找到最终消息")

    async def handle_initial_evaluation(self, res, evaluation: Dict[str, Any]) -> None:
        """处理初始评估结果"""
        reflection_content = evaluation.get('reflections', '')
        score = evaluation.get('score', 0)

        logger.info(f"[LATS SSE] 展示初始评估思考过程，评分: {score}/10")

        # 先展示评估进行中的提示
        await self.send_sse(res, self.formatter.format_content(
            "\n🧠 **正在深度分析初始方案...**\n\n"
        ))

        if reflection_content:
            await self.send_sse(res, self.formatter.format_thinking_process(
                f"**初始方案深度分析**\n\n{reflection_content}"
            ))
            await self.send_sse(res, self.formatter.format_reflection(
                reflection_content, score
            ))

        # 展示初始评估结果
        await self.send_sse(res, self.formatter.format_initial_evaluation(score))

    async def handle_evaluation_results(self, res, evaluations: List[Dict[str, Any]]) -> None:
        """处理评估结果"""
        if evaluations:
            logger.info(f"[LATS SSE] 展示 {len(evaluations)} 个候选方案评估结果")

            # 首先展示评估过程提示
            await self.send_sse(res, self.formatter.format_content(
                f"\n⚖️ **开始评估 {len(evaluations)} 个候选方案...**\n\n"
            ))

            # 展示每个候选方案的详细思考过程（只展示前3个最好的）
            sorted_evaluations = sorted(
                evaluations, key=lambda x: x.get('score', 0), reverse=True)
            top_evaluations = sorted_evaluations[:3]  # 只展示前3个

            for i, evaluation in enumerate(top_evaluations):
                reflection_content = evaluation.get('reflections', '')
                score = evaluation.get('score', 0)

                if reflection_content:
                    await self.send_sse(res, self.formatter.format_thinking_process(
                        f"**候选方案 #{evaluation.get('index', i+1)} 分析**\n\n{reflection_content}"
                    ))

                    # 简化的评分展示
                    emoji = "🌟" if score >= 8 else "⭐" if score >= 6 else "💡"
                    await self.send_sse(res, self.formatter.format_content(
                        f"\n📊 评分：**{score}/10** {emoji}\n\n"
                    ))

            # 最后展示评估总结
            await self.send_sse(res, self.formatter.format_candidates_evaluation(evaluations))

    async def handle_node_transition(self, res, chunk, iteration_count: int) -> None:
        """处理节点转换"""
        node_name = next(iter(chunk.keys()))
        node_data = chunk[node_name]

        if node_name == "generate_initial_response":
            # 输出初始响应生成的思考过程
            await self.send_sse(res, self.formatter.format_content("\n🤔 **分析问题，生成初始回答...**\n\n"))
        elif node_name == "expand":
            await self.send_sse(res, self.formatter.format_search_iteration(iteration_count + 1))
        elif node_name == "tools":
            # 优化工具执行提示，显示具体工具名称
            tool_name = "知识库搜索"  # 默认工具名称
            if isinstance(node_data, dict) and 'name' in node_data:
                tool_name = self.formatter._get_tool_display_name(
                    node_data['name'])
            await self.send_sse(res, self.formatter.format_tool_execution(tool_name))
        elif node_name == "reflect":
            await self.send_sse(res, self.formatter.format_content("\n🔍 **评估当前解决方案质量...**\n\n"))
        elif node_name == "should_continue":
            await self.send_sse(res, self.formatter.format_content("\n⚖️ **判断是否需要继续搜索...**\n\n"))
        else:
            # 输出其他节点的处理信息，增强思考感
            node_descriptions = {
                "generate_candidates": "🌱 **生成多个候选解决方案...**",
                "evaluate_candidates": "📊 **评估候选方案质量...**",
                "select_best": "🎯 **选择最佳候选方案...**",
                "backtrack": "🔄 **回溯寻找更好路径...**",
                "generate_final_answer": "✨ **正在生成最终解答...**",
            }
            description = node_descriptions.get(
                node_name, f"🔄 **执行 {node_name} 节点...**")
            await self.send_sse(res, self.formatter.format_content(f"\n{description}\n\n"))

    async def handle_message_stream(self, res, chunk) -> None:
        """处理消息流"""
        message = chunk[0] if chunk else None
        if not message:
            return

        message_type = type(message).__name__
        logger.debug(f"[LATS SSE] 处理消息类型: {message_type}")

        # 首先检查是否为系统消息或用户消息，如果是则直接过滤掉
        if self._is_system_or_user_message(message):
            logger.debug(f"[LATS SSE] 跳过系统/用户消息: {message_type}")
            return

        # 处理 AI 消息块 - 检查是否包含JSON格式的reflection
        if message_type == "AIMessageChunk" and hasattr(message, 'content') and message.content:
            content = message.content
            logger.debug(
                f"[LATS SSE] 处理AIMessageChunk，内容长度: {len(content)}, 预览: {content[:100]}")

            # 检查是否包含reflection JSON
            if self._contains_reflection_json(content):
                await self._handle_reflection_content(res, content)
            else:
                # 直接输出原始内容，保持完整性
                logger.debug(f"[LATS SSE] 输出AI消息块内容: {content[:50]}...")
                await self.send_sse(res, self.formatter.format_content(content))

        # 处理完整的AI消息 - 也检查reflection
        elif message_type == "AIMessage" and hasattr(message, 'content') and message.content:
            content = message.content
            logger.info(f"[LATS SSE] 处理完整AI消息，内容长度: {len(content)}")
            logger.debug(f"[LATS SSE] AI消息内容预览: {content[:200]}...")

            if self._contains_reflection_json(content):
                await self._handle_reflection_content(res, content)
            else:
                # 对于完整消息，确保内容完整输出，并优化格式
                logger.info(f"[LATS SSE] 输出完整AI消息内容")
                formatted_content = self._format_ai_content(content)
                # 处理工具消息 - 只显示工具执行状态，不显示敏感的工具结果内容
                await self.send_sse(res, self.formatter.format_content(formatted_content))
        elif "Tool" in message_type and "Message" in message_type:
            logger.debug(f"[LATS SSE] 处理工具消息: {message_type}")

            if hasattr(message, 'name'):
                tool_name = getattr(message, 'name', 'unknown_tool')
                logger.info(f"[LATS SSE] 工具执行: {tool_name}")
                await self.send_sse(res, self.formatter.format_tool_execution(tool_name))
            elif hasattr(message, 'content') and message.content:
                # 工具结果已获取，但不显示具体内容（避免泄露敏感信息）
                content_length = len(message.content) if message.content else 0
                logger.info(f"[LATS SSE] 工具返回结果，长度: {content_length}")
                await self.send_sse(res, self.formatter.format_content("\n✅ **工具执行完成，正在分析结果...**\n"))

        # 处理其他未知消息类型
        else:
            logger.warning(
                f"[LATS SSE] 未处理的消息类型: {message_type}, 是否有content: {hasattr(message, 'content')}")
            if hasattr(message, 'content') and message.content:
                logger.debug(
                    f"[LATS SSE] 未知消息内容预览: {str(message.content)[:100]}...")
                # 对于未知类型，也尝试输出内容
                await self.send_sse(res, self.formatter.format_content(str(message.content)))

    def _contains_reflection_json(self, content: str) -> bool:
        """检查内容是否包含reflection JSON"""
        try:
            # 检查是否包含reflection的关键字段
            return ('"reflections"' in content and
                    '"score"' in content and
                    '"found_solution"' in content and
                    content.strip().startswith('{') and
                    content.strip().endswith('}'))
        except:
            return False

    def _is_system_or_user_message(self, message) -> bool:
        """检查是否为系统消息或用户消息对象（基于消息类型）"""
        if not message:
            return False

        message_type = type(message).__name__

        # 检查消息类型，过滤掉系统消息和用户消息
        if message_type in ['SystemMessage', 'HumanMessage']:
            logger.debug(f"[LATS SSE] 检测到系统/用户消息类型: {message_type}")
            return True

        # 检查是否是字符串形式的消息类型名称
        if hasattr(message, '__class__') and message.__class__.__name__ in ['SystemMessage', 'HumanMessage']:
            logger.debug(
                f"[LATS SSE] 检测到系统/用户消息类: {message.__class__.__name__}")
            return True

        return False

    def _format_ai_content(self, content: str) -> str:
        """格式化AI内容，提升可读性"""
        # 移除多余的空行
        lines = content.split('\n')
        formatted_lines = []

        for line in lines:
            stripped_line = line.strip()
            if stripped_line:  # 只保留非空行
                formatted_lines.append(stripped_line)

        # 重新组织内容，添加适当的换行和格式
        formatted_content = '\n\n'.join(formatted_lines)

        # 如果内容不是以标题开头，添加一个标题
        if not formatted_content.startswith('#') and not formatted_content.startswith('**'):
            formatted_content = f"📋 **基于搜索结果的分析**\n\n{formatted_content}"

        return formatted_content

    async def _handle_reflection_content(self, res, content: str) -> None:
        """处理包含reflection的内容"""
        try:
            # 分离正常内容和reflection JSON
            parts = content.split('{', 1)
            if len(parts) == 2:
                normal_content = parts[0].strip()
                json_part = '{' + parts[1]

                # 先输出正常内容
                if normal_content:
                    await self.send_sse(res, self.formatter.format_content(normal_content))

                # 解析和格式化reflection
                try:
                    reflection_data = json.loads(json_part)
                    await self._format_and_send_reflection(res, reflection_data)
                except json.JSONDecodeError:
                    # 如果解析失败，输出原始内容
                    await self.send_sse(res, self.formatter.format_content(content))
            else:
                # 没有分离成功，输出原始内容
                await self.send_sse(res, self.formatter.format_content(content))
        except Exception as e:
            logger.error(f"[LATS SSE] 处理reflection内容失败: {e}")
            # 出错时输出原始内容
            await self.send_sse(res, self.formatter.format_content(content))

    async def _format_and_send_reflection(self, res, reflection_data: dict) -> None:
        """格式化并发送reflection数据"""
        reflections = reflection_data.get('reflections', '')
        score = reflection_data.get('score', 0)
        found_solution = reflection_data.get('found_solution', False)

        # 展示思考过程
        if reflections:
            await self.send_sse(res, self.formatter.format_thinking_process(
                f"\n\n**AI 分析过程**\n\n{reflections}"
            ))

        # 展示评估结果
        await self.send_sse(res, self.formatter.format_reflection(
            reflections, score
        ))

        # 如果找到解决方案，展示状态
        if found_solution and score >= 9:
            await self.send_sse(res, self.formatter.format_content(
                "\n🎉 **完美解决方案！** 无需进一步优化\n"
            ))

        elif found_solution:
            await self.send_sse(res, self.formatter.format_content(
                "\n✅ **解决方案已找到！**\n"
            ))

    async def send_completion(self, res) -> None:
        """发送完成消息"""
        try:
            # 发送完成统计
            await self.send_sse(res, self.formatter.format_completion())

            # 发送结束信号
            end_response = {
                "id": self.chat_id,
                "object": "chat.completion.chunk",
                "created": int(datetime.now().timestamp()),
                "model": self.model,
                "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
            }

            json_str = json.dumps(
                end_response, ensure_ascii=False, separators=(',', ':'))

            await res.write(f"data: {json_str}\n\n".encode('utf-8'))
            await res.write("data: [DONE]\n\n".encode('utf-8'))

        except Exception as e:
            logger.error(f"[LATS SSE] 发送完成消息失败: {e}")


async def stream_lats_response(workflow, body: Dict[str, Any], chat_id: str, model: str, res) -> None:
    """
    优化的 LATS Agent 流式响应处理函数

    简化逻辑，提升性能，优化用户体验
    防止消息错乱，确保输出顺序
    """
    handler = LatsSSEHandler(chat_id, model)
    await handler.handle_search_flow(res, workflow, body)
