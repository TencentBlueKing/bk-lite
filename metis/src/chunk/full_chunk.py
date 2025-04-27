from typing import List

from langchain_core.documents import Document


class FullChunk:
    def chunk(self, docs: List[Document]) -> List[Document]:
        return docs
