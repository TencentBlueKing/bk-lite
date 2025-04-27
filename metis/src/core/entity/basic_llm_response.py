from pydantic import BaseModel


class BasicLLMResponse(BaseModel):
    message: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
