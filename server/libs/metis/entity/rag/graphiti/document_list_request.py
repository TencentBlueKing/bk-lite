from pydantic import BaseModel


class DocumentListRequest(BaseModel):
    group_id: str
