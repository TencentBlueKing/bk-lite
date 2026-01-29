"""自定义异常定义."""

from bentoml.exceptions import BentoMLException


class ModelNotLoadedError(BentoMLException):
    """模型未加载异常."""

    error_code = 500


class ModelInferenceError(BentoMLException):
    """模型推理异常."""

    error_code = 500


class InvalidInputError(BentoMLException):
    """无效输入异常."""

    error_code = 400
