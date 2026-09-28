"""将异常按类型映射为安全的 HTTP 响应。

view 中常见的 ``except Exception as e: return Response({"message": str(e)}, 500)``
存在两个问题：

1. 把内部异常细节（栈/SQL/路径等）直接回显给前端，泄漏实现信息。
2. 一律返回 500，让客户端无法区分 4xx 业务错误与 5xx 系统错误。

本模块提供 :func:`exception_to_response`，按异常类型映射状态码，将异常细节仅写入日志。
"""

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import job_logger as logger
from apps.job_mgmt.utils.i18n import job_message

try:
    from nats.errors import Error as NatsError
except ImportError:  # pragma: no cover - nats 是项目硬依赖，缺失时退化为不识别
    NatsError = None

DEFAULT_5XX_MESSAGE = job_message(None, "error.internal_server", "Internal server error; try again later")
SERVICE_UNAVAILABLE_MESSAGE = job_message(None, "error.service_unavailable", "Upstream service is temporarily unavailable; try again later")
NOT_FOUND_MESSAGE = job_message(None, "error.resource_not_found", "Resource not found")


def exception_to_response(
    e: Exception,
    *,
    context: str = "",
    default_message: str | None = None,
    body_key: str = "detail",
    request=None,
) -> Response:
    """根据异常类型返回安全的 HTTP 响应；异常细节仅写日志。

    响应体形如 ``{body_key: <文案>}``，搭配 ``config/drf/renderers.py`` 的
    ``CustomRenderer`` 会被规范化为 ``{result, code, message, data}`` 外壳。
    ``body_key`` 默认 ``"detail"`` —— 这是渲染器优先读取的字段；改成其他键
    会让渲染器把整个 body 当成 dict 走 ``key:value;key:value`` 拼接，
    输出会被拧坏。

    映射规则：

    - :class:`BaseAppException` / :class:`ValueError` / DRF 或 Django 的 ``ValidationError``
      → 400，对外回显异常 ``str(e)``（业务文案是后端撰写的，安全）。
    - :class:`ObjectDoesNotExist` → 404，对外返回固定文案。
    - :class:`TimeoutError` / :class:`ConnectionError` / :class:`nats.errors.Error`
      → 503，对外返回通用文案（下游 NATS / 网络不可达）。
    - 其余异常 → 500，对外返回 ``default_message``，异常细节走日志。

    Args:
        e: 抓获的异常对象。
        context: 上下文标签，用于日志（如 ``"[query_nodes]"``）。
        default_message: 5xx 兜底对外文案。
        body_key: 响应体里承载消息的字段名。默认 ``"detail"`` 匹配 ``CustomRenderer``。
        request: 可选请求，用于选择语言。
    """
    prefix = f"{context} " if context else ""
    resolved_default = default_message or job_message(request, "error.internal_server", "Internal server error; try again later")
    not_found = job_message(request, "error.resource_not_found", "Resource not found")
    unavailable = job_message(request, "error.service_unavailable", "Upstream service is temporarily unavailable; try again later")

    if isinstance(e, BaseAppException):
        logger.warning(f"{prefix}业务异常: {e}")
        return Response({body_key: str(e)}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(e, (DRFValidationError, DjangoValidationError, ValueError)):
        logger.warning(f"{prefix}参数错误: {e}")
        return Response({body_key: str(e)}, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(e, ObjectDoesNotExist):
        logger.warning(f"{prefix}资源不存在: {e}")
        return Response({body_key: not_found}, status=status.HTTP_404_NOT_FOUND)

    # NATS RPC 失败（NoRespondersError / NoServersError / ConnectionClosedError 等）
    # 都归到"上游不可达"。nats.errors.TimeoutError 同时是 Python TimeoutError，
    # 这里把它和裸 TimeoutError / ConnectionError 一起处理。
    if isinstance(e, (TimeoutError, ConnectionError)) or (NatsError is not None and isinstance(e, NatsError)):
        logger.warning(f"{prefix}上游不可达: {e}")
        return Response({body_key: unavailable}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    logger.exception(f"{prefix}未预期异常: {e}")
    return Response({body_key: resolved_default}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
