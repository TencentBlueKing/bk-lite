from loguru import logger

from src.loader.ppt_loader import PPTLoader


def test_ppt_loader():
    loader = PPTLoader('tests/assert/ppt_loader.pptx', 'full')
    rs = loader.load()
    logger.info(rs)

    loader = PPTLoader('tests/assert/ppt_loader.pptx', 'page')
    rs = loader.load()
    logger.info(rs)
