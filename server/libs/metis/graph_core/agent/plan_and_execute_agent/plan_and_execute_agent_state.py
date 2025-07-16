import operator
from typing import TypedDict, Annotated, List, Tuple, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import Field

from libs.metis.entity.agent.plan_and_execute_agent.plan_and_execute_agent_request import PlanAndExecuteAgentRequest


class PlanAndExecuteAgentState(TypedDict):
    """状态对象，用于Plan and Execute Agent的状态管理

    属性:
        messages: 消息历史，使用add_messages注解保证正确添加消息
        graph_request: 图请求对象
        plan: 排序的步骤列表
        past_steps: 已执行步骤的历史记录，包含步骤描述和执行结果
        current_step_index: 当前执行的步骤索引
        response: 最终响应
    """
    messages: Annotated[List[BaseMessage], add_messages]
    graph_request: PlanAndExecuteAgentRequest
    plan: List[str] = Field(
        description="different steps to follow, should be in sorted order"
    )
    past_steps: Annotated[List[Tuple[str, str]], operator.add]
    current_step_index: int = 0
    response: Optional[str] = None
