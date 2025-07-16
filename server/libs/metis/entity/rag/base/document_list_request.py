from pydantic import BaseModel


class DocumentListRequest(BaseModel):
    index_name: str
    page: int
    size: int
    metadata_filter: dict
    query: str
