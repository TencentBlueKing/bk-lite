from pydantic import BaseModel


class ElasticsearchDocumentMetadataUpdateRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
    metadata: dict = {}
