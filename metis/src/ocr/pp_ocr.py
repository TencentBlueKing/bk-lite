import paddle
from loguru import logger
from paddleocr import PaddleOCR

from src.ocr.base_ocr import BaseOCR


class PPOcr(BaseOCR):
    def __init__(self):
        gpu_available = paddle.device.is_compiled_with_cuda()
        self.ocr_engine = PaddleOCR(table=True, show_log=True,
                                    lang='ch', use_angle_cls=True,
                                    use_gpu=gpu_available,
                                    det_model_dir='models/pp_ocr_det',
                                    rec_model_dir='models/pp_ocr_rec',
                                    cls_model_dir='models/pp_ocr_cls')

    def predict(self, file) -> str:
        logger.info(f"使用PaddleOCR识别图片:[{file}]")
        result = self.ocr_engine.ocr(file, cls=True)
        recognized_texts = ''
        if result:
            for lines in result:
                for line in lines:
                    recognized_texts += line[1][0] + ''
        return recognized_texts
