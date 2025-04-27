from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class RecursiveChunk:
    def __init__(self, chunk_size: int = 500, chunk_overlap=128):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    def chunk(self, docs: List[Document]) -> List[Document]:
        split_docs = self.text_splitter.split_documents(docs)
        return split_docs
