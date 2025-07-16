from typing import List
from pydantic import BaseModel


class DocumentDeleteRequest(BaseModel):
    uuids: List[str] = []
