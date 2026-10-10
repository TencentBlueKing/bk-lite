"""OpenAPI 暴露注册表：service 名一级实体 + path → 端点映射。

fail-closed：任何契约缺失（缺 schema、缺 inject、身份参数缺失、命名违规、
path 重复）在注册时（即 Django AppConfig.ready 的 import 阶段）抛
ImproperlyConfigured，阻断启动——契约错误属代码缺陷，不适用「非关键资源
不阻断启动」的豁免。

契约来源：specs/changes/openapi-unified-gateway/design.md 3.1 / 3.4。
"""

import inspect
import re
from dataclasses import dataclass, field

from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers as drf_serializers

SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

INJECT_TEAM_LIST = "team_list"
INJECT_TEAM_LIST_WITH_USER = "team_list_with_user"
INJECT_USER_INFO = "user_info"
VALID_INJECTS = {INJECT_TEAM_LIST, INJECT_TEAM_LIST_WITH_USER, INJECT_USER_INFO}

DISPATCH_LOCAL = "local"

METHODS = {"GET", "POST", "PUT", "DELETE"}

# 锚点式注入下，serializer 中会被抽入 user_info 的业务参数（组织锚点与级联开关）
USER_INFO_ANCHOR_FIELDS = ("team", "include_children")


@dataclass
class Endpoint:
    service: str
    sub_path: str
    method: str
    func: object
    serializer_class: type
    inject: str
    permission: str = ""
    permission_app: str = ""
    team_free: bool = False
    param_map: dict = field(default_factory=dict)
    dispatch: str = DISPATCH_LOCAL
    summary: str = ""

    @property
    def path(self) -> str:
        return f"{self.service}/{self.sub_path}"


class OpenAPIRegistry:
    def __init__(self):
        self._endpoints = {}

    def register(
        self,
        *,
        path: str,
        method: str,
        serializer_class,
        func,
        inject: str = None,
        permission: str = "",
        permission_app: str = "",
        team_free: bool = False,
        param_map: dict = None,
        summary: str = "",
    ) -> Endpoint:
        func_name = getattr(func, "__name__", repr(func))

        service, _, sub_path = (path or "").partition("/")
        if not sub_path:
            raise ImproperlyConfigured(
                f"openapi_expose({func_name}): path 必须形如 'service/sub-path'，got {path!r}"
            )
        if service.startswith("_") or not SERVICE_NAME_RE.match(service):
            raise ImproperlyConfigured(
                f"openapi_expose({func_name}): 非法 service 名 {service!r}"
                "（规则 ^[a-z][a-z0-9-]{0,31}$，下划线开头为网关保留命名空间）"
            )
        if method not in METHODS:
            raise ImproperlyConfigured(
                f"openapi_expose({func_name}): method 必须是 {sorted(METHODS)} 之一，got {method!r}"
            )
        if serializer_class is None or not (
            isinstance(serializer_class, type)
            and issubclass(serializer_class, drf_serializers.BaseSerializer)
        ):
            raise ImproperlyConfigured(
                f"openapi_expose({func_name}): schema 必填且须为 DRF Serializer 子类（fail-closed）"
            )

        params = inspect.signature(func).parameters
        serializer_fields = set(serializer_class().fields)

        if team_free:
            if inject is not None:
                raise ImproperlyConfigured(
                    f"openapi_expose({func_name}): team_free=True 与 inject 互斥"
                )
        else:
            if inject not in VALID_INJECTS:
                raise ImproperlyConfigured(
                    f"openapi_expose({func_name}): inject 必须是 {sorted(VALID_INJECTS)} 之一，"
                    f"或显式声明 team_free=True，got {inject!r}"
                )
            if inject in {INJECT_TEAM_LIST, INJECT_TEAM_LIST_WITH_USER}:
                if "team" not in params:
                    raise ImproperlyConfigured(
                        f"openapi_expose({func_name}): inject='{inject}' 要求函数具有可按关键字传入的 team 参数"
                    )
                if "team" in serializer_fields:
                    raise ImproperlyConfigured(
                        f"openapi_expose({func_name}): inject='{inject}' 时 serializer 不得声明 team 字段"
                        "（身份集合只能由网关注入，客户端字段一律丢弃）"
                    )
                if inject == INJECT_TEAM_LIST_WITH_USER:
                    if "user_info" not in params:
                        raise ImproperlyConfigured(
                            f"openapi_expose({func_name}): inject='{inject}' 要求函数具有 user_info 参数"
                        )
                    conflict = serializer_fields & {"user_info", "user", "domain"}
                    if conflict:
                        raise ImproperlyConfigured(
                            f"openapi_expose({func_name}): serializer 不得声明身份字段 {sorted(conflict)}"
                        )
            if inject == INJECT_USER_INFO:
                if "user_info" not in params:
                    raise ImproperlyConfigured(
                        f"openapi_expose({func_name}): inject='user_info' 要求函数具有 user_info 参数"
                    )
                conflict = serializer_fields & {"user_info", "user", "domain"}
                if conflict:
                    raise ImproperlyConfigured(
                        f"openapi_expose({func_name}): serializer 不得声明身份字段 {sorted(conflict)}"
                    )
                # 锚点式下 dispatcher 从 serializer 中抽取字面名 team 的字段并入
                # user_info。serializer 若把锚点命名成别的字段，JWT 调用方将永远
                # 拿到 400 "team is required"（且无法补传，未知字段被拒），
                # API 令牌调用方则静默使用绑定组织——把该错误提前到启动期。
                if "team" not in serializer_fields:
                    raise ImproperlyConfigured(
                        f"openapi_expose({func_name}): inject='user_info' 要求 serializer 声明名为 "
                        "'team' 的组织锚点字段（网关据此抽取并注入 user_info）"
                    )

        if permission and not permission_app:
            raise ImproperlyConfigured(
                f"openapi_expose({func_name}): 声明 permission 时必须同时声明 permission_app"
                "（取值为该应用菜单定义的 client_id，如 patch_mgmt → 'patch'）"
            )

        key = (service, sub_path, method)
        if key in self._endpoints:
            raise ImproperlyConfigured(
                f"openapi_expose({func_name}): 重复注册 {method} /{path}"
            )

        endpoint = Endpoint(
            service=service,
            sub_path=sub_path,
            method=method,
            func=func,
            serializer_class=serializer_class,
            inject=inject,
            permission=permission,
            permission_app=permission_app,
            team_free=team_free,
            param_map=dict(param_map or {}),
            summary=summary,
        )
        self._endpoints[key] = endpoint
        return endpoint

    def find(self, service: str, sub_path: str, method: str):
        return self._endpoints.get((service, sub_path, method))

    def services(self):
        """内部注册的 service 名列表（M2 起与外部 KV 注册表合并成统一目录）。"""
        return sorted({ep.service for ep in self._endpoints.values()})

    def endpoints(self):
        return list(self._endpoints.values())


default_registry = OpenAPIRegistry()
