from typing import List
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader


class RawLoader(BaseLoader):
    def __init__(self, content: str):
        self.content = content

    def load(self) -> List[Document]:
        doc: List[Document] = []
        doc.append(Document(page_content=self.content))
        return doc
