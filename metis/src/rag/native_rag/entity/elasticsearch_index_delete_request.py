from pydantic import BaseModel


class ElasticSearchIndexDeleteRequest(BaseModel):
    index_name: str
