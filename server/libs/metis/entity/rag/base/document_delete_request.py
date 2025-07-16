from pydantic import BaseModel


class DocumentDeleteRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
