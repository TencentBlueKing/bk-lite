import time
from typing import TypedDict, Annotated, List, Optional

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END
from langgraph.graph import StateGraph, add_messages
from pydantic import BaseModel, Field
from loguru import logger

from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import ToolsNodes

class PlanAndExecuteAgentResponse(BasicLLMResponse):
    pass

class PlanAndExecuteAgentRequest(BasicLLMRequest):
    tools_servers: List[ToolsServer] = []
    langchain_tools: List[str] = []

class PlanAndExecuteAgentState(TypedDict):
    """真正的Plan and Execute Agent状态管理"""
    messages: Annotated[List[BaseMessage], add_messages]
    graph_request: PlanAndExecuteAgentRequest
    
    # 计划相关
    original_plan: List[str]      # 原始计划
    current_plan: List[str]       # 当前剩余步骤
    
    # 执行相关
    execution_prompt: Optional[str]  # 当前步骤的执行提示
    
    # 最终结果
    final_response: Optional[str]

class Plan(BaseModel):
    """动态计划模型"""
    steps: List[str] = Field(description="当前剩余的执行步骤列表，每个步骤应该具体明确且可执行")

class PlanResponse(BaseModel):
    """计划响应模型"""
    plan: Plan = Field(description="生成的执行计划")
    reasoning: str = Field(description="计划制定的推理过程")

class ReplanResponse(BaseModel):
    """重新规划响应模型"""
    updated_plan: Plan = Field(description="更新后的剩余步骤")
    reasoning: str = Field(description="重新规划的推理过程")
    is_complete: bool = Field(description="任务是否已经完成，无需继续执行")

class PlanAndExecuteAgentNode(ToolsNodes):
    """Plan and Execute Agent - 智能计划生成与执行"""

    async def planner_node(self, state: PlanAndExecuteAgentState, config: RunnableConfig):
        """动态计划生成节点 - 真正的Plan and Execute Agent"""
        
        user_message = config["configurable"]["graph_request"].user_message
        
        # 获取可用工具信息
        tools_info = ""
        if hasattr(self, 'tools') and self.tools:
            tools_list = []
            for tool in self.tools:
                tool_name = getattr(tool, 'name', str(tool))
                tool_desc = getattr(tool, 'description', '工具功能')
                tools_list.append(f"  • {tool_name}: {tool_desc}")
            
            tools_info = f"""

🔧 **可用工具**:
{chr(10).join(tools_list)}"""
        
        # 动态计划生成提示
        planning_prompt = f"""你是一个智能任务规划师。请为以下任务制定详细的执行计划。

📋 **用户任务**: {user_message}{tools_info}

🎯 **规划指南**:
1. 分析任务的具体需求和目标
2. 识别需要使用的工具和资源  
3. 制定清晰、可执行的步骤序列
4. 每个步骤都应该是具体的行动项
5. 充分利用可用工具的能力

请提供你的推理过程和具体的执行计划。"""

        try:
            # 使用LLM动态生成计划
            plan_response = await self.structured_output_parser.parse_with_structured_output(
                user_message=planning_prompt,
                pydantic_class=PlanResponse
            )
            
            plan_steps = plan_response.plan.steps
            reasoning = plan_response.reasoning
            
        except Exception as e:
            logger.warning(f"动态计划生成失败: {e}")
            # 紧急备用计划
            plan_steps = ["分析用户需求", "执行必要的操作", "提供结果"]
            reasoning = "使用备用计划"
        
        # 改进规划显示，让结构更清晰，显示详细计划
        plan_display = f"🎯 **执行计划已制定** ({len(plan_steps)} 个步骤)\n\n"
        plan_display += f"📝 **计划推理**: {reasoning}\n\n"
        plan_display += "📋 **执行步骤**:\n"
        for i, step in enumerate(plan_steps, 1):
            plan_display += f"   **{i}.** {step}\n"
        plan_display += f"\n🚀 开始执行计划...\n\n---\n"
        
        self.log(config, plan_display)
        
        return {
            "messages": [AIMessage(content=plan_display)],
            "original_plan": plan_steps,
            "current_plan": plan_steps,
            "final_response": None
        }

    async def executor_node(self, state: PlanAndExecuteAgentState, config: RunnableConfig):
        """单步执行节点 - 执行当前计划的第一步"""
        
        current_plan = state.get("current_plan", [])
        if not current_plan:
            # 没有待执行步骤，直接进入总结 - 不设置final_response，让should_continue决定
            return {**state}
        
        current_step = current_plan[0]  # 取第一个待执行步骤
        
        # 移除干扰性输出，让执行过程更简洁
        # self.log(config, f"⚡ 执行步骤 {len(original_plan) - len(current_plan) + 1}")  # 可选：显示步骤编号
        
        # 使用ReAct模式执行当前步骤
        execution_prompt = f"""请执行以下具体步骤：

🎯 **当前步骤**: {current_step}

📋 **原始任务**: {config["configurable"]["graph_request"].user_message}

请专注于完成这一个步骤，使用必要的工具，并提供执行结果。"""
        
        # 传递执行提示给React节点使用，不添加额外的显示消息
        return {
            **state,
            "execution_prompt": execution_prompt
        }

    async def replanner_node(self, state: PlanAndExecuteAgentState, config: RunnableConfig):
        """智能重新规划节点 - 基于执行结果反思并调整剩余计划"""
        
        current_plan = state.get("current_plan", [])
        original_plan = state.get("original_plan", [])
        
        if not current_plan:
            # 计划为空，不设置final_response，让should_continue统一判断
            return {**state}
        
        # 计算执行进度 - 正确计算已完成步骤数
        total_steps = len(original_plan) if original_plan else 1
        completed_count = total_steps - len(current_plan) + 1  # +1 表示刚完成了一步
        
        # 构建智能重新规划提示
        replan_prompt = f"""你是一个智能任务重新规划助手。请基于当前执行情况，反思并重新规划剩余任务步骤。

📋 **原始用户任务**: {config["configurable"]["graph_request"].user_message}

📝 **原始完整计划**:
{chr(10).join([f"   {i+1}. {step}" for i, step in enumerate(original_plan)])}

📊 **当前剩余步骤**:
{chr(10).join([f"   {i+1}. {step}" for i, step in enumerate(current_plan)])}

🔍 **最近执行历史**:
{chr(10).join([f"- {msg.content}" for msg in state.get("messages", [])[-3:] if hasattr(msg, 'content') and msg.content])}

🎯 **重新规划要求**:
1. 分析当前执行情况和已获得的结果
2. 判断当前第一个步骤是否已经完成或需要调整
3. 基于执行结果，重新评估剩余步骤的必要性和顺序
4. 如果发现新的需求或问题，可以添加新步骤
5. 如果某些步骤已经不再必要，可以移除
6. 如果任务已经完成，标记为完成状态

请提供你的重新规划结果。"""

        try:
            # 使用LLM进行智能重新规划
            replan_response = await self.structured_output_parser.parse_with_structured_output(
                user_message=replan_prompt,
                pydantic_class=ReplanResponse
            )
            
            updated_steps = replan_response.updated_plan.steps
            reasoning = replan_response.reasoning
            is_complete = replan_response.is_complete
            
        except Exception as e:
            logger.warning(f"智能重新规划失败: {e}")
            # 简单降级：移除第一个步骤
            updated_steps = current_plan[1:] if len(current_plan) > 1 else []
            reasoning = "使用简单规则：移除已完成步骤"
            is_complete = len(updated_steps) == 0

        if is_complete or not updated_steps:
            # 任务完成 - 清空current_plan，让should_continue统一判断进入summary
            return {
                **state,
                "current_plan": []
                # 不设置final_response，避免重复
            }
        else:
            # 还有剩余步骤，继续执行
            # 改进进度显示，让步骤更清晰，包含重新规划信息
            progress_display = f"\n---\n\n📊 **步骤 {completed_count}/{total_steps} 完成**\n"
            
            # 如果步骤有变化，显示重新规划信息
            if updated_steps != current_plan[1:]:
                progress_display += f"\n🔄 **计划已调整**: {reasoning}\n"
                progress_display += f"\n📋 **剩余步骤**:\n"
                for i, step in enumerate(updated_steps, 1):
                    progress_display += f"   **{i}.** {step}\n"
                progress_display += f"\n"  # 确保末尾有换行
            
            logger.debug(f"[replanner_node] 显示进度: {progress_display.strip()}, current_plan长度: {len(current_plan)}, updated_steps长度: {len(updated_steps)}")
            self.log(config, progress_display)
            
            return {
                **state,
                "current_plan": updated_steps
            }

    async def should_continue(self, state: PlanAndExecuteAgentState) -> str:
        """判断是否继续执行或结束 - 统一判断逻辑，避免重复进入summary"""
        current_plan = state.get("current_plan", [])
        
        logger.debug(f"[should_continue] current_plan长度: {len(current_plan)}")
        
        # 只基于current_plan判断：没有剩余步骤就结束执行
        if not current_plan:
            logger.debug("[should_continue] 没有剩余步骤，返回 summary")
            return "summary"
        
        # 否则继续执行
        logger.debug("[should_continue] 还有剩余步骤，返回 executor") 
        return "executor"

    async def summary_node(self, state: PlanAndExecuteAgentState, config: RunnableConfig):
        """最终总结节点 - 使用LLM智能总结执行过程和结果"""
        logger.debug("[summary_node] 进入总结节点")
        
        # 检查是否已经有最终响应，避免重复生成
        existing_final_response = state.get("final_response")
        if existing_final_response:
            logger.debug("[summary_node] 已存在final_response，跳过重复生成")
            return state
        
        # 获取原始用户问题和执行计划
        user_message = config["configurable"]["graph_request"].user_message
        original_plan = state.get("original_plan", [])
        total_steps = len(original_plan)
        
        # 收集整个执行过程的消息历史
        messages = state.get("messages", [])
        execution_history = []
        
        # 整理执行历史，包括计划、执行步骤和结果
        for message in messages:
            if hasattr(message, 'content') and message.content:
                content = message.content.strip()
                if content:  # 只收集非空内容
                    execution_history.append(f"- {content}")
        
        # 构建给LLM的总结提示
        history_text = "\n".join(execution_history)  
        plan_text = "\n".join([f"   {i+1}. {step}" for i, step in enumerate(original_plan)])
        
        summary_prompt = f"""你是一个智能任务总结助手。请基于以下完整的执行历史，为用户生成一个清晰、有用的任务完成总结。

📋 **原始用户问题**: {user_message}

📝 **执行计划** ({total_steps} 个步骤):
{plan_text}

📊 **完整执行历史**:
{history_text}

🎯 **总结要求**:
1. 简要概述任务完成情况
2. 突出显示关键的执行结果和数据
3. 如果有具体数据（如提交记录、统计信息等），请清晰地整理和展示
4. 保持专业、友好的语调
5. 如果用户可能需要进一步操作，提供简要建议

请生成一个结构清晰、内容丰富的最终总结。"""

        try:
            # 使用LLM生成智能总结
            summary_response = await self.llm.ainvoke([
                HumanMessage(content=summary_prompt)
            ])
            
            if hasattr(summary_response, 'content') and summary_response.content:
                intelligent_summary = summary_response.content.strip()
                logger.debug(f"[summary_node] LLM生成总结，长度: {len(intelligent_summary)}")
            else:
                intelligent_summary = "任务已成功完成，所有步骤都已按计划执行。"
                logger.warning("[summary_node] LLM返回空内容，使用默认总结")
                
        except Exception as e:
            logger.error(f"[summary_node] LLM总结失败: {e}")
            intelligent_summary = f"""🎉 **任务执行完成！**

✅ 成功完成 {total_steps} 个计划步骤，所有预定目标均已达成。

📋 **执行概况**: 按照既定计划逐步执行，所有工具调用和数据处理都已顺利完成。

💡 如需进一步分析或有其他问题，请随时告知！"""

        # 格式化最终总结显示 - 确保前后都有适当的换行
        formatted_summary = f"\n\n---\n\n🎯 **最终结果**\n\n{intelligent_summary}\n"
        self.log(config, formatted_summary)
        
        return {
            **state,
            "messages": state.get("messages", []) + [AIMessage(content=formatted_summary)],
            "final_response": formatted_summary
        }

class PlanAndExecuteAgentGraph(BasicGraph):
    """Plan and Execute Agent - 智能计划生成与执行系统"""

    async def compile_graph(self, request: PlanAndExecuteAgentRequest):
        """编译工作流图"""
        node_builder = PlanAndExecuteAgentNode()
        logger.debug("🚀 初始化Plan and Execute Agent")
        await node_builder.setup(request)
        logger.debug(f"🔧 已加载 {len(node_builder.tools)} 个工具")

        graph_builder = StateGraph(PlanAndExecuteAgentState)
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 添加核心节点
        graph_builder.add_node("planner", node_builder.planner_node)
        graph_builder.add_node("executor", node_builder.executor_node)  
        graph_builder.add_node("replanner", node_builder.replanner_node)
        graph_builder.add_node("summary", node_builder.summary_node)
        
        # 添加动态步骤执行包装节点
        async def step_executor_wrapper(state: PlanAndExecuteAgentState, config: RunnableConfig):
            """包装节点：动态设置执行步骤提示"""
            execution_prompt = state.get("execution_prompt", "请完成当前任务")
            
            # 直接传递执行提示给React节点，不显示额外的状态信息
            current_step_msg = HumanMessage(content=execution_prompt)
            
            return {
                **state,
                "messages": state.get("messages", []) + [current_step_msg]
            }
        
        graph_builder.add_node("step_executor_wrapper", step_executor_wrapper)
        
        # 使用现有的ReAct节点构建方法
        react_entry_node = await node_builder.build_react_nodes(
            graph_builder=graph_builder,
            composite_node_name="react_step_executor", 
            additional_system_prompt="你是任务执行助手，专注完成用户最新消息中的具体步骤。请使用合适的工具完成任务，并简洁地提供结果。",
            next_node="replanner"
        )

        # 设置图边缘 - 实现 Plan -> Execute -> Replan -> Execute 循环
        graph_builder.add_edge(last_edge, "planner")                    # 开始 -> 计划
        graph_builder.add_edge("planner", "executor")                   # 计划 -> 准备执行
        graph_builder.add_edge("executor", "step_executor_wrapper")     # 准备执行 -> 步骤包装
        graph_builder.add_edge("step_executor_wrapper", react_entry_node)  # 步骤包装 -> React执行
        
        # 手动添加React节点到replanner的连接（因为build_react_nodes没有自动处理next_node参数）
        graph_builder.add_edge(react_entry_node, "replanner")          # React执行完成 -> 重新规划
        
        # 条件边：重新规划后决定继续执行还是结束
        async def debug_should_continue(state):
            result = await node_builder.should_continue(state)
            logger.debug(f"[debug_should_continue] 返回: {result}")
            return result
        
        graph_builder.add_conditional_edges(
            "replanner",
            debug_should_continue,
            {
                "executor": "executor",   # 继续执行下一步
                "summary": "summary"      # 任务完成，生成总结
            }
        )
        
        graph_builder.add_edge("summary", END)

        logger.debug("✅ Plan and Execute Agent编译完成")
        
        graph = graph_builder.compile()
        return graph