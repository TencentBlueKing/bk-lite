from loguru import logger

from src.loader.markdown_loader import MarkdownLoader


def test_markdown_loader():
    loader = MarkdownLoader(path='tests/assert/full_markdown_loader.md')
    rs = loader.load()
    logger.info(rs)
