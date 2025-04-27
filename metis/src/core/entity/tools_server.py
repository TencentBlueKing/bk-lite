from pydantic import BaseModel


class ToolsServer(BaseModel):
    name: str
    url: str
