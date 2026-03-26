from typing import Optional

from apps.opspilot.metis.ocr.azure_ocr import AzureOCR
from apps.opspilot.metis.ocr.olm_ocr import OlmOcr


class OcrManager:
    @classmethod
    def load_ocr(cls, ocr_type: str, model: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        ocr = None

        if ocr_type == "olm_ocr":
            ocr = OlmOcr(base_url=base_url or "", api_key=api_key or "", model=model or "olmOCR-7B-0225-preview")

        if ocr_type == "azure_ocr":
            ocr = AzureOCR(azure_ocr_key=api_key or "", azure_ocr_endpoint=base_url or "")

        return ocr
