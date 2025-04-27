from typing import List

from src.core.entity.basic_llm_request import BasicLLMReuqest
from src.core.entity.tools_server import ToolsServer


class ReActAgentRequest(BasicLLMReuqest):
    tools_servers: List[ToolsServer] = []
    langchain_tools:List[str] = []