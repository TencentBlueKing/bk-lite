import os

from loguru import logger

from src.loader.website_loader import WebSiteLoader


def test_website_loader():
    loader = WebSiteLoader(url=os.getenv('TEST_WEBSITE_LOADER_BASE_URL'),
                           max_depth=1)

    result=loader.load()
    logger.info(result)
