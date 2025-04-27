import os

from dotenv import load_dotenv
from loguru import logger

from src.ocr.olm_ocr import OlmOcr


def test_olm_ocr():
    ocr = OlmOcr(base_url=os.getenv('TEST_INFERENCE_BASE_URL'),
                 api_key=os.getenv('TEST_INFERENCE_TOKEN'))

    result = ocr.predict('./tests/assert/umr.jpeg')
    logger.info(result)
