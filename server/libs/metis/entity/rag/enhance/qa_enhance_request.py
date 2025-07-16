from pydantic import BaseModel


class QAEnhanceRequest(BaseModel):
    size: int
    content: str

    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'
