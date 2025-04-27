import os

from langchain_openai import ChatOpenAI
from loguru import logger

from src.chunk.fixed_size_chunk import FixedSizeChunk
from src.enhance.qa_enhance import QAEnhance
from src.loader.markdown_loader import MarkdownLoader


def test_qa_enhance():
    loader = MarkdownLoader(path='../readme.md')
    doc = loader.load()
    chunk = FixedSizeChunk()
    rs = chunk.chunk(doc)
    llm = ChatOpenAI(model="gpt-4o", base_url=os.getenv("OPENAI_BASE_URL"),
                     api_key=os.getenv("OPENAI_API_KEY"),
                     temperature="0")
    e = QAEnhance(10)
    for t in rs:
        qa = e.generate_qa(llm, t.page_content)
        logger.info(qa)
