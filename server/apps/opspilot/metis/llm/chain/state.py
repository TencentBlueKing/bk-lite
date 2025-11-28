from typing import TypedDict, Annotated

from langgraph.graph import add_messages


class BasicState(TypedDict):
    messages: Annotated[list, add_messages]
