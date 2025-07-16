import uuid
from collections import defaultdict
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

        # 2. 按照 segment_number 分组
        grouped_docs = defaultdict(list)
        for doc in split_docs:
            segment_number = doc.metadata.get('segment_number', 0)
            grouped_docs[segment_number].append(doc)

        # 3. 为每个组内的文档添加 chunk_number
        result_docs = []
        for segment_number, segment_docs in grouped_docs.items():
            for chunk_number, doc in enumerate(segment_docs):
                doc.metadata['chunk_number'] = str(chunk_number)
                doc.metadata['chunk_id'] = str(uuid.uuid4())
                result_docs.append(doc)

        return split_docs
