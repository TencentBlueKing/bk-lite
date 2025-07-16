from pydantic import BaseModel


class SummarizeEnhanceRequest(BaseModel):
    content: str

    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'

