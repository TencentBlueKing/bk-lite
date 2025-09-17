from typing import List

from src.core.llm.entity.basic_llm_request import BasicLLMRequest
from src.core.llm.entity.tools_server import ToolsServer


class ReActAgentRequest(BasicLLMRequest):
    tools_servers: List[ToolsServer] = []
    langchain_tools: List[str] = []
    max_iterations: int = 10  # ReAct Agent 最大迭代次数
