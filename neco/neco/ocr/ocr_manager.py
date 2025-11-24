from typing import Optional
from loguru import logger

from neco.ocr.azure_ocr import AzureOCR
from neco.ocr.olm_ocr import OlmOcr


class OcrManager:
    @classmethod
    def load_ocr(cls, ocr_type: str,
                 model: Optional[str] = None,
                 base_url: Optional[str] = None,
                 api_key: Optional[str] = None):
        ocr = None
        logger.debug(f"加载OCR服务，类型: {ocr_type}")

        if ocr_type == 'olm_ocr':
            logger.debug(f"初始化OLM-OCR服务，模型: {model}")
            ocr = OlmOcr(base_url=base_url, api_key=api_key, model=model)

        if ocr_type == 'azure_ocr':
            logger.debug(f"初始化Azure-OCR服务，endpoint: {base_url}")
            ocr = AzureOCR(api_key=api_key, endpoint=base_url)

        return ocr
