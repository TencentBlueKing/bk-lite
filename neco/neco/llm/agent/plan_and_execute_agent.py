import time
from typing import TypedDict, Annotated, List, Optional

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END
from langgraph.graph import StateGraph, add_messages
from neco.core.utils.template_loader import TemplateLoader
from pydantic import BaseModel, Field
from loguru import logger

from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import ToolsNodes

class PlanAndExecuteAgentResponse(BasicLLMResponse):
    pass

class PlanAndExecuteAgentRequest(BasicLLMRequest):
    pass

class PlanAndExecuteAgentState(TypedDict):
    """真正的Plan and Execute Agent状态管理"""
    messages: Annotated[List[BaseMessage], add_messages]
    graph_request: PlanAndExecuteAgentRequest
    
    # 计划相关
    original_plan: List[str]      # 原始计划
    current_plan: List[str]       # 当前剩余步骤
    
    # 执行相关
    execution_prompt: Optional[str]  # 当前步骤的执行提示
    execution_count: int              # 执行计数器
    step_history: List[str]           # 步骤执行历史，用于检测循环
    
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
        
        # 动态计划生成提示
        planning_prompt = TemplateLoader.render_template("prompts/plan_and_execute_agent/planning_prompt",{
            "user_message": user_message,
            "tools_description": self.get_tools_description()
        })

        plan_response = await self.structured_output_parser.parse_with_structured_output(
            user_message=planning_prompt,
            pydantic_class=PlanResponse
        )
        
        plan_steps = plan_response.plan.steps
        reasoning = plan_response.reasoning
        
        # 改进规划显示，让结构更清晰，显示详细计划
        plan_display = f"🎯 **执行计划已制定** ({len(plan_steps)} 个步骤)\n\n"
        plan_display += f"📝 **计划推理**: {reasoning}\n\n"
        plan_display += "📋 **执行步骤**:\n\n"
        for i, step in enumerate(plan_steps, 1):
            plan_display += f"   **{i}.** {step}\n\n"
        plan_display += f"\n\n🚀 开始执行计划...\n\n"
        
        return {
            "messages": [AIMessage(content=plan_display)],
            "original_plan": plan_steps,
            "current_plan": plan_steps,
            "execution_count": 0,
            "step_history": [],
            "final_response": None
        }

    async def executor_node(self, state: PlanAndExecuteAgentState, config: RunnableConfig):
        current_plan = state.get("current_plan", [])
        if not current_plan:
            # 没有待执行步骤，直接进入总结 - 不设置final_response，让should_continue决定
            return {**state}
        
        current_step = current_plan[0]  # 取第一个待执行步骤
        
        # 记录即将执行的步骤
        step_history = state.get("step_history", [])
        execution_count = state.get("execution_count", 0)

        execution_prompt = TemplateLoader.render_template("prompts/plan_and_execute_agent/execute_node_prompt",{
                "current_step": current_step,
                "user_message": config["configurable"]["graph_request"].user_message
            }
        )
        
        # 更新执行计数和步骤历史
        new_step_history = step_history + [current_step]
        new_execution_count = execution_count + 1
        
        # 传递执行提示给React节点使用，不添加额外的显示消息
        return {
            **state,
            "execution_prompt": execution_prompt,
            "step_history": new_step_history,
            "execution_count": new_execution_count
        }

    async def replanner_node(self, state: PlanAndExecuteAgentState, config: RunnableConfig):
        """智能重新规划节点 - 基于执行结果反思并调整剩余计划"""
        
        current_plan = state.get("current_plan", [])
        original_plan = state.get("original_plan", [])
        step_history = state.get("step_history", [])
        execution_count = state.get("execution_count", 0)
        
        if not current_plan:
            # 计划为空，只更新current_plan，不传递任何消息
            logger.debug("[replanner_node] 计划为空，准备进入总结")
            return {
                "current_plan": []
            }
        
        # 死循环检测：检查是否重复执行相同步骤
        current_step = current_plan[0]
        step_occurrences = step_history.count(current_step)
        
        # 如果同一步骤执行超过2次，强制完成任务
        if step_occurrences >= 2:
            logger.warning(f"[replanner_node] 检测到循环: 步骤 '{current_step}' 已执行 {step_occurrences} 次，强制完成任务")
            
            loop_warning = f"\n\n⚠️ **检测到重复执行模式**\n\n"
            loop_warning += f"步骤 \"{current_step}\" 已经执行了 {step_occurrences} 次，为避免无限循环，任务将被标记为完成。\n\n"
            loop_warning += "📝 **建议**: 如需继续执行，请重新定义具体的、可执行的步骤。\n\n"
            
            return {
                "messages": [AIMessage(content=loop_warning)],
                "current_plan": []
            }
        
        # 如果总执行次数超过原计划的2倍，也强制完成
        max_iterations = len(original_plan) * 2 if original_plan else 20
        if execution_count >= max_iterations:
            logger.warning(f"[replanner_node] 执行次数 ({execution_count}) 超过限制 ({max_iterations})，强制完成任务")
            
            limit_warning = f"\n\n⚠️ **执行次数超限**\n\n"
            limit_warning += f"已执行 {execution_count} 个步骤，超过预期的 {max_iterations} 步，任务将被标记为完成。\n\n"
            
            return {
                "messages": [AIMessage(content=limit_warning)],
                "current_plan": []
            }
        
        # 计算执行进度 - 正确计算已完成步骤数
        total_steps = len(original_plan) if original_plan else 1
        completed_count = total_steps - len(current_plan) + 1  # +1 表示刚完成了一步
        
        # 准备模板变量 - 只获取最近的非重复消息内容
        messages = state.get("messages", [])
        recent_messages = []
        seen_contents = set()
        
        # 从后往前遍历，避免重复内容
        for msg in reversed(messages[-5:]):  # 只看最近5条消息
            if hasattr(msg, 'content') and msg.content:
                content = msg.content.strip()
                if content and content not in seen_contents:
                    recent_messages.insert(0, content)  # 保持时间顺序
                    seen_contents.add(content)
        
        # 使用模板构建智能重新规划提示
        replan_prompt = TemplateLoader.render_template("prompts/plan_and_execute_agent/replan_prompt",{
            "user_message": config["configurable"]["graph_request"].user_message,
            "original_plan": original_plan,
            "current_plan": current_plan,
            "recent_messages": recent_messages,
            "step_history": step_history,
            "execution_count": execution_count
        })

        replan_response = await self.structured_output_parser.parse_with_structured_output(
            user_message=replan_prompt,
            pydantic_class=ReplanResponse
        )
        
        updated_steps = replan_response.updated_plan.steps
        reasoning = replan_response.reasoning
        is_complete = replan_response.is_complete

        logger.debug(f"[replanner_node] 重新规划结果: is_complete={is_complete}, updated_steps={len(updated_steps)}")

        if is_complete or not updated_steps:
            # 任务完成 - 清空current_plan，不添加任何消息
            logger.debug("[replanner_node] 任务完成，清空计划")
            return {
                "current_plan": []
            }
        else:
            # 还有剩余步骤，继续执行
            logger.debug(f"[replanner_node] 还有 {len(updated_steps)} 个步骤待执行")
            
            # 只有当步骤发生实际变化时才显示进度信息
            expected_remaining = current_plan[1:] if len(current_plan) > 1 else []
            
            if updated_steps != expected_remaining:
                # 计划发生了调整，显示调整信息
                progress_display = f"\n\n📊 **步骤 {completed_count}/{total_steps} 完成**\n\n"
                progress_display += f"\n\n🔄 **计划已调整**: {reasoning}\n\n"
                progress_display += f"\n\n📋 **剩余步骤**:\n\n"
                for i, step in enumerate(updated_steps, 1):
                    progress_display += f"   **{i}.** {step}\n\n"
                progress_display += f"\n\n"
                
                return {
                    "messages": [AIMessage(content=progress_display)],
                    "current_plan": updated_steps
                }
            else:
                # 计划没有变化，静默更新状态，不添加消息
                return {
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
        
        logger.debug("[summary_node] 开始生成最终总结")
        
        # 获取原始用户问题和执行计划
        user_message = config["configurable"]["graph_request"].user_message
        original_plan = state.get("original_plan", [])
        total_steps = len(original_plan)
        
        # 收集整个执行过程的消息历史，去重处理
        messages = state.get("messages", [])
        execution_history = []
        seen_contents = set()
        
        # 整理执行历史，过滤重复内容
        for message in messages:
            if hasattr(message, 'content') and message.content:
                content = message.content.strip()
                # 过滤掉空内容、重复内容以及包含"最终结果"的内容（避免嵌套）
                if (content and 
                    content not in seen_contents and 
                    "🎯 **最终结果**" not in content):
                    execution_history.append(f"- {content}")
                    seen_contents.add(content)
        
        # 使用模板构建总结提示
        summary_prompt = TemplateLoader.render_template("prompts/plan_and_execute_agent/summary_prompt",{
            "user_message": user_message,
            "total_steps": total_steps,
            "original_plan": original_plan,
            "execution_history": execution_history
        })

        # 使用LLM生成智能总结
        summary_response = await self.llm.ainvoke([
            HumanMessage(content=summary_prompt)
        ])

        # 格式化最终总结显示
        formatted_summary = f"\n\n🎯 **最终结果**\n\n{summary_response.content}\n\n"
        
        logger.debug("[summary_node] 总结生成完成")
        
        return {
            "messages": [AIMessage(content=formatted_summary)],
            "final_response": formatted_summary
        }

class PlanAndExecuteAgentGraph(BasicGraph):
    """Plan and Execute Agent - 智能计划生成与执行系统"""

    async def compile_graph(self, request: PlanAndExecuteAgentRequest):
        """编译工作流图"""
        node_builder = PlanAndExecuteAgentNode()
        await node_builder.setup(request)

        graph_builder = StateGraph(PlanAndExecuteAgentState)
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 添加核心节点
        graph_builder.add_node("planner", node_builder.planner_node)
        graph_builder.add_node("executor", node_builder.executor_node)  
        graph_builder.add_node("replanner", node_builder.replanner_node)
        graph_builder.add_node("summary", node_builder.summary_node)
        
        # 使用现有的ReAct节点构建方法
        react_entry_node = await node_builder.build_react_nodes(
            graph_builder=graph_builder,
            composite_node_name="react_step_executor", 
            additional_system_prompt="你是任务执行助手，专注完成用户最新消息中的具体步骤。请使用合适的工具完成任务，并简洁地提供结果。",
        )

        # 设置图边缘 - 实现 Plan -> Execute -> Replan -> Execute 循环
        graph_builder.add_edge(last_edge, "planner")                    # 开始 -> 计划
        graph_builder.add_edge("planner", "executor")                   # 计划 -> 准备执行
        graph_builder.add_edge("executor", "react_step_executor_wrapper")     # 准备执行 -> 步骤包装
        graph_builder.add_edge("react_step_executor_wrapper", "replanner")  # 步骤包装 -> 重新规划
        
        graph_builder.add_conditional_edges(
            "replanner",
            node_builder.should_continue,
            {
                "executor": "executor",   # 继续执行下一步
                "summary": "summary"      # 任务完成，生成总结
            }
        )
        
        graph_builder.add_edge("summary", END)

        graph = graph_builder.compile()
        return graph