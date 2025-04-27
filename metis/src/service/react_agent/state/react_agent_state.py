from typing import TypedDict, Annotated

from langgraph.graph import add_messages

from src.service.react_agent.entity.react_agent_request import ReActAgentRequest


class ReActAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    graph_request: ReActAgentRequest
    agent_scratchpad: str
