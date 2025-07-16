from typing import TypedDict, Annotated

from langgraph.graph import add_messages

from libs.metis.entity.agent.react_agent.react_agent_request import ReActAgentRequest


class ReActAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    graph_request: ReActAgentRequest
