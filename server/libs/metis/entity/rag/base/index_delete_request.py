from pydantic import BaseModel


class IndexDeleteRequest(BaseModel):
    index_name: str
