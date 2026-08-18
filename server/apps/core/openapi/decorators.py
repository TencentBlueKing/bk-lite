"""@openapi_expose：内部函数升格为对外 API 的唯一入口（opt-in，fail-closed）。

与 @nats_client.register 可叠加共存；注册发生在模块 import 阶段
（各 app 的 AppConfig.ready 已 import 其 nats 模块），校验失败即阻断启动。
"""

from apps.core.openapi.registry import default_registry


def openapi_expose(
    *,
    path: str,
    method: str,
    schema,
    inject: str = None,
    permission: str = "",
    permission_app: str = "",
    team_free: bool = False,
    param_map: dict = None,
    summary: str = "",
):
    def decorator(func):
        default_registry.register(
            path=path,
            method=method,
            serializer_class=schema,
            func=func,
            inject=inject,
            permission=permission,
            permission_app=permission_app,
            team_free=team_free,
            param_map=param_map,
            summary=summary,
        )
        return func

    return decorator
