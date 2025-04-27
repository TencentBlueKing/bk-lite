from dotenv import load_dotenv
from loguru import logger

from src.chunk.fixed_size_chunk import FixedSizeChunk
from src.loader.text_loader import TextLoader


def test_fixed_size_chunk():
    chunk = FixedSizeChunk()
    loader = TextLoader(path='./tests/assert/full_text_loader.txt')
    docs = loader.load()
    rs = chunk.chunk(docs)
    logger.info(rs)
