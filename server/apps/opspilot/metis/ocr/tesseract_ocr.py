import logging

from apps.opspilot.metis.ocr.base_ocr import BaseOCR

logger = logging.getLogger(__name__)


class TesseractOCR(BaseOCR):
    """本地 Tesseract OCR(无需外部服务)。

    依赖 `pytesseract` + 本机 `tesseract` 可执行文件;两者均按需惰性导入/调用,
    缺失时 `available()` 返回 False、`predict()` 返回空串(优雅降级,不抛错)。
    适合不便接入云端 OCR 服务的部署:本地装好 tesseract 即可识别纯图片资料。
    """

    def __init__(self, lang: str = "chi_sim+eng"):
        self.lang = lang

    @staticmethod
    def available() -> bool:
        """pytesseract 可导入且 tesseract 二进制可用时返回 True。"""
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def predict(self, file) -> str:
        try:
            import pytesseract
            from PIL import Image

            with Image.open(file) as img:
                return (pytesseract.image_to_string(img, lang=self.lang) or "").strip()
        except Exception:
            logger.exception("本地 Tesseract OCR 识别失败:%s(请确认已安装 pytesseract 与 tesseract 二进制)", file)
            return ""
