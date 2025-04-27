import os
from dotenv import load_dotenv
from loguru import logger

from src.ocr.azure_ocr import AzureOCR


def test_azure_ocr():
    azure_ocr = AzureOCR(
        os.getenv("TEST_AZURE_VISION_URL"),
        os.getenv("TEST_AZURE_VISION_TOKEN"),
    )

    image_path = "./tests/assert/umr.jpeg"
    result = azure_ocr.predict(image_path)
    logger.info(result)
