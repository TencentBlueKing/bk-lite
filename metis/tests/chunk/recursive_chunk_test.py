import os

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from loguru import logger

from src.chunk.recursive_chunk import RecursiveChunk
from src.chunk.semantic_chunk import SemanticChunk
from src.loader.text_loader import TextLoader


def test_recursive_chunk():
    chunk = RecursiveChunk()
    loader = TextLoader(path='./tests/assert/full_text_loader.txt')
    docs = loader.load()
    rs = chunk.chunk(docs)
    logger.info(rs)
