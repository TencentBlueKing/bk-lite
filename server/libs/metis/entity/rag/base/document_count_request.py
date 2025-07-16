from pydantic import BaseModel


class DocumentCountRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
    query: str