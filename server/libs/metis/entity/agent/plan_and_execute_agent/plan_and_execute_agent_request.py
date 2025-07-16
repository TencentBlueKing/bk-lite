import operator
from typing import List, Annotated, Tuple

from libs.metis.entity.basic.basic_llm_request import BasicLLMRequest
from libs.metis.entity.basic.tools_server import ToolsServer
from pydantic import Field


class PlanAndExecuteAgentRequest(BasicLLMRequest):
    tools_servers: List[ToolsServer] = []
    langchain_tools: List[str] = []
