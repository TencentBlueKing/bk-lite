from pydantic import BaseModel


class DocumentMetadataUpdateRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
    metadata: dict = {}
