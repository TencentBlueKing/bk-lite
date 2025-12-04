from pydantic import BaseModel


class AnswerGenerateRequest(BaseModel):
    context: str
    content: str

    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'

    extra_prompt: str = ''

class QAEnhanceRequest(BaseModel):
    content: str

    size: int
    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'

    extra_prompt: str = ''

class QuestionGenerateRequest(BaseModel):
    content: str

    size: int
    openai_api_base: str = 'https://api.openai.com'
    openai_api_key: str = ''
    model: str = 'gpt-4o'

    extra_prompt: str = ''
    