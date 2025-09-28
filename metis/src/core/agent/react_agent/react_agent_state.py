from typing import TypedDict, Annotated, Optional

from langgraph.graph import add_messages

from src.web.entity.agent.react_agent.react_agent_request import ReActAgentRequest


class ReActAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    graph_request: ReActAgentRequest
    react_iteration: Optional[int]  # ReAct Agent 迭代计数
