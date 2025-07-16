from pydantic import BaseModel


class MetisEmbedderConfig(BaseModel):
    url: str
    model_name: str
    api_key: str = ''
