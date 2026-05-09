from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph, add_messages
from loguru import logger
from pydantic import BaseModel, Field

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from apps.opspilot.metis.llm.chain.graph import BasicGraph
from apps.opspilot.metis.llm.chain.node import ToolsNodes
from apps.opspilot.metis.utils.template_loader import TemplateLoader


class AgentConfig(BaseModel):
    """单个 Agent 配置"""

    name: str = Field(..., description="Agent 名称，用于识别和路由")
    description: str = Field(..., description="Agent 功能描述，用于 Supervisor 决策")
    system_message_prompt: str = Field(default="", description="Agent 专属系统提示词")
    tools_servers: List[ToolsServer] = Field(default_factory=list, description="Agent 专属工具服务")
    temperature: float = Field(default=0.7, description="Agent 温度参数")
    context_window_size: Optional[int] = Field(default=None, description="上下文窗口大小（消息数量）。None 表示使用全部消息")
    context_isolation: bool = Field(
        default=True,
        description="是否启用独立上下文。启用后子 Agent 只接收任务描述，不继承共享消息历史；" "执行结果仅以摘要形式返回 Supervisor，不暴露中间工具调用细节",
    )


class SupervisorMultiAgentRequest(BasicLLMRequest):
    """Supervisor Multi-Agent 请求配置"""

    # Supervisor 配置
    supervisor_system_prompt: str = Field(default="你是一个团队主管，负责协调多个专业 Agent 完成任务。", description="Supervisor 的系统提示词")
    supervisor_model: Optional[str] = Field(default=None, description="Supervisor 使用的模型，不指定则使用全局 model")

    # Agent 配置
    agents: List[AgentConfig] = Field(default_factory=list, description="所有 Agent 的配置列表")

    # 执行策略
    max_iterations: int = Field(default=10, description="最大迭代次数，防止无限循环")

    output_mode: Literal["full_history", "last_message"] = Field(
        default="last_message",
        description="输出模式：full_history 包含完整历史，last_message 仅包含最终响应",
    )

    # 上下文管理
    default_context_window_size: Optional[int] = Field(
        default=None,
        description="默认上下文窗口大小（消息数量）。None 表示使用全部消息，优先级低于 Agent 级配置",
    )
    supervisor_context_window_size: Optional[int] = Field(
        default=None,
        description="Supervisor 决策时的上下文窗口大小。None 表示使用全部消息",
    )
    default_context_isolation: bool = Field(
        default=True,
        description="默认是否启用子 Agent 独立上下文，优先级低于 Agent 级配置",
    )


class SupervisorMultiAgentResponse(BasicLLMResponse):
    """Supervisor Multi-Agent 响应"""

    executed_agents: List[str] = Field(default_factory=list, description="执行过的 Agent 名称列表")
    iterations: int = Field(default=0, description="实际迭代次数")


class SupervisorMultiAgentState(TypedDict):
    """Supervisor Multi-Agent 状态"""

    messages: Annotated[list, add_messages]
    graph_request: SupervisorMultiAgentRequest
    active_agent: Optional[str]  # 当前活跃的 Agent
    executed_agents: List[str]  # 已执行的 Agent 列表
    iterations: int  # 当前迭代次数
    next_action: Optional[str]  # Supervisor 决策：agent_name 或 "FINISH"


class SupervisorMultiAgentNode(ToolsNodes):
    """Supervisor Multi-Agent 节点构建器"""

    def __init__(self):
        super().__init__()
        # Agent 名称 -> ToolsNodes 映射
        self.agent_tools_map: Dict[str, ToolsNodes] = {}

    async def setup_supervisor(self, request: SupervisorMultiAgentRequest):
        """初始化 Supervisor（仅使用 Supervisor 自己的工具）"""
        await self.setup(request)

    async def setup_agents(self, request: SupervisorMultiAgentRequest):
        """初始化所有 Agent"""
        logger.info("🔧 开始初始化所有 Agent...")

        for agent_config in request.agents:
            # 为每个 Agent 创建独立的 ToolsNodes
            agent_node = ToolsNodes()

            # 构建 Agent 专属请求（继承全局配置 + Agent 配置）
            agent_request = BasicLLMRequest(
                openai_api_base=request.openai_api_base,
                openai_api_key=request.openai_api_key,
                model=request.model,
                system_message_prompt=agent_config.system_message_prompt,
                temperature=agent_config.temperature,
                tools_servers=agent_config.tools_servers,
                user_id=request.user_id,
                thread_id=request.thread_id,
            )

            await agent_node.setup(agent_request)
            self.agent_tools_map[agent_config.name] = agent_node

            logger.info(f"  ✓ Agent [{agent_config.name}] 初始化完成 - " f"工具数: {len(agent_node.tools)}, " f"温度: {agent_config.temperature}")

        logger.info(f"✅ 共初始化 {len(request.agents)} 个 Agent")

    async def supervisor_node(self, state: SupervisorMultiAgentState, config: RunnableConfig) -> Dict[str, Any]:
        """Supervisor 决策节点：选择下一个要执行的 Agent 或结束"""
        request: SupervisorMultiAgentRequest = config["configurable"]["graph_request"]

        current_iteration = state.get("iterations", 0) + 1
        executed_agents = state.get("executed_agents", [])

        logger.info("=" * 80)
        logger.info(f"🎯 Supervisor 第 {current_iteration} 轮决策（上限: {request.max_iterations}）")
        logger.info(f"📊 已执行 Agent: {executed_agents if executed_agents else '无'}")
        logger.info(f"� 已完成 {len(executed_agents)} 次 Agent 调用")

        # 检查是否超过最大迭代次数
        if state.get("iterations", 0) >= request.max_iterations:
            logger.warning(f"⚠️  达到最大迭代次数 {request.max_iterations}，强制结束")
            logger.info("=" * 80)
            return {"next_action": "FINISH", "iterations": current_iteration}

        # 准备 Supervisor 提示词
        supervisor_prompt = self._build_supervisor_prompt(request, state)
        logger.debug(f"📝 Supervisor 提示词已构建，长度: {len(supervisor_prompt)} 字符")

        # 调用 LLM 做决策
        logger.info("🤔 正在调用 LLM 进行决策...")
        llm = self.get_llm_client(request, disable_stream=True)
        decision_messages = [
            SystemMessage(content=supervisor_prompt),
            HumanMessage(content="请决策下一步：选择一个 Agent 执行任务，或者返回 FINISH 结束。"),
        ]

        response = llm.invoke(decision_messages)
        decision = response.content.strip()

        logger.info(f"💭 Supervisor 原始决策: {decision[:200]}{'...' if len(decision) > 200 else ''}")

        # 解析决策
        next_action = self._parse_supervisor_decision(decision, request)

        if next_action == "FINISH":
            logger.info("✅ Supervisor 决定: 任务完成，结束执行")
        else:
            logger.info(f"👉 Supervisor 决定: 委派给 [{next_action}] Agent")

        logger.info("=" * 80)

        return {"next_action": next_action, "iterations": current_iteration, "messages": [response]}  # 保留 Supervisor 的思考过程

    def _build_supervisor_prompt(self, request: SupervisorMultiAgentRequest, state: SupervisorMultiAgentState) -> str:
        """构建 Supervisor 提示词"""
        # 构建 Agent 列表描述
        agents_desc = "\n".join([f"- {agent.name}: {agent.description}" for agent in request.agents])

        # 已执行的 Agent 列表
        executed = state.get("executed_agents", [])
        executed_desc = ", ".join(executed) if executed else "无"

        # 最近的对话上下文（使用智能选择策略）
        all_messages = state.get("messages", [])
        recent_messages = self._select_context_messages(all_messages, request.supervisor_context_window_size)

        context_desc = "\n".join([f"{msg.__class__.__name__}: {msg.content[:100]}..." for msg in recent_messages])

        template_data = {
            "supervisor_system_prompt": request.supervisor_system_prompt,
            "agents_desc": agents_desc,
            "executed_desc": executed_desc,
            "context_desc": context_desc,
            "user_message": request.user_message,
        }

        return TemplateLoader.render_template("prompts/graph/supervisor_decision_prompt", template_data)

    def _parse_supervisor_decision(self, decision: str, request: SupervisorMultiAgentRequest) -> str:
        """解析 Supervisor 决策结果"""
        decision_upper = decision.upper().strip()

        # 检查是否是 FINISH
        if "FINISH" in decision_upper:
            logger.debug("🔍 决策解析: 匹配到 FINISH 关键词")
            return "FINISH"

        # 检查是否匹配某个 Agent 名称
        for agent_config in request.agents:
            if agent_config.name.upper() in decision_upper or agent_config.name in decision:
                logger.debug(f"🔍 决策解析: 匹配到 Agent [{agent_config.name}]")
                return agent_config.name

        # 默认返回第一个 Agent（降级策略）
        fallback_agent = request.agents[0].name if request.agents else "FINISH"
        logger.warning(f"⚠️  无法解析 Supervisor 决策 [{decision[:100]}]，降级选择: {fallback_agent}")
        return fallback_agent

    async def agent_executor_node(self, agent_name: str):
        """生成指定 Agent 的执行节点"""
        # 保存对 self 的引用，供内部函数使用
        node_builder = self

        async def _execute_agent(state: SupervisorMultiAgentState, config: RunnableConfig) -> Dict[str, Any]:
            """执行指定 Agent"""
            request: SupervisorMultiAgentRequest = config["configurable"]["graph_request"]

            logger.info("")
            logger.info("🤖" + "=" * 78)
            logger.info(f"🚀 开始执行 Agent: [{agent_name}]")
            logger.info("=" * 80)

            # 获取 Agent 配置
            agent_config = next((a for a in request.agents if a.name == agent_name), None)
            if not agent_config:
                logger.error(f"❌ 未找到 Agent 配置: {agent_name}")
                return {
                    "messages": [AIMessage(content=f"错误：未找到 Agent {agent_name}")],
                    "executed_agents": state.get("executed_agents", []) + [agent_name],
                }

            logger.info(f"📋 Agent 描述: {agent_config.description}")
            logger.info(f"🛠️  工具列表: {[ts.name for ts in agent_config.tools_servers]}")

            # 获取 Agent 专属的 ToolsNodes
            agent_node = node_builder.agent_tools_map.get(agent_name)
            if not agent_node:
                logger.error(f"❌ 未初始化 Agent: {agent_name}")
                return {
                    "messages": [AIMessage(content=f"错误：Agent {agent_name} 未初始化")],
                    "executed_agents": state.get("executed_agents", []) + [agent_name],
                }

            # 创建临时 StateGraph 用于 ReAct Agent
            temp_graph_builder = StateGraph(dict)

            # 构建 Agent 专属的系统提示
            agent_system_prompt = f"""
你是专业的 {agent_name} Agent。
{agent_config.description}

{agent_config.system_message_prompt}
"""

            logger.info("⚙️  正在编译 Agent 执行图...")
            # 使用可复用的 ReAct 节点构建
            # next_node=END 使 ReAct 循环结束后直接终止临时图
            react_entry_node = await agent_node.build_react_nodes(
                graph_builder=temp_graph_builder,
                composite_node_name=f"{agent_name}_react",
                additional_system_prompt=agent_system_prompt,
                next_node=END,
            )

            # 设置起始节点
            # 注意：不需要额外添加 wrapper → END 的边，因为 build_react_nodes
            # 已经通过 next_node 参数设置了 ReAct 循环结束后的去向
            temp_graph_builder.set_entry_point(react_entry_node)

            # 编译并执行
            temp_graph = temp_graph_builder.compile()

            # 确定是否使用独立上下文
            use_isolation = agent_config.context_isolation if agent_config.context_isolation is not None else request.default_context_isolation

            all_messages = state.get("messages", [])

            if use_isolation:
                # ─── 独立上下文模式 ───
                # 子 Agent 只接收任务描述，不继承共享消息历史
                # 从 Supervisor 最近的决策中提取任务上下文
                task_context = node_builder._build_isolated_task_context(all_messages, agent_name, request)
                context_messages = [HumanMessage(content=task_context)]

                logger.info(f"🔒 独立上下文模式: 构建专属任务描述 ({len(task_context)} 字符)")
            else:
                # ─── 共享上下文模式（旧行为） ───
                window_size = agent_config.context_window_size
                if window_size is None:
                    window_size = request.default_context_window_size

                context_messages = node_builder._select_context_messages(all_messages, window_size)

                logger.info(
                    f"💬 共享上下文模式: 原始 {len(all_messages)} 条 -> "
                    f"选择 {len(context_messages)} 条"
                    f"{f' (窗口: {window_size})' if window_size else ' (无限制)'}"
                )

            logger.info("▶️  开始执行 Agent 任务...")

            result = await temp_graph.ainvoke({"messages": context_messages}, config=config)

            # 获取完整的响应消息列表
            result_messages = result.get("messages", [])
            if not result_messages:
                logger.warning(f"⚠️  Agent [{agent_name}] 未返回任何消息")
                return {
                    "messages": [AIMessage(content=f"[Agent: {agent_name}]\n{agent_name} 未产生有效响应")],
                    "active_agent": agent_name,
                    "executed_agents": state.get("executed_agents", []) + [agent_name],
                }

            # 找出新增的消息（排除输入的上下文消息）
            new_messages = []
            for msg in result_messages:
                is_input_msg = False
                for ctx_msg in context_messages:
                    if msg is ctx_msg:
                        is_input_msg = True
                        break
                if not is_input_msg:
                    new_messages.append(msg)

            if not new_messages:
                logger.warning(f"⚠️  Agent [{agent_name}] 未产生新的响应")
                return {
                    "messages": [AIMessage(content=f"[Agent: {agent_name}]\n{agent_name} 未产生新的响应")],
                    "active_agent": agent_name,
                    "executed_agents": state.get("executed_agents", []) + [agent_name],
                }

            logger.info(f"✅ Agent [{agent_name}] 执行完成，产生 {len(new_messages)} 条新消息")

            if use_isolation:
                # ─── 独立上下文：只返回最终摘要给 Supervisor ───
                # 不暴露中间工具调用细节，仅返回最后一条 AIMessage 作为结果摘要
                final_summary = node_builder._extract_agent_summary(new_messages, agent_name)
                logger.info(f"🔒 独立上下文: 仅返回摘要 ({len(final_summary)} 字符) 给 Supervisor")
                logger.info("=" * 80)

                return {
                    "messages": [AIMessage(content=f"[Agent: {agent_name}]\n{final_summary}")],
                    "active_agent": agent_name,
                    "executed_agents": state.get("executed_agents", []) + [agent_name],
                }
            else:
                # ─── 共享上下文：返回全部消息（旧行为） ───
                marked_messages = []
                last_ai_msg_idx = None

                for i in range(len(new_messages) - 1, -1, -1):
                    if isinstance(new_messages[i], AIMessage):
                        last_ai_msg_idx = i
                        break

                for i, msg in enumerate(new_messages):
                    if i == last_ai_msg_idx and isinstance(msg, AIMessage) and msg.content:
                        marked_content = f"[Agent: {agent_name}]\n{msg.content}"
                        marked_messages.append(
                            AIMessage(
                                content=marked_content,
                                response_metadata=getattr(msg, "response_metadata", {}),
                                tool_calls=getattr(msg, "tool_calls", []),
                                usage_metadata=getattr(msg, "usage_metadata", None),
                            )
                        )
                    else:
                        marked_messages.append(msg)

                logger.info("=" * 80)

                return {"messages": marked_messages, "active_agent": agent_name, "executed_agents": state.get("executed_agents", []) + [agent_name]}

        return _execute_agent

    def should_continue(self, state: SupervisorMultiAgentState) -> str:
        """条件边：根据 Supervisor 决策路由到对应 Agent 或结束"""
        next_action = state.get("next_action")

        if next_action == "FINISH":
            return "FINISH"

        # 返回 Agent 名称作为路由目标
        return next_action or "FINISH"

    def _build_isolated_task_context(self, messages: List[BaseMessage], agent_name: str, request: SupervisorMultiAgentRequest) -> str:
        """
        为独立上下文的子 Agent 构建任务描述。

        从共享消息中提取用户原始请求和 Supervisor 的委派意图，
        组合成一个精简的任务描述，不包含其他 Agent 的执行细节。
        """
        # 1. 提取用户原始请求
        user_request = request.user_message or ""

        # 2. 提取 Supervisor 最近一次决策的上下文（如果有）
        supervisor_context = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                # Supervisor 的决策消息通常包含对任务的分析
                content = msg.content.strip()
                # 跳过其他 Agent 的结果摘要
                if content.startswith("[Agent:"):
                    continue
                # 找到 Supervisor 的决策/分析
                supervisor_context = content[:500]  # 限制长度
                break

        # 3. 收集已完成 Agent 的摘要（提供协作上下文）
        agent_summaries = []
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.content and msg.content.startswith("[Agent:"):
                # 只取前200字符作为摘要
                agent_summaries.append(msg.content[:200])

        # 4. 组装任务描述
        parts = [f"## 用户请求\n{user_request}"]

        if supervisor_context:
            parts.append(f"\n## Supervisor 指示\n{supervisor_context}")

        if agent_summaries:
            parts.append("\n## 其他 Agent 已完成的工作\n" + "\n".join(f"- {s}" for s in agent_summaries[-3:]))

        parts.append(f"\n## 你的任务\n请作为 {agent_name} 完成上述请求中属于你职责范围的部分。")

        return "\n".join(parts)

    def _extract_agent_summary(self, new_messages: List[BaseMessage], agent_name: str) -> str:
        """
        从子 Agent 执行结果中提取最终摘要。

        只取最后一条有内容的 AIMessage 作为结果摘要，
        丢弃中间的工具调用和工具返回消息。
        """
        # 从后向前找最后一条有内容的 AIMessage
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", []):
                return msg.content

        # 如果没有纯文本 AIMessage（所有 AIMessage 都带 tool_calls），
        # 尝试拼接最后一条 AIMessage 的内容
        for msg in reversed(new_messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content

        return f"{agent_name} 执行完成但未产生文本响应"

    def _select_context_messages(self, messages: List[BaseMessage], window_size: Optional[int] = None) -> List[BaseMessage]:
        """
        智能选择上下文消息

        策略：
        1. 如果 window_size 为 None，返回全部消息
        2. 如果消息总数 <= window_size，返回全部消息
        3. 否则，保留最近的 window_size 条消息，但尽量保证对话轮次完整性
           （即 HumanMessage 和紧随其后的 AIMessage 成对保留）

        Args:
            messages: 原始消息列表
            window_size: 窗口大小（消息数量），None 表示不限制

        Returns:
            选择后的消息列表
        """
        if not messages:
            return []

        # 不限制窗口大小
        if window_size is None:
            logger.debug("上下文窗口无限制，使用全部消息")
            return messages

        # 消息数量在限制内
        if len(messages) <= window_size:
            logger.debug(f"消息数 {len(messages)} <= 窗口 {window_size}，使用全部消息")
            return messages

        # 需要截断，但优先保持对话完整性
        selected = messages[-window_size:]

        # 如果第一条是 AIMessage，尝试向前扩展找到配对的 HumanMessage
        if selected and isinstance(selected[0], AIMessage):
            start_idx = len(messages) - window_size
            # 向前查找最近的 HumanMessage
            for i in range(start_idx - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    selected = messages[i:]
                    logger.debug(f"为保持对话完整性，向前扩展到 HumanMessage，最终选择 {len(selected)} 条消息")
                    break

        logger.debug(f"上下文截断：原始 {len(messages)} 条 -> 选择 {len(selected)} 条")
        return selected


class SupervisorMultiAgentGraph(BasicGraph):
    """Supervisor Multi-Agent 图执行器"""

    async def compile_graph(self, request: SupervisorMultiAgentRequest):
        """编译 Supervisor Multi-Agent 执行图"""

        logger.info("=" * 80)
        logger.info("🏗️  开始编译 Supervisor Multi-Agent 图")
        logger.info("=" * 80)
        logger.info(f"📌 用户任务: {request.user_message}")
        logger.info(f"🤖 Agent 数量: {len(request.agents)}")
        logger.info(f"📊 最大迭代: {request.max_iterations}")
        logger.info(f"📤 输出模式: {request.output_mode}")
        logger.info("")

        # 初始化节点构建器
        node_builder = SupervisorMultiAgentNode()

        # 初始化 Supervisor 和所有 Agent
        logger.info("🎯 初始化 Supervisor...")
        await node_builder.setup_supervisor(request)
        await node_builder.setup_agents(request)

        # 创建状态图
        logger.info("📐 构建状态图...")
        graph_builder = StateGraph(SupervisorMultiAgentState)

        # 添加基础图结构（prompt、chat_history、rag、user_message 等）
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 添加 Supervisor 节点
        graph_builder.add_node("supervisor", node_builder.supervisor_node)
        logger.info("  ✓ 添加 Supervisor 节点")

        # 添加所有 Agent 节点
        for agent_config in request.agents:
            agent_executor = await node_builder.agent_executor_node(agent_config.name)
            graph_builder.add_node(agent_config.name, agent_executor)
            logger.info(f"  ✓ 添加 Agent 节点: {agent_config.name}")

        # 连接基础图到 Supervisor
        graph_builder.add_edge(last_edge, "supervisor")
        logger.info("  ✓ 连接基础图 -> Supervisor")

        # 添加条件边：Supervisor -> Agent 或 END
        agent_routes = {agent.name: agent.name for agent in request.agents}
        agent_routes["FINISH"] = END

        graph_builder.add_conditional_edges("supervisor", node_builder.should_continue, agent_routes)
        logger.info("  ✓ 添加条件路由: Supervisor -> Agents/END")

        # 所有 Agent 执行完后返回 Supervisor
        for agent_config in request.agents:
            graph_builder.add_edge(agent_config.name, "supervisor")
            logger.info(f"  ✓ 连接 {agent_config.name} -> Supervisor")

        # 编译并返回
        compiled_graph = graph_builder.compile()

        logger.info("")
        logger.info("✅ Supervisor Multi-Agent 图编译完成")
        logger.info("=" * 80)

        return compiled_graph

    async def execute(self, request: SupervisorMultiAgentRequest) -> SupervisorMultiAgentResponse:
        """执行图并返回增强的响应"""
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request)

        # 统计 token 使用
        prompt_token = 0
        completion_token = 0

        for message in result.get("messages", []):
            if isinstance(message, AIMessage) and hasattr(message, "response_metadata"):
                token_usage = message.response_metadata.get("token_usage", {})
                prompt_token += token_usage.get("prompt_tokens", 0)
                completion_token += token_usage.get("completion_tokens", 0)

        # 根据 output_mode 处理最终消息
        final_message = self._extract_final_message(result, request.output_mode)

        return SupervisorMultiAgentResponse(
            message=final_message,
            total_tokens=prompt_token + completion_token,
            prompt_tokens=prompt_token,
            completion_tokens=completion_token,
            executed_agents=result.get("executed_agents", []),
            iterations=result.get("iterations", 0),
        )

    def _extract_final_message(self, result: Dict[str, Any], output_mode: str) -> str:
        """根据 output_mode 提取最终消息"""
        messages = result.get("messages", [])

        if not messages:
            return "未生成任何响应"

        if output_mode == "last_message":
            # 仅返回最后一个 AI 消息
            for msg in reversed(messages):
                if isinstance(msg, AIMessage):
                    return msg.content
            return "未找到有效的 AI 响应"

        elif output_mode == "full_history":
            # 返回所有 AI 消息的组合
            ai_messages = [msg.content for msg in messages if isinstance(msg, AIMessage)]
            return "\n\n---\n\n".join(ai_messages)

        return "未知的 output_mode"
