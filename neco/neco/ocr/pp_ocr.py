from loguru import logger
from neco.ocr.base_ocr import BaseOCR


class PPOcr(BaseOCR):
    _ocr_engine = None

    @classmethod
    def get_engine(cls):
        if cls._ocr_engine is None:
            from paddleocr import PaddleOCR
            import paddle

            gpu_available = paddle.device.is_compiled_with_cuda()

            logger.info(f"初始化PaddleOCR,GPU可用性为:{gpu_available}")
            cls._ocr_engine = PaddleOCR(table=True, show_log=True,
                                        lang='ch', use_angle_cls=True,
                                        use_gpu=gpu_available,
                                        det_model_dir='models/pp_ocr_det',
                                        rec_model_dir='models/pp_ocr_rec',
                                        cls_model_dir='models/pp_ocr_cls')
        return cls._ocr_engine

    def __init__(self):
        self.ocr_engine = self.get_engine()

    def predict(self, file) -> str:
        logger.info(f"使用PaddleOCR识别图片:[{file}]")
        result = self.ocr_engine.ocr(file, cls=True)
        recognized_texts = ''
        if result:
            for lines in result:
                for line in lines:
                    recognized_texts += line[1][0] + ''
        return recognized_texts
