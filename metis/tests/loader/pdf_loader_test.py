from loguru import logger

from src.loader.pdf_loader import PDFLoader
from src.ocr.pp_ocr import PPOcr


def test_load_pdf():
    ocr = PPOcr()
    loader = PDFLoader(file_path="tests/assert/pdf_word_raw.pdf", ocr=ocr)
    result = loader.load()
    logger.info(result)
