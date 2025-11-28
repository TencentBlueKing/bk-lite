from typing import List
from langchain_community.document_loaders import RecursiveUrlLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain_core.documents import Document
from loguru import logger


class WebSiteLoader:
    def __init__(self, url, max_depth):
        self.url = url
        self.max_depth = max_depth

    def load(self) -> List[Document]:
        logger.info(f'加载网站: [{self.url}], 最大深度: [{self.max_depth}]')

        loader = RecursiveUrlLoader(self.url, max_depth=self.max_depth)
        web_docs = loader.load()
        transformer = BeautifulSoupTransformer()
        docs = transformer.transform_documents(web_docs)

        logger.info(f"网站加载完成, 文档数量: {len(docs)}")

        return docs
