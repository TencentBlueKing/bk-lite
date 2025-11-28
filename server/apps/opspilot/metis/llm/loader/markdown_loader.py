from typing import List
from langchain_core.documents import Document
from loguru import logger


class MarkdownLoader:
    def __init__(self, path: str, load_mode='full'):
        self.path = path
        self.load_mode = load_mode

    def load(self) -> List[Document]:
        logger.info(f"解析MarkDown文件: {self.path}")
        docs: List[Document] = []
        with open(self.path, 'r', encoding='utf-8') as file:
            content = file.read()
            docs.append(Document(content))
        return docs
