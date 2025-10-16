import json
import uuid
from datetime import datetime
from typing import Dict, Any
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


@dataclass
class LatsSSEConfig:
    """LATS SSE 显示配置"""
    
    # 显示选项
    show_search_details: bool = True
    show_evaluation_progress: bool = True
    show_timing: bool = True
    enable_emojis: bool = True
    
    # 内容长度控制
    candidate_content_max_length: int = 150
    evaluation_summary_max_length: int = 200
    
    # 自定义显示文本
    phase_texts: Dict[str, str] = None
    
    def __post_init__(self):
        if self.phase_texts is None:
            self.phase_texts = {
                "analyzing": "🧠 正在智能分析您的问题...",
                "searching": "🌳 开始智能树搜索，寻找最优解答",
                "generating": "💡 生成多个解决方案候选",
                "evaluating": "📊 评估方案质量",
                "optimizing": "⚡ 发现更优方案，继续深度搜索",
                "synthesizing": "✨ 整合最佳答案",
                "completed": "🎉 智能搜索完成"
            }


class LatsExecutionPhase(Enum):
    """LATS 执行阶段"""
    ANALYZING = "analyzing"
    INITIAL_SEARCH = "initial_search"
    TREE_EXPANSION = "tree_expansion"
    EVALUATION = "evaluation"
    OPTIMIZATION = "optimization"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"


class LatsSSEFormatter:
    """LATS Agent SSE 优雅格式化器"""
    
    def __init__(self, chat_id: str, model: str, config: LatsSSEConfig = None):
        self.chat_id = chat_id
        self.model = model
        self.config = config or LatsSSEConfig()
        self.created_time = int(datetime.now().timestamp())
        self.current_phase = LatsExecutionPhase.ANALYZING
        self.search_iteration = 0
        self.total_candidates = 0
        self.best_score = 0.0
        self.start_time = datetime.now()
        
    def _create_base_response(self, 
                              delta_content: str = None, 
                              finish_reason: str = None,
                              metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建基础 SSE 响应"""
        response = {
            "id": self.chat_id,
            "object": "chat.completion.chunk", 
            "created": self.created_time,
            "model": self.model,
            "choices": [{
                "delta": {"role": "assistant"},
                "index": 0,
                "finish_reason": finish_reason
            }],
            # LATS 特定元数据
            "metis_metadata": {
                "execution_phase": self.current_phase.value,
                "search_iteration": self.search_iteration,
                "total_candidates": self.total_candidates,
                "best_score": self.best_score,
                **(metadata or {})
            }
        }
        
        if delta_content is not None:
            response["choices"][0]["delta"]["content"] = delta_content
            
        return response
    
    def _format_sse_data(self, response: Dict[str, Any]) -> str:
        """格式化 SSE 数据"""
        json_str = json.dumps(response, ensure_ascii=False, separators=(',', ':'))
        return f"data: {json_str}\n\n"
    
    def format_phase_transition(self, phase: LatsExecutionPhase) -> str:
        """格式化阶段转换"""
        self.current_phase = phase
        content = self.config.phase_texts.get(phase.value, f"进入 {phase.value} 阶段")
        
        response = self._create_base_response(
            delta_content=f"\n{content}\n",
            metadata={"phase_transition": True}
        )
        return self._format_sse_data(response)
    
    def format_search_iteration(self, iteration: int) -> str:
        """格式化搜索迭代开始"""
        self.search_iteration = iteration
        self.current_phase = LatsExecutionPhase.TREE_EXPANSION
        
        if iteration == 1:
            content = f"🎯 **启动智能搜索** - 第 {iteration} 轮探索"
        else:
            content = f"🔍 **深度搜索** - 第 {iteration} 轮优化 (已找到 {self.best_score:.1f}/10 分方案)"
            
        response = self._create_base_response(
            delta_content=f"\n{content}\n",
            metadata={"search_iteration": iteration}
        )
        return self._format_sse_data(response)
    
    def format_candidate_generation(self, index: int, total: int) -> str:
        """格式化候选生成进度"""
        content = f"💡 正在生成方案 {index}/{total}..."
        
        response = self._create_base_response(
            delta_content=content,
            metadata={
                "candidate_generation": True,
                "progress": f"{index}/{total}"
            }
        )
        return self._format_sse_data(response)
    
    def format_evaluation_start(self, candidate_count: int) -> str:
        """格式化评估开始"""
        self.current_phase = LatsExecutionPhase.EVALUATION
        self.total_candidates += candidate_count
        
        content = f"\n📊 **智能评估** - 分析 {candidate_count} 个候选方案\n"
        
        response = self._create_base_response(
            delta_content=content,
            metadata={"evaluation_start": True, "candidate_count": candidate_count}
        )
        return self._format_sse_data(response)
    
    def format_evaluation_result(self, index: int, score: float, is_solution: bool) -> str:
        """格式化单个评估结果"""
        self.best_score = max(self.best_score, score)
        
        if is_solution:
            content = f"🎉 候选 {index}: **{score:.1f}/10** ⭐ 优质解决方案"
        elif score >= 8.0:
            content = f"✨ 候选 {index}: **{score:.1f}/10** 高质量答案"
        elif score >= 6.0:
            content = f"👍 候选 {index}: **{score:.1f}/10** 良好方案"
        else:
            content = f"📝 候选 {index}: **{score:.1f}/10** 待优化"
            
        response = self._create_base_response(
            delta_content=content,
            metadata={
                "evaluation_result": True,
                "score": score,
                "is_solution": is_solution
            }
        )
        return self._format_sse_data(response)
    
    def format_search_summary(self, best_score: float, solutions_found: int) -> str:
        """格式化搜索轮次总结"""
        self.best_score = max(self.best_score, best_score)
        
        if solutions_found > 0:
            content = f"\n🏆 **本轮最佳: {best_score:.1f}/10** | ✅ 发现 {solutions_found} 个解决方案"
        elif best_score >= 8.0:
            content = f"\n⭐ **本轮最佳: {best_score:.1f}/10** | 🔍 继续寻找更优方案"
        else:
            content = f"\n📊 **本轮最佳: {best_score:.1f}/10** | ⚡ 扩展搜索空间"
            
        response = self._create_base_response(
            delta_content=content,
            metadata={
                "search_summary": True,
                "round_best_score": best_score,
                "solutions_found": solutions_found
            }
        )
        return self._format_sse_data(response)
    
    def format_final_synthesis(self) -> str:
        """格式化最终合成阶段"""
        self.current_phase = LatsExecutionPhase.SYNTHESIS
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        content = f"\n✨ **智能搜索完成** ({elapsed:.1f}s) | 🎯 为您整理最佳答案..."
        
        response = self._create_base_response(
            delta_content=content,
            metadata={"final_synthesis": True, "elapsed_time": elapsed}
        )
        return self._format_sse_data(response)
    
    def format_tool_execution(self, tool_name: str) -> str:
        """格式化工具执行"""
        display_name = {
            "naive_rag_search": "知识库搜索",
            "web_search": "网络搜索"
        }.get(tool_name, tool_name)
        
        content = f"🔧 正在使用 **{display_name}**"
        
        response = self._create_base_response(
            delta_content=content,
            metadata={"tool_execution": True, "tool_name": tool_name}
        )
        return self._format_sse_data(response)


async def stream_lats_response(workflow, body: Dict[str, Any], chat_id: str, model: str, res) -> None:
    """LATS Agent 优雅流式响应"""
    formatter = LatsSSEFormatter(chat_id, model)
    sent_contents = set()
    has_shown_final_synthesis = False
    
    try:
        logger.info(f"[LATS SSE] 开始优雅流式处理，chat_id: {chat_id}")
        
        # 1. 初始分析阶段
        start_content = formatter.format_phase_transition(LatsExecutionPhase.ANALYZING)
        await res.write(start_content.encode('utf-8'))
        
        stream_iter = await workflow.stream(body)
        
        async for chunk in stream_iter:
            if not chunk:
                continue
            
            # 处理最终状态 - 直接输出答案
            if _is_final_state(chunk):
                if not has_shown_final_synthesis:
                    synthesis_msg = formatter.format_final_synthesis()
                    await res.write(synthesis_msg.encode('utf-8'))
                    has_shown_final_synthesis = True
                
                await _handle_final_state_elegant(res, chunk, formatter, sent_contents)
                continue
            
            # 处理节点转换和评估结果
            if isinstance(chunk, dict):
                # 评估结果处理
                if 'evaluation_results' in chunk:
                    eval_results = chunk['evaluation_results']
                    if eval_results:
                        # 显示评估开始
                        eval_start_msg = formatter.format_evaluation_start(len(eval_results))
                        await res.write(eval_start_msg.encode('utf-8'))
                        
                        # 显示每个评估结果
                        for i, result in enumerate(eval_results, 1):
                            score = result.get('score', 0)
                            is_solution = result.get('found_solution', False)
                            eval_result_msg = formatter.format_evaluation_result(i, score, is_solution)
                            await res.write(eval_result_msg.encode('utf-8'))
                        
                        # 显示本轮总结
                        best_score = max(r.get('score', 0) for r in eval_results)
                        solutions_count = sum(1 for r in eval_results if r.get('found_solution', False))
                        summary_msg = formatter.format_search_summary(best_score, solutions_count)
                        await res.write(summary_msg.encode('utf-8'))
                    continue
                
                # 节点转换处理
                node_keys = list(chunk.keys())
                if len(node_keys) == 1:
                    node_name = node_keys[0]
                    
                    if node_name == 'expand':
                        # 搜索迭代
                        formatter.search_iteration += 1
                        iteration_msg = formatter.format_search_iteration(formatter.search_iteration)
                        await res.write(iteration_msg.encode('utf-8'))
                        continue
                    
                    elif node_name == 'generate_initial_response':
                        # 初始响应生成
                        initial_msg = formatter.format_phase_transition(LatsExecutionPhase.INITIAL_SEARCH)
                        await res.write(initial_msg.encode('utf-8'))
                        continue
                    
                    elif node_name == 'tools':
                        # 工具执行
                        tool_name = _get_tool_name(chunk[node_name])
                        tool_msg = formatter.format_tool_execution(tool_name)
                        await res.write(tool_msg.encode('utf-8'))
                        continue
            
            # 处理消息流 - 只输出重要内容
            if isinstance(chunk, (tuple, list)) and len(chunk) > 0:
                message = chunk[0]
                if not message:
                    continue
                
                message_type = type(message).__name__
                
                # AIMessageChunk - 直接流式输出
                if message_type == "AIMessageChunk":
                    if hasattr(message, 'content') and message.content:
                        content_data = formatter._format_sse_data({
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": formatter.created_time,
                            "model": model,
                            "choices": [{
                                "delta": {"role": "assistant", "content": message.content},
                                "index": 0,
                                "finish_reason": None
                            }]
                        })
                        await res.write(content_data.encode('utf-8'))
                    continue
                
                # AIMessage - 过滤并优雅显示
                elif message_type == "AIMessage":
                    content = _extract_elegant_ai_content(message)
                    if content and content not in sent_contents:
                        content_data = formatter._format_sse_data({
                            "id": chat_id,
                            "object": "chat.completion.chunk", 
                            "created": formatter.created_time,
                            "model": model,
                            "choices": [{
                                "delta": {"role": "assistant", "content": content},
                                "index": 0,
                                "finish_reason": None
                            }]
                        })
                        await res.write(content_data.encode('utf-8'))
                        sent_contents.add(content)
        
        # 发送完成标志
        await _write_sse_end(res, chat_id, formatter.created_time, model)
        
        logger.info(f"[LATS SSE] 优雅流式处理完成，chat_id: {chat_id}，搜索轮次: {formatter.search_iteration}")
        
    except Exception as e:
        logger.error(f"[LATS SSE] 处理出错: {str(e)}", exc_info=True)
        error_msg = formatter._format_sse_data({
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": formatter.created_time, 
            "model": model,
            "choices": [{
                "delta": {"role": "assistant", "content": "\n❌ **处理遇到问题，请稍后重试**"},
                "index": 0,
                "finish_reason": "stop"
            }]
        })
        await res.write(error_msg.encode('utf-8'))


async def _handle_final_state_elegant(res, chunk, formatter: LatsSSEFormatter, sent_contents: set):
    """优雅处理最终状态 - 只输出清洁的答案"""
    messages = chunk.get('messages', [])
    if not messages:
        return
    
    final_msg = messages[-1]
    if hasattr(final_msg, 'content') and final_msg.content:
        msg_type = type(final_msg).__name__
        if msg_type not in ['SystemMessage', 'HumanMessage']:
            # 清理和格式化最终答案
            content = _clean_final_answer(final_msg.content)
            if content and content not in sent_contents:
                content_data = formatter._format_sse_data({
                    "id": formatter.chat_id,
                    "object": "chat.completion.chunk",
                    "created": formatter.created_time,
                    "model": formatter.model,
                    "choices": [{
                        "delta": {"role": "assistant", "content": f"\n\n{content}"},
                        "index": 0,
                        "finish_reason": None
                    }]
                })
                await res.write(content_data.encode('utf-8'))
                sent_contents.add(content)


def _extract_elegant_ai_content(message) -> str:
    """提取优雅的AI消息内容 - 过滤技术细节"""
    try:
        if not hasattr(message, 'content'):
            return ""
        
        content = message.content.strip()
        if not content:
            return ""
        
        # 过滤技术性内容
        filter_keywords = [
            '"reflections"', '"score"', '"found_solution"', 
            "评分：", "/10", "置信度:", "候选", "评估",
            "🔍 **生成候选方案", "📊 **评估", "✅ 候选"
        ]
        
        if any(keyword in content for keyword in filter_keywords):
            return ""
        
        # 过滤过短或过于技术性的内容
        if len(content) < 20 or content.startswith("正在"):
            return ""
        
        return content
        
    except Exception as e:
        logger.debug(f"[LATS SSE] 内容提取失败: {e}")
        return ""


def _clean_final_answer(content: str) -> str:
    """清理最终答案，移除技术细节"""
    try:
        lines = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 过滤技术性行
            if any(keyword in line for keyword in ['评分', 'score', '置信度', '反思', 'reflection']):
                continue
                
            lines.append(line)
        
        return '\n\n'.join(lines) if lines else content
        
    except Exception:
        return content


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


async def _write_sse_end(res, chat_id: str, created: int, model: str):
    """写入SSE结束标志"""
    end_response = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
    }
    json_str = json.dumps(end_response, ensure_ascii=False, separators=(',', ':'))
    await res.write(f"data: {json_str}\n\n".encode('utf-8'))
    await res.write("data: [DONE]\n\n".encode('utf-8'))
