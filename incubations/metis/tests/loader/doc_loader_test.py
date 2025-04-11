from src.loader.doc_loader import DocLoader
from src.ocr.pp_ocr import PPOcr


ocr = PPOcr()


def test_load_docs_full_mode():
    loader = DocLoader('tests/assert/pdf_word_raw.docx', mode='full', ocr=ocr)
    print(loader.load())


def test_load_docs_paragraph_mode():
    loader = DocLoader('tests/assert/pdf_word_raw.docx',
                       mode='paragraph', ocr=ocr)
    print(loader.load())
