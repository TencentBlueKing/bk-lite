from pydantic import BaseModel


class ElasticSearchDocumentListRequest(BaseModel):
    """
    Request model for ElasticSearch document list.
    """

    index_name: str
    page: int
    size: int
    metadata_filter: dict
    query: str
