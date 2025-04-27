from loguru import logger

from src.loader.doc_loader import DocLoader
from src.ocr.pp_ocr import PPOcr

ocr = PPOcr()


def test_load_docs_full_mode():
    loader = DocLoader('tests/assert/pdf_word_raw.docx', mode='full', ocr=ocr)
    rs = loader.load()
    logger.info(rs)


def test_load_docs_paragraph_mode():
    loader = DocLoader('tests/assert/pdf_word_raw.docx',
                       mode='paragraph', ocr=ocr)
    rs = loader.load()
    logger.info(rs)
