from typing import List

from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings


class SemanticChunk:
    def __init__(self, semantic_embedding_model: OpenAIEmbeddings):
        self.semantic_embedding_model = semantic_embedding_model
        self.semantic_chunker = SemanticChunker(embeddings=semantic_embedding_model,
                                                sentence_split_regex=r'(?<=[.?!。？！])\s*')

    def chunk(self, docs: List[Document]) -> List[Document]:
        docs = self.semantic_chunker.split_documents(docs)
        return docs
