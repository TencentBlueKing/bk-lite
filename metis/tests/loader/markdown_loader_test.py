from loguru import logger

from src.loader.markdown_loader import MarkdownLoader


def test_markdown_loader():
    loader = MarkdownLoader(path='../readme.md')
    rs = loader.load()
    logger.info(rs)
