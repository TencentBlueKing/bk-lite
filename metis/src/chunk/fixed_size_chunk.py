from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


class FixedSizeChunk:
    def __init__(self, chunk_size: int = 500):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=0,
            length_function=len,
            is_separator_regex=False,
        )

    def chunk(self, docs: List[Document]) -> List[Document]:
        split_docs = self.text_splitter.split_documents(docs)
        return split_docs
