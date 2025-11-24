import base64

from langchain_core.documents import Document
from loguru import logger

from neco.ocr.base_ocr import BaseOCR


class ImageLoader:
    def __init__(self, path, ocr: BaseOCR, load_mode='full'):
        self.path = path
        self.ocr = ocr
        self.load_mode = load_mode

    def load(self):
        logger.info(f"解析图片: {self.path}")
        docs = []
        result = self.ocr.predict(self.path)

        with open(self.path, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode('utf-8')

        doc = Document(page_content=result, metadata={
                       "format": "image", "image_base64": image_base64})
        docs.append(doc)
        return docs
