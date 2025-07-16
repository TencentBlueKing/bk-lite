from typing import List, Optional

from libs.metis.entity.basic.chat_history import ChatHistory
from libs.metis.entity.rag.base.document_retriever_request import DocumentRetrieverRequest
from pydantic import BaseModel



class BasicLLMRequest(BaseModel):
    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'

    system_message_prompt: str = ''
    temperature: float = 0.7

    user_message: str = ''

    chat_history: List[ChatHistory] = []

    user_id: Optional[str] = ''
    thread_id: Optional[str] = ''

    naive_rag_request: List[DocumentRetrieverRequest] = []

    extra_config: Optional[dict] = {}
