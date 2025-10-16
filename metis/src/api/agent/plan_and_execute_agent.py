from loguru import logger
from sanic import Blueprint, json
from sanic_ext import validate
from sanic.response import ResponseStream
from neco.sanic.auth.api_auth import auth
from src.services.agent_service import AgentService
from neco.llm.agent.plan_and_execute_agent import *
from typing import Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import asyncio
import json

plan_and_execute_agent_router = Blueprint(
    "plan_and_execute_agent_router", url_prefix="/agent"
)


@dataclass
class SSEDisplayConfig:
    """SSE 显示配置"""

    # 是否显示详细的工具执行信息
    show_tool_details: bool = True

    # 是否显示步骤进度
    show_progress: bool = True

    # 是否显示执行时间
    show_timing: bool = True

    # 工具结果摘要的最大长度
    tool_result_max_length: int = 200

    # 是否启用表情符号
    enable_emojis: bool = True

    # 自定义阶段显示文本（可选，外部传入）
    phase_texts: Dict[str, str] = None

    # 工具名称映射（可选，外部传入，不提供默认值）
    tool_display_names: Dict[str, str] = None


@plan_and_execute_agent_router.post("/invoke_plan_and_execute_agent")
@auth.login_required
@validate(json=PlanAndExecuteAgentRequest)
async def invoke_plan_and_execute_agent(request, body: PlanAndExecuteAgentRequest):
    """
    Plan and Execute Agent 同步执行接口

    返回格式化后的执行结果，包含消息内容和Token统计信息
    """
    graph = PlanAndExecuteAgentGraph()
    AgentService.prepare_request(body)

    logger.debug(f"执行PlanAndExecuteAgentGraph，用户的问题：[{body.user_message}]")
    result = await graph.execute(body)

    # 使用格式化器美化响应
    formatted_response = PlanExecuteResponseFormatter.format_response(result)

    logger.info(
        f"执行PlanAndExecuteAgentGraph成功，用户的问题：[{body.user_message}]，"
        f"响应Token数：{formatted_response.get('total_tokens', 0)}个"
    )
    return json(formatted_response)


@plan_and_execute_agent_router.post("/invoke_plan_and_execute_agent_sse")
@auth.login_required
@validate(json=PlanAndExecuteAgentRequest)
async def invoke_plan_and_execute_agent_sse(request, body: PlanAndExecuteAgentRequest):
    """
    优雅的 Plan and Execute Agent SSE 接口

    提供类似 Claude 的执行体验，包括：
    - 清晰的阶段划分（规划、执行、完成）
    - 优雅的进度显示
    - 简洁的工具调用反馈
    - 结构化的最终输出
    """
    workflow = PlanAndExecuteAgentGraph()
    AgentService.prepare_request(body)
    logger.debug(f"执行优雅的PlanAndExecuteAgentGraph，用户的问题：[{body.user_message}]")

    # 生成聊天ID
    import uuid
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    async def sse_stream(response):
        async for data in stream_plan_execute_response(workflow, body, chat_id):
            await response.write(data.encode('utf-8'))

    return ResponseStream(
        sse_stream,
        content_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保实时流式传输
            "Content-Encoding": "identity"  # 确保不压缩内容
        }
    )


class PlanExecuteResponseFormatter:
    """Plan and Execute Agent 响应格式化器"""

    @staticmethod
    def format_response(raw_response: PlanAndExecuteAgentResponse) -> Dict[str, Any]:
        """
        格式化 Plan and Execute Agent 的响应为简洁的结构

        Args:
            raw_response: 原始响应对象

        Returns:
            格式化后的响应字典
        """
        try:
            # 返回简洁的格式，类似 BasicLLMResponse
            formatted_response = {
                "message": raw_response.message or "执行完成",
                "total_tokens": raw_response.total_tokens,
                "prompt_tokens": raw_response.prompt_tokens,
                "completion_tokens": raw_response.completion_tokens
            }

            return formatted_response

        except Exception as e:
            return {
                "message": f"响应格式化失败: {str(e)}",
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0
            }


class ExecutionPhase(Enum):
    """执行阶段枚举"""
    INITIALIZING = "initializing"  # 初始化
    PLANNING = "planning"          # 规划中
    EXECUTING = "executing"        # 执行中
    REPLANNING = "replanning"      # 重新规划
    TOOL_CALLING = "tool_calling"  # 工具调用
    FINALIZING = "finalizing"      # 最终化
    COMPLETED = "completed"        # 已完成


@dataclass
class ExecutionStatus:
    """执行状态"""
    phase: ExecutionPhase
    step_index: int = 0
    total_steps: int = 0
    current_task: str = ""
    tool_name: str = ""
    progress_percentage: int = 0


class PlanExecuteSSEFormatter:
    """Plan and Execute Agent SSE 格式化器"""

    def __init__(self, chat_id: str, model: str, config: SSEDisplayConfig = None):
        self.chat_id = chat_id
        self.model = model
        self.config = config or SSEDisplayConfig()
        self.created_time = int(datetime.now().timestamp())
        self.current_status = ExecutionStatus(ExecutionPhase.INITIALIZING)
        self.plan_steps: List[str] = []
        self.completed_steps: List[str] = []
        self.start_time = datetime.now()

    def _create_base_response(self, delta_content: str = None,
                              finish_reason: str = None,
                              metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建基础响应对象"""
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
            # 添加自定义元数据用于前端渲染
            "metis_metadata": {
                "execution_phase": self.current_status.phase.value,
                "step_index": self.current_status.step_index,
                "total_steps": self.current_status.total_steps,
                "progress_percentage": self.current_status.progress_percentage,
                **(metadata or {})
            }
        }

        if delta_content is not None:
            response["choices"][0]["delta"]["content"] = delta_content

        return response

    def _format_sse_data(self, response: Dict[str, Any]) -> str:
        """格式化 SSE 数据，确保中文字符正确编码"""
        json_str = json.dumps(
            response, ensure_ascii=False, separators=(',', ':'))
        return f"data: {json_str}\n\n"

    def format_initialization(self) -> str:
        """格式化初始化阶段"""
        self.current_status.phase = ExecutionPhase.INITIALIZING
        content = self.config.phase_texts.get("initializing", "分析问题中...")

        response = self._create_base_response(
            delta_content=content,
            metadata={"status_message": "初始化中"}
        )
        return self._format_sse_data(response)

    def format_planning_start(self) -> str:
        """格式化开始规划阶段"""
        self.current_status.phase = ExecutionPhase.PLANNING
        prefix = "\n\n" if self.config.enable_emojis else "\n"
        content = f"{prefix}{self.config.phase_texts.get('planning', '制定计划...')}\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={"status_message": "规划中"}
        )
        return self._format_sse_data(response)

    def format_plan_generated(self, plan_steps: List[str]) -> str:
        """格式化生成的计划"""
        self.plan_steps = plan_steps
        self.current_status.total_steps = len(plan_steps)

        # 创建优雅的计划展示
        emoji_prefix = "✅ " if self.config.enable_emojis else ""
        rocket_emoji = "🚀 " if self.config.enable_emojis else ""

        plan_content = f"\n{emoji_prefix}**执行计划已制定：**\n\n"
        for i, step in enumerate(plan_steps, 1):
            plan_content += f"**步骤 {i}：** {step}\n"

        plan_content += f"\n{rocket_emoji}开始执行计划（共 {len(plan_steps)} 个步骤）\n\n"

        response = self._create_base_response(
            delta_content=plan_content,
            metadata={
                "status_message": "计划已生成",
                "plan_steps": plan_steps
            }
        )
        return self._format_sse_data(response)

    def format_step_start(self, step_index: int, task_description: str) -> str:
        """格式化步骤开始"""
        self.current_status.phase = ExecutionPhase.EXECUTING
        self.current_status.step_index = step_index
        self.current_status.current_task = task_description
        self.current_status.progress_percentage = int(
            (step_index / self.current_status.total_steps) * 100)

        content = f"---\n\n⚡ **执行步骤 {step_index}/{self.current_status.total_steps}：**{task_description}\n\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={
                "status_message": f"执行步骤 {step_index}",
                "current_task": task_description
            }
        )
        return self._format_sse_data(response)

    def format_tool_call_start(self, tool_name: str, tool_description: str = None) -> str:
        """格式化工具调用开始"""
        self.current_status.phase = ExecutionPhase.TOOL_CALLING
        self.current_status.tool_name = tool_name

        # 美化工具名称显示
        tool_display_name = self._get_tool_display_name(tool_name)
        desc = f" - {tool_description}" if tool_description else ""

        content = f"🔧 正在使用 **{tool_display_name}**{desc}...\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={
                "status_message": f"调用工具：{tool_display_name}",
                "tool_name": tool_name
            }
        )
        return self._format_sse_data(response)

    def format_tool_result(self, tool_name: str, result_summary: str) -> str:
        """格式化工具执行结果"""
        tool_display_name = self._get_tool_display_name(tool_name)

        content = f"✅ **{tool_display_name}** 执行完成\n"

        # 如果结果过长，只显示摘要
        if len(result_summary) > 200:
            content += f"📊 获得结果摘要：{result_summary[:200]}...\n\n"
        else:
            content += f"📊 结果：{result_summary}\n\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={
                "status_message": f"工具执行完成：{tool_display_name}",
                "tool_result_summary": result_summary[:500]
            }
        )
        return self._format_sse_data(response)

    def format_step_completed(self, step_index: int, step_result: str) -> str:
        """格式化步骤完成"""
        self.completed_steps.append(
            self.plan_steps[step_index - 1] if step_index <= len(self.plan_steps) else "未知步骤")

        content = f"✅ **步骤 {step_index} 完成**\n\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={
                "status_message": f"步骤 {step_index} 已完成",
                "completed_steps": len(self.completed_steps)
            }
        )
        return self._format_sse_data(response)

    def format_replanning(self, reason: str) -> str:
        """格式化重新规划"""
        self.current_status.phase = ExecutionPhase.REPLANNING

        content = f"\n🔄 **需要调整计划**\n💡 原因：{reason}\n📋 正在重新制定计划...\n\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={
                "status_message": "重新规划中",
                "replan_reason": reason
            }
        )
        return self._format_sse_data(response)

    def format_final_answer_start(self) -> str:
        """格式化开始生成最终答案"""
        self.current_status.phase = ExecutionPhase.FINALIZING

        content = "\n---\n\n🎯 **正在整理最终答案...**\n\n"

        response = self._create_base_response(
            delta_content=content,
            metadata={"status_message": "生成最终答案中"}
        )
        return self._format_sse_data(response)

    def format_final_content(self, content: str) -> str:
        """格式化最终内容"""
        response = self._create_base_response(
            delta_content=content,
            metadata={"status_message": "输出最终答案"}
        )
        return self._format_sse_data(response)

    def format_completion(self) -> str:
        """格式化完成"""
        self.current_status.phase = ExecutionPhase.COMPLETED
        self.current_status.progress_percentage = 100

        emoji_prefix = "✨ " if self.config.enable_emojis else ""
        chart_emoji = "📊 " if self.config.enable_emojis else ""
        clock_emoji = "⏱️ " if self.config.enable_emojis else ""

        summary_content = f"\n\n---\n\n{emoji_prefix}**任务完成！**\n"
        summary_content += f"{chart_emoji}总共执行了 {len(self.completed_steps)} 个步骤\n"

        if self.config.show_timing:
            execution_time = datetime.now() - self.start_time
            minutes, seconds = divmod(execution_time.total_seconds(), 60)
            time_str = f"{int(minutes)}分{int(seconds)}秒" if minutes > 0 else f"{int(seconds)}秒"
            summary_content += f"{clock_emoji}执行时间：{time_str}\n"

        response = self._create_base_response(
            delta_content=summary_content,
            finish_reason="stop",
            metadata={
                "status_message": "任务完成",
                "total_completed_steps": len(self.completed_steps)
            }
        )
        return self._format_sse_data(response)

    def _get_tool_display_name(self, tool_name: str) -> str:
        """
        获取工具的友好显示名称

        优先级：
        1. 配置的自定义映射
        2. 工具原始名称
        """
        if self.config.tool_display_names and tool_name in self.config.tool_display_names:
            return self.config.tool_display_names[tool_name]

        # 直接返回工具原始名称，不做任何转换
        return tool_name


# 默认配置（移除硬编码）
DEFAULT_SSE_CONFIG = SSEDisplayConfig()

# 简洁模式配置
MINIMAL_SSE_CONFIG = SSEDisplayConfig(
    show_tool_details=False,
    show_timing=False,
    tool_result_max_length=100,
    enable_emojis=False
)

# 详细模式配置
VERBOSE_SSE_CONFIG = SSEDisplayConfig(
    show_tool_details=True,
    show_progress=True,
    show_timing=True,
    tool_result_max_length=500,
    enable_emojis=True
)


class MessageTracker:
    """智能消息跟踪器，用于精确去重和状态管理"""
    
    def __init__(self):
        self.sent_message_hashes = set()  # 已发送消息的hash
        self.execution_phase = "init"  # 当前执行阶段
        self.step_count = 0  # 步骤计数
        self.node_outputs = {}  # 各节点的输出记录
        self.user_message = ""  # 用户原始问题
        
    def set_user_message(self, message: str):
        """设置用户原始问息，用于过滤重复"""
        self.user_message = message.strip()
        
    def _calculate_content_hash(self, content: str) -> str:
        """计算内容hash"""
        import hashlib
        return hashlib.md5(content.encode('utf-8')).hexdigest()
        
    def should_send_message(self, content: str, message_type: str = "general") -> bool:
        """
        判断是否应该发送消息
        Args:
            content: 消息内容
            message_type: 消息类型 (planner, executor, replanner, summary, tool, general)
        """
        if not content or not content.strip():
            return False
            
        content = content.strip()
        
        # 1. 过滤用户原始问题的重复
        if content == self.user_message:
            logger.debug(f"[MessageTracker] 跳过用户原始问题重复: {content[:30]}...")
            return False
            
        # 2. 基于内容hash去重 
        content_hash = self._calculate_content_hash(content)
        if content_hash in self.sent_message_hashes:
            logger.debug(f"[MessageTracker] 跳过重复内容: {content[:30]}...")
            return False
            
        # 3. 基于消息类型和执行阶段的智能过滤
        if message_type == "planner":
            if "planner_output" in self.node_outputs:
                logger.debug(f"[MessageTracker] 跳过重复的planner输出")
                return False
            self.node_outputs["planner_output"] = content_hash
            self.execution_phase = "planning"
            
        elif message_type == "replanner":
            # replanner消息允许多次（因为可能有多轮重新规划），但要避免完全相同的内容
            replanner_key = f"replanner_{self.step_count}"
            if replanner_key in self.node_outputs and self.node_outputs[replanner_key] == content_hash:
                logger.debug(f"[MessageTracker] 跳过重复的replanner输出")
                return False
            self.node_outputs[replanner_key] = content_hash
            self.execution_phase = "replanning"
            
        elif message_type == "summary":
            if "summary_output" in self.node_outputs:
                logger.debug(f"[MessageTracker] 跳过重复的summary输出")
                return False
            self.node_outputs["summary_output"] = content_hash
            self.execution_phase = "completed"
            
        elif message_type == "progress":
            # 进度消息允许重复，但要记录
            self.step_count += 1
            
        # 4. 过滤内部协调消息
        if self._is_internal_coordination_message(content):
            logger.debug(f"[MessageTracker] 跳过内部协调消息: {content[:30]}...")
            return False
            
        # 记录已发送的消息
        self.sent_message_hashes.add(content_hash)
        return True
        
    def _is_internal_coordination_message(self, content: str) -> bool:
        """判断是否为内部协调消息"""
        # 重要：不要过滤掉计划相关的信息和总结信息
        important_keywords = [
            "执行计划已制定", "计划推理", "执行步骤", "剩余步骤", "计划已调整",
            "### 📋", "任务完成总结", "🎯 **最终结果**", "📊 任务完成总结",
            "🎯 **执行结果**", "执行结果"
        ]
        if any(keyword in content for keyword in important_keywords):
            return False  # 这些是重要的计划、执行和总结信息，不应过滤
            
        internal_indicators = [
            content.startswith("请执行以下具体步骤"),  # 内部执行提示
            "🤔" in content,  # 思考过程
            content.strip().startswith("{") and content.strip().endswith("}"),  # JSON格式
            len(content.strip()) < 10,  # 过短的内容可能是无意义的
        ]
        return any(internal_indicators)


async def stream_plan_execute_response(
    workflow,
    body: Dict[str, Any],
    chat_id: str,
    model: str = "plan-execute"
) -> AsyncGenerator[str, None]:
    """
    流式处理 Plan and Execute Agent 响应
    使用智能去重和状态跟踪，提供清晰的用户体验
    """
    created = int(datetime.now().timestamp())
    message_tracker = MessageTracker()  # 智能消息跟踪器
    tool_call_pending = False  # 是否有待处理的工具调用
    last_tool_name = ""  # 最后一个工具名称
    
    # 设置用户原始问题
    user_message = body.user_message if hasattr(body, 'user_message') else ""
    message_tracker.set_user_message(user_message)

    try:
        logger.info(f"[Plan Execute SSE] 开始流式处理，chat_id: {chat_id}")

        # 发送简洁的开始消息
        start_content = "🎯 **正在分析您的请求...**\n"
        if message_tracker.should_send_message(start_content, "init"):
            yield _create_sse_data(chat_id, created, model, start_content)

        # 获取流式迭代器
        stream_iter = await workflow.stream(body)

        async for chunk in stream_iter:
            if not chunk or chunk is None:
                logger.debug(f"[Plan Execute SSE] 跳过空的或None的chunk")
                continue

            if isinstance(chunk, (tuple, list)) and len(chunk) > 0:
                message = chunk[0]

                if message is None:
                    logger.debug(f"[Plan Execute SSE] 跳过None消息")
                    continue

                message_type = type(message).__name__

                if message_type == "AIMessageChunk":
                    if hasattr(message, 'content') and message.content:
                        yield _create_sse_data(chat_id, created, model, message.content)
                    continue

                elif message_type == "AIMessage":
                    # 检查是否包含工具调用
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        # 有工具调用，标记待处理状态
                        tool_call_pending = True
                        for tool_call in message.tool_calls:
                            tool_name = tool_call.get('name', '未知工具')
                            last_tool_name = tool_name
                            content = f"\n\n🔧 **正在调用工具：{tool_name}**\n"
                            if message_tracker.should_send_message(content, "tool_start"):
                                yield _create_sse_data(chat_id, created, model, content)
                                logger.info(
                                    f"[Plan Execute SSE] 工具调用开始: {tool_name}")
                    else:
                        # 没有工具调用，可能是最终回答或中间思考
                        content = _extract_message_content(
                            message, message_tracker.step_count, user_message)
                        
                        # 智能判断消息类型
                        msg_type = "general"
                        if "执行计划已制定" in content or "计划推理" in content:
                            msg_type = "planner"
                        elif "计划已调整" in content or "剩余步骤" in content:
                            msg_type = "replanner" 
                        elif any(keyword in content for keyword in ["最终结果", "任务总结", "### 📋", "📊 任务完成总结", "任务完成总结"]):
                            msg_type = "summary"
                        elif "🎯 **执行结果**" in content or "执行结果" in content:
                            msg_type = "execution_result"
                        elif "步骤" in content and "完成" in content:
                            msg_type = "progress"
                            
                        if message_tracker.should_send_message(content, msg_type):
                            # 确保重要消息前有适当的换行分隔
                            if msg_type in ["planner", "replanner", "summary", "progress", "execution_result"]:
                                if not content.startswith('\n'):
                                    # 对于summary类型，确保前面有双换行
                                    if msg_type == "summary":
                                        content = f"\n\n{content}"
                                    elif msg_type == "execution_result":
                                        # 执行结果前也需要换行分隔
                                        content = f"\n{content}"
                                    else:
                                        content = f"\n{content}"
                            yield _create_sse_data(chat_id, created, model, content)
                            logger.info(
                                f"[Plan Execute SSE] 发送AI消息({msg_type}): {content[:50]}...")

                elif message_type == "HumanMessage":
                    # 检查是否是步骤开始消息（但要过滤掉用户原始输入的重复）
                    if hasattr(message, 'content') and message.content:
                        raw_content = message.content.strip()

                        # 使用智能跟踪器处理人类消息
                        if message_tracker.should_send_message(raw_content, "human"):
                            # 检查是否是步骤开始标记
                            if "开始执行任务" in raw_content and "执行步骤" not in raw_content:
                                content = f"\n\n⚡ **开始执行步骤 {message_tracker.step_count + 1}**\n"
                                if message_tracker.should_send_message(content, "step_start"):
                                    yield _create_sse_data(chat_id, created, model, content)
                                    logger.info(
                                        f"[Plan Execute SSE] 步骤开始: 步骤{message_tracker.step_count}")
                    continue

                elif message_type == "ToolMessage":
                    # 工具执行完成，显示结果摘要
                    if tool_call_pending:
                        tool_name = last_tool_name or _extract_tool_name(
                            message)
                        result_summary = _extract_tool_result_summary(message)

                        content = f"\n\n✅ **{tool_name}** 执行完成"
                        if result_summary:
                            content += f" - {result_summary}"
                        content += f"\n"  # 确保工具执行完成消息后有换行

                        if message_tracker.should_send_message(content, "tool_result"):
                            yield _create_sse_data(chat_id, created, model, content)
                            logger.info(
                                f"[Plan Execute SSE] 工具执行完成: {tool_name}")

                        tool_call_pending = False
                        last_tool_name = ""
                    continue

                elif message_type == "SystemMessage":
                    logger.debug(f"[Plan Execute SSE] 跳过系统消息")
                    continue

                else:
                    logger.debug(
                        f"[Plan Execute SSE] 处理未知消息类型: {message_type}")
                    content = _extract_message_content(
                        message, message_tracker.step_count, user_message)
                    if message_tracker.should_send_message(content, "unknown"):
                        yield _create_sse_data(chat_id, created, model, content)
                        logger.info(
                            f"[Plan Execute SSE] 发送未知类型消息: {content[:50]}...")

        # 只有当没有发送过总结时，才发送简洁的完成消息
        has_summary = "summary_output" in message_tracker.node_outputs
        if not has_summary:
            completion_content = "\n\n✨ **任务执行完成！**\n"
            if message_tracker.should_send_message(completion_content, "completion"):
                yield _create_sse_data(chat_id, created, model, completion_content)

        # 发送结束标志
        end_response = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "delta": {},
                "index": 0,
                "finish_reason": "stop"
            }]
        }

        json_str = json.dumps(
            end_response, ensure_ascii=False, separators=(',', ':'))
        yield f"data: {json_str}\n\n"

        logger.info(f"[Plan Execute SSE] 流式处理完成，chat_id: {chat_id}")

    except Exception as e:
        logger.error(f"[Plan Execute SSE] 处理过程中出错: {str(e)}", exc_info=True)
        error_content = f"\n\n❌ **处理遇到问题** - {str(e)}\n"
        yield _create_sse_data(chat_id, created, model, error_content, finish_reason="stop")


def _create_sse_data(chat_id: str, created: int, model: str, content: str, finish_reason: str = None) -> str:
    """创建SSE数据"""
    response = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "delta": {
                "role": "assistant",
                "content": content
            },
            "index": 0,
            "finish_reason": finish_reason
        }]
    }

    json_str = json.dumps(response, ensure_ascii=False, separators=(',', ':'))
    return f"data: {json_str}\n\n"


def _extract_tool_name(message: Any) -> str:
    """
    从ToolMessage中提取工具名称
    """
    try:
        # 尝试从name属性获取
        if hasattr(message, 'name') and message.name:
            return message.name

        # 尝试从tool_call_id解析
        if hasattr(message, 'tool_call_id') and message.tool_call_id:
            return message.tool_call_id

        # 尝试从additional_kwargs获取
        if hasattr(message, 'additional_kwargs'):
            kwargs = message.additional_kwargs
            if isinstance(kwargs, dict) and 'tool_name' in kwargs:
                return kwargs['tool_name']

        return "未知工具"

    except Exception as e:
        logger.debug(f"[Plan Execute SSE] 提取工具名称失败: {e}")
        return "未知工具"


def _extract_message_content(message: Any, step_counter: int = 0, user_message: str = "") -> str:
    """
    从消息对象中提取内容，优化显示效果
    注意：ToolMessage 已在主流程中单独处理，此函数不再处理工具结果

    Args:
        message: 消息对象
        step_counter: 当前步骤计数
        user_message: 用户原始问题（用于过滤重复输出）
    """
    content = ""

    try:
        if message is None:
            logger.debug(f"[Plan Execute SSE] 消息为None，跳过处理")
            return ""

        message_type = type(message).__name__
        logger.debug(f"[Plan Execute SSE] 处理消息类型: {message_type}")

        # 检查消息是否有content属性
        if hasattr(message, 'content'):
            raw_content = message.content
            logger.debug(
                f"[Plan Execute SSE] 消息内容: {raw_content[:100] if raw_content else 'None'}")

            if isinstance(raw_content, str) and raw_content.strip():
                content = raw_content.strip()

                # 过滤用户原始问题的重复输出
                if content == user_message or content.strip() == user_message.strip():
                    logger.debug(f"[Plan Execute SSE] 跳过用户原始问题的重复输出")
                    return ""

                # 根据消息类型进行不同的格式化处理
                if message_type == "ToolMessage":
                    # ToolMessage 已在主流程单独处理，这里跳过
                    return ""
                elif message_type == "AIMessage":
                    # AI消息需要过滤和美化
                    content = content
                elif message_type == "SystemMessage":
                    # 跳过系统消息
                    return ""
                elif message_type == "HumanMessage":
                    # 人类消息，需要进一步过滤
                    # 跳过包含"思考中"前缀的重复内容
                    if content.startswith("🤔"):
                        return ""
                    # 跳过技术性的执行步骤列表
                    if "执行步骤" in content and content.count("\n") > 3:
                        return ""
                    # 其他人类消息也不输出（通常是内部协调信息）
                    return ""
                else:
                    # 其他类型的消息
                    content = _format_general_message(content)

        # 检查消息是否有其他可能的内容字段
        elif hasattr(message, 'text'):
            content = message.text.strip() if message.text else ""
        elif hasattr(message, 'data'):
            content = str(message.data).strip() if message.data else ""

        return content

    except Exception as e:
        logger.error(f"[Plan Execute SSE] 提取消息内容失败: {str(e)}")
        return ""


def _format_general_message(content: str) -> str:
    """格式化一般消息，确保适当的换行分隔"""
    # 过滤掉技术细节和JSON内容
    if any(keyword in content.lower() for keyword in ["json", "{", "tool", "args"]):
        return ""

    # 确保消息前后都有适当的换行
    if "执行步骤" in content:
        return f"\n\n⚡ **执行中** - {content}\n"
    elif "🎯 **执行结果**" in content or "执行结果" in content:
        return f"\n{content}\n"  # 执行结果消息已经有emoji和格式，只需要换行
    elif "完成" in content:
        return f"\n\n✅ **完成** - {content}\n"
    elif "搜索" in content:
        return f"\n\n🔍 **搜索中** - {content}\n"
    elif "分析" in content:
        return f"\n\n📊 **分析中** - {content}\n"
    else:
        # 对于一般消息，确保前后都有换行
        return f"\n\n{content}\n"


def _extract_tool_result_summary(message: Any) -> str:
    """
    从ToolMessage中提取结果摘要
    """
    try:
        if not hasattr(message, 'content') or not message.content:
            return ""

        content = message.content.strip()

        # 如果是JSON格式，尝试解析并生成摘要
        if content.startswith('{') or content.startswith('['):
            try:
                import json
                data = json.loads(content)

                # 根据不同的数据结构生成摘要
                if isinstance(data, dict):
                    # 对于GitHub commits等结构化数据
                    if all(isinstance(v, list) for v in data.values()):
                        total_items = sum(len(v) for v in data.values())
                        return f"获取到 {total_items} 条记录"
                    else:
                        return f"获取到 {len(data)} 个字段的数据"
                elif isinstance(data, list):
                    return f"获取到 {len(data)} 条记录"
                else:
                    return str(data)[:100]

            except json.JSONDecodeError:
                pass

        # 对于纯文本结果
        if len(content) > 100:
            return content[:100] + "..."
        else:
            return content

    except Exception as e:
        logger.debug(f"[Plan Execute SSE] 提取工具结果摘要失败: {e}")
        return ""
