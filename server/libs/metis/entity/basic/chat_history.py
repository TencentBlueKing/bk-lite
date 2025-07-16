from typing import List

from pydantic import BaseModel


class ChatHistory(BaseModel):
    event: str
    message: str
    image_data: List[str] = []