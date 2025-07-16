from pydantic import BaseModel


class IndexDeleteRequest(BaseModel):
    group_id: str
