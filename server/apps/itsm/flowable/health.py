import requests
from django.conf import settings

from apps.core.logger import itsm_logger

# flowable-rest:7.1.0 的上下文是 /flowable-rest，仓库接口在 /service 下。
_REPOSITORY_PATH = "/flowable-rest/service/repository/deployments"
_TIMEOUT_SECONDS = 5


def probe_flowable() -> dict:
    """探测 Flowable REST 是否可连通。不记录口令，也不把响应体返回给调用方。"""
    password = settings.FLOWABLE_PASSWORD
    if not password:
        return {"reachable": False, "status_code": None, "detail": "missing_password"}

    url = f"{settings.FLOWABLE_URL.rstrip('/')}{_REPOSITORY_PATH}"
    try:
        response = requests.get(
            url,
            auth=(settings.FLOWABLE_USER, password),
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        itsm_logger.warning("Flowable 健康检查失败: %s", type(exc).__name__)
        return {"reachable": False, "status_code": None, "detail": type(exc).__name__}

    return {
        "reachable": response.status_code == 200,
        "status_code": response.status_code,
        "detail": "ok" if response.status_code == 200 else "http_error",
    }
