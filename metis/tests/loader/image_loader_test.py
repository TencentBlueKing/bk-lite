from loguru import logger

from src.loader.image_loader import ImageLoader
from src.ocr.pp_ocr import PPOcr


def test_image_loader():
    loader = ImageLoader('tests/assert/umr.jpeg', PPOcr())
    rs = loader.load()
    logger.info(rs)
