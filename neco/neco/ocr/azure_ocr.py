import time

from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from loguru import logger
from msrest.authentication import CognitiveServicesCredentials

from neco.ocr.base_ocr import BaseOCR


class AzureOCR(BaseOCR):
    def __init__(self, azure_ocr_endpoint: str, azure_ocr_key: str):
        self.azure_ocr_endpoint = azure_ocr_endpoint
        self.azure_ocr_key = azure_ocr_key

    def predict(self, file) -> str:
        logger.info(f"使用Azure OCR识别图片:[{file}]")
        with open(file, "rb") as image:
            try:
                computervision_client = ComputerVisionClient(self.azure_ocr_endpoint,
                                                             CognitiveServicesCredentials(self.azure_ocr_key))
                read_response = computervision_client.read_in_stream(
                    image, raw=True)
                read_operation_location = read_response.headers["Operation-Location"]
                operation_id = read_operation_location.split("/")[-1]
                while True:
                    read_result = computervision_client.get_read_result(
                        operation_id)
                    if read_result.status not in ['notStarted', 'running']:
                        break
                    time.sleep(1)

                content = ''
                if read_result.status == OperationStatusCodes.succeeded:
                    for text_result in read_result.analyze_result.read_results:
                        for line in text_result.lines:
                            content += line.text + ' '
            except Exception as ex:
                logger.error(f"Azure OCR识别图片失败: {ex}")
                content = ''
        return content
