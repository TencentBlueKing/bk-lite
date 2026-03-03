from typing import List, Optional

from pydantic import BaseModel

from apps.opspilot.metis.llm.rag.naive_rag_entity import DocumentRetrieverRequest


class BasicLLMResponse(BaseModel):
    message: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    browser_steps: List[str] = []  # browser_use 步骤信息，格式: ["step1 xxx", "step2 xxx", ..., "最终结果: xxx"]


class ChatHistory(BaseModel):
    event: str
    message: str
    image_data: List[str] = []


class ToolsServer(BaseModel):
    name: str
    url: str = ""
    transport: str = ""
    command: str = ""
    args: list = []
    extra_param_prompt: dict = {}
    extra_tools_prompt: str = ""
    enable_auth: bool = False
    auth_token: str = ""


class BasicLLMRequest(BaseModel):
    openai_api_base: str = "https://api.openai.com"
    openai_api_key: str = ""
    model: str = "gpt-4o"

    system_message_prompt: str = ""
    enable_suggest: bool = False
    enable_query_rewrite: bool = False
    temperature: float = 0.7

    user_message: str = ""

    chat_history: List[ChatHistory] = []

    user_id: Optional[str] = ""
    thread_id: Optional[str] = ""

    naive_rag_request: List[DocumentRetrieverRequest] = []

    extra_config: Optional[dict] = {}

    graph_user_message: Optional[str] = ""

    tools_servers: List[ToolsServer] = []

    locale: str = "en"  # 用户语言设置，用于 browser-use 输出国际化
