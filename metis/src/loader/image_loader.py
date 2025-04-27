from langchain_core.documents import Document
from loguru import logger

from src.ocr.base_ocr import BaseOCR


class ImageLoader:
    def __init__(self, path, ocr: BaseOCR, load_mode='full'):
        self.path = path
        self.ocr = ocr
        self.load_mode = load_mode

    def load(self):
        logger.info(f"解析图片: {self.path}")
        docs = []
        result = self.ocr.predict(self.path)
        doc = Document(page_content=result, metadata={"format": "image"})
        docs.append(doc)
        return docs
