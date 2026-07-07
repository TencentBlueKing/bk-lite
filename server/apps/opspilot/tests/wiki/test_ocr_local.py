def test_tesseract_unavailable_is_graceful():
    from apps.opspilot.metis.ocr.tesseract_ocr import TesseractOCR

    # 本环境未装 pytesseract/tesseract → available False、predict 返回空串(不抛错)
    assert TesseractOCR.available() is False
    assert TesseractOCR().predict("nonexistent.png") == ""


def test_ocr_manager_registers_tesseract():
    from apps.opspilot.metis.ocr.ocr_manager import OcrManager
    from apps.opspilot.metis.ocr.tesseract_ocr import TesseractOCR

    assert isinstance(OcrManager.load_ocr("tesseract"), TesseractOCR)


def test_ocr_manager_registers_rapidocr():
    from apps.opspilot.metis.ocr.ocr_manager import OcrManager
    from apps.opspilot.metis.ocr.rapid_ocr import RapidOCR

    assert isinstance(OcrManager.load_ocr("rapidocr"), RapidOCR)


def test_rapidocr_unavailable_is_graceful():
    from apps.opspilot.metis.ocr.rapid_ocr import RapidOCR

    # 私有 pip 源无 rapidocr_onnxruntime → available False、predict 空串(不抛错)
    if not RapidOCR.available():
        assert RapidOCR().predict("nonexistent.png") == ""
