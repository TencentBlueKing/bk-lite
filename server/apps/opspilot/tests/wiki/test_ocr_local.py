import pytest


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


@pytest.mark.django_db
def test_build_ocr_falls_back_to_local_tesseract(monkeypatch):
    from apps.opspilot.metis.ocr.tesseract_ocr import TesseractOCR
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import material_service

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    mat = Material.objects.create(knowledge_base=kb, name="x.png", material_type="file")

    # 无 OCRProvider + 本机 tesseract 可用 → 回退本地 OCR
    monkeypatch.setattr(TesseractOCR, "available", staticmethod(lambda: True))
    assert isinstance(material_service._build_ocr(mat), TesseractOCR)
    # 本机也不可用 → None
    monkeypatch.setattr(TesseractOCR, "available", staticmethod(lambda: False))
    assert material_service._build_ocr(mat) is None
