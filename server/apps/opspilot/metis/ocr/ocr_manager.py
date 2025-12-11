from typing import Optional
from loguru import logger

from apps.opspilot.metis.ocr.azure_ocr import AzureOCR
from apps.opspilot.metis.ocr.olm_ocr import OlmOcr
from apps.core.mixinx import EncryptMixin


class OcrManager:
    @classmethod
    def load_ocr(cls, ocr_type: str,
                 model: Optional[str] = None,
                 base_url: Optional[str] = None,
                 api_key: Optional[str] = None):
        ocr = None

        if ocr_type == 'olm_ocr':
            # 解密 api_key
            decrypted_config = {"api_key": api_key}
            EncryptMixin.decrypt_field("api_key", decrypted_config)
            ocr = OlmOcr(base_url=base_url,
                         api_key=decrypted_config["api_key"], model=model)

        if ocr_type == 'azure_ocr':
            decrypted_config = {"api_key": api_key}
            EncryptMixin.decrypt_field("api_key", decrypted_config)
            ocr = AzureOCR(
                api_key=decrypted_config["api_key"], endpoint=base_url)

        return ocr
