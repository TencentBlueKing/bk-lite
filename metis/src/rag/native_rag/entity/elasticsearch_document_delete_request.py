from pydantic import BaseModel


class ElasticSearchDocumentDeleteRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
