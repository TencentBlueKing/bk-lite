from typing import List, Optional

from pydantic import BaseModel

from src.core.entity import ChatHistory, MCPServers
from src.rag.naive_rag.entity import ElasticSearchRetrieverRequest


class ToolsAgentResponse(BaseModel):
    message: str
    total_tokens: int


class ToolsAgentRequest(BaseModel):
    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'

    system_message_prompt: str = ''
    temperature: float = 0.7

    user_message: str = ''

    chat_history: List[ChatHistory] = []

    user_id: Optional[str] = ''
    thread_id: Optional[str] = ''

    enable_naive_rag: bool = False
    naive_rag_request: Optional[ElasticSearchRetrieverRequest] = None

    mcp_servers: List[MCPServers] = []
