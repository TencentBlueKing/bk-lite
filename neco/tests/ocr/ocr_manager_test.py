from regex import P
from neco.ocr.ocr_manager import OcrManager
import os


def test_ocr():
    ocr = OcrManager.load_ocr(
        ocr_type='olm_ocr',
        model='richardyoung/olmocr2:7b-q8',
        base_url=os.getenv('TEST_LLM_API_URL'),
        api_key=os.getenv('TEST_LLM_API_KEY')
    )

    result = ocr.predict(file_path='./tests/ocr/umr.jpeg')
    print(result)
