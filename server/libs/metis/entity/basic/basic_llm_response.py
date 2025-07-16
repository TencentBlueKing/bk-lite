from pydantic import BaseModel


class BasicLLMResponse(BaseModel):
    message: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
