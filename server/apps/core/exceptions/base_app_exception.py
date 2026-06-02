import logging
from typing import Any, Dict, Optional, Union


class BaseAppException(Exception):
    ERROR_CODE = "0000000"
    MESSAGE = "APP异常"
    STATUS_CODE = 500
    LOG_LEVEL = logging.ERROR

    def __init__(self, message: Optional[str] = None, data: Any = None, *args):
        """
        初始化应用异常

        :param message: 错误消息，如果为None则使用类的默认MESSAGE
        :param data: 附加数据，可以是任意类型
        :param args: 传递给父类Exception的其他参数
        """
        self.message = message or self.MESSAGE
        super(BaseAppException, self).__init__(self.message, *args)

        self.data = data

        # 仅记录异常发生的关键信息
        logger = logging.getLogger(self.__class__.__module__)
        logger.log(self.LOG_LEVEL, "异常 %s: %s [%s]", self.__class__.__name__, self.message, self.ERROR_CODE)

    def render_data(self) -> Any:
        """
        渲染异常数据

        :return: 处理后的数据，默认直接返回原始数据
        """
        return self.data

    def response_data(self) -> Dict[str, Union[bool, str, Any]]:
        """
        生成标准的响应数据格式

        :return: 包含result、code、message、data的字典
        """
        return {
            "result": False,
            "code": self.ERROR_CODE,
            "message": self.message,
            "data": self.render_data(),
        }


class UnauthorizedException(BaseAppException):
    """认证失败异常，返回401状态码"""

    ERROR_CODE = "4010001"
    MESSAGE = "未授权访问"
    STATUS_CODE = 401
    LOG_LEVEL = logging.ERROR


class ValidationAppException(BaseAppException):
    """校验失败异常，返回400状态码"""

    ERROR_CODE = "4000001"
    MESSAGE = "请求参数非法"
    STATUS_CODE = 400
    LOG_LEVEL = logging.WARNING
