from typing import List

from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader
from loguru import logger


class TextLoader(BaseLoader):
    def __init__(self, path, load_mode='full'):
        self.path = path
        self.load_mode = load_mode

    def load(self) -> List[Document]:
        logger.info(f"解析TXT文件[{self.path}]")

        docs: List[Document] = []

        with open(self.path, 'r', encoding="utf-8") as f:
            if self.load_mode == "full":
                full_text = f.read()
                docs.append(Document(full_text))

        return docs
