import logging

from apps.opspilot.metis.ocr.base_ocr import BaseOCR

logger = logging.getLogger(__name__)


class RapidOCR(BaseOCR):
    """本地 RapidOCR(ONNX runtime,自带模型)——无需外部服务,也无需系统二进制。

    依赖 pip 包 `rapidocr_onnxruntime`(纯 pip,含中英文模型 + onnxruntime),按需惰性加载;
    缺失时 `available()` 返回 False、`predict()` 返回空串(优雅降级)。引擎单例复用。
    """

    _engine = None

    @classmethod
    def available(cls) -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401

            return True
        except Exception:
            return False

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            from rapidocr_onnxruntime import RapidOCR as _RapidOCR

            cls._engine = _RapidOCR()
        return cls._engine

    def predict(self, file) -> str:
        try:
            result, _ = self._get_engine()(file)
            if not result:
                return ""
            return "\n".join(line[1] for line in result if len(line) > 1).strip()
        except Exception:
            logger.exception("本地 RapidOCR 识别失败:%s", file)
            return ""
