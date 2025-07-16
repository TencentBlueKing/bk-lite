from typing import List

from libs.metis.entity.basic.basic_llm_request import BasicLLMRequest
from libs.metis.entity.basic.tools_server import ToolsServer



class ReActAgentRequest(BasicLLMRequest):
    tools_servers: List[ToolsServer] = []
    langchain_tools: List[str] = []
