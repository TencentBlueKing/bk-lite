from pydantic import BaseModel


class MetisRerankerConfig(BaseModel):
    url: str
    model_name: str
    api_key: str = ''
