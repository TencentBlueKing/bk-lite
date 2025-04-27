from pydantic import BaseModel


class ElasticSearchDocumentCountRequest(BaseModel):
    index_name: str
    metadata_filter: dict = {}
    query: str