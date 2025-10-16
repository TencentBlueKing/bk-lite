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


async def stream_plan_execute_response(
    workflow,
    body: Dict[str, Any],
    chat_id: str,
    model: str = "plan-execute"
) -> AsyncGenerator[str, None]:
    """
    流式处理 Plan and Execute Agent 响应
    使用简化的标准SSE格式，提供优雅的用户体验
    """
    created = int(datetime.now().timestamp())
    sent_contents = set()  # 用于去重
    step_counter = 0  # 步骤计数器

    try:
        logger.info(f"[Plan Execute SSE] 开始流式处理，chat_id: {chat_id}")

        # 发送简洁的开始消息
        start_content = "🎯 **正在分析您的请求...**\n"
        yield _create_sse_data(chat_id, created, model, start_content)
        sent_contents.add(start_content)

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
                    content = _extract_message_content(message, step_counter)
                    if content and content not in sent_contents:
                        yield _create_sse_data(chat_id, created, model, content)
                        sent_contents.add(content)
                        logger.info(
                            f"[Plan Execute SSE] 发送AI消息: {content[:50]}...")

                elif message_type == "HumanMessage":
                    if hasattr(message, 'content') and message.content:
                        raw_content = message.content.strip()
                        if raw_content and not any(keyword in raw_content.lower() for keyword in ["json", "tool", "{"]):
                            content = f"🤔 **思考中...**\n{raw_content}\n"
                            if content not in sent_contents:
                                yield _create_sse_data(chat_id, created, model, content)
                                sent_contents.add(content)
                                logger.info(
                                    f"[Plan Execute SSE] 发送人类消息: {content[:50]}...")
                    continue

                elif message_type == "ToolMessage":
                    tool_name = _extract_tool_name(message)
                    if tool_name:
                        content = f"🔧 正在执行【{tool_name}】工具\n"
                        if content not in sent_contents:
                            yield _create_sse_data(chat_id, created, model, content)
                            sent_contents.add(content)
                            logger.info(
                                f"[Plan Execute SSE] 工具执行: {tool_name}")
                    continue

                elif message_type == "SystemMessage":
                    logger.debug(f"[Plan Execute SSE] 跳过系统消息")
                    continue

                else:
                    logger.debug(
                        f"[Plan Execute SSE] 处理未知消息类型: {message_type}")
                    content = _extract_message_content(message, step_counter)
                    if content and content not in sent_contents:
                        yield _create_sse_data(chat_id, created, model, content)
                        sent_contents.add(content)
                        logger.info(
                            f"[Plan Execute SSE] 发送未知类型消息: {content[:50]}...")

        # 发送简洁的完成消息
        completion_content = "\n✨ **任务执行完成！**\n"
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
        error_content = f"\n❌ **处理遇到问题**\n{str(e)}\n"
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


def _extract_message_content(message: Any, step_counter: int = 0) -> str:
    """
    从消息对象中提取内容，优化显示效果
    注意：ToolMessage 已在主流程中单独处理，此函数不再处理工具结果
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
            logger.debug(f"[Plan Execute SSE] 消息内容: {raw_content}")

            if isinstance(raw_content, str) and raw_content.strip():
                content = raw_content.strip()

                # 根据消息类型进行不同的格式化处理
                if message_type == "ToolMessage":
                    # ToolMessage 已在主流程单独处理，这里跳过
                    return ""
                elif message_type == "AIMessage":
                    # AI消息需要过滤和美化
                    content = _format_ai_message(content, step_counter)
                elif message_type == "SystemMessage":
                    # 跳过系统消息
                    return ""
                elif message_type == "HumanMessage":
                    # 人类消息，直接格式化显示
                    content = f"🤔 **思考中...**\n\n{content}"
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


def _format_ai_message(content: str, step_counter: int = 0) -> str:
    """格式化AI消息，提取关键信息"""
    try:
        # 尝试解析JSON格式的计划 - 不输出JSON内容
        if content.startswith('{"steps"'):
            import json
            data = json.loads(content)
            if "steps" in data:
                steps = data["steps"]
                formatted_steps = []
                for i, step in enumerate(steps):
                    # 提取步骤描述，去掉工具调用细节
                    step_desc = step if isinstance(
                        step, str) else step.get("description", str(step))
                    formatted_steps.append(f"**{i+1}.** {step_desc}")
                steps_text = "\n".join(formatted_steps)
                return f"\n📋 **执行计划已制定**\n\n{steps_text}\n"
            # 如果解析失败，不输出JSON内容
            return ""

        # 尝试解析action格式
        elif content.startswith('{"action"'):
            import json
            data = json.loads(content)
            if "action" in data and "response" in data["action"]:
                response = data["action"]["response"]
                return f"\n✨ **最终答案**\n\n{response}\n"
            # 如果解析失败，不输出JSON内容
            return ""

        # 过滤掉不需要的内容
        elif content.startswith('{"') or content.startswith('[{'):
            # 跳过所有JSON格式的内容
            return ""
        elif "步骤" in content and ("tool" in content.lower() or "args" in content.lower()):
            # 跳过包含工具调用细节的步骤描述
            return ""
        elif "步骤" in content or "计划" in content:
            return f"\n📋 **制定计划中...**\n\n{content}\n"
        elif "最终答案" in content or "任务完成" in content:
            return f"\n✅ **最终答案**\n\n{content}\n"
        elif "执行步骤" in content or content.strip().startswith("步骤"):
            if "执行完成" in content or "结果:" in content:
                return f"\n⚡ **步骤执行完成**\n\n{content}\n"
            else:
                return f"\n⚡ **执行步骤**\n\n{content}\n"
        else:
            # 过滤掉"处理中"的内容和过长的技术细节
            if len(content) > 200 or any(keyword in content.lower() for keyword in ["json", "tool", "args", "api"]):
                return ""
            # 简化输出，减少换行
            return f"\n{content}\n"

    except Exception as e:
        logger.debug(f"JSON解析失败: {e}")
        # JSON解析失败时，不输出内容
        return ""


def _format_general_message(content: str) -> str:
    """格式化一般消息，减少换行符"""
    # 过滤掉技术细节和JSON内容
    if any(keyword in content.lower() for keyword in ["json", "{", "tool", "args"]):
        return ""

    if "执行步骤" in content:
        return f"\n⚡ **执行中**\n{content}\n"
    elif "完成" in content:
        return f"\n✅ **完成**\n{content}\n"
    elif "搜索" in content:
        return f"\n🔍 **搜索中**\n{content}\n"
    elif "分析" in content:
        return f"\n📊 **分析中**\n{content}\n"
    else:
        return f"\n{content}\n"
