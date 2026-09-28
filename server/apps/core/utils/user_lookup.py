"""按处理人标识（ID 或用户名）定位 system_mgmt 用户。

告警处理人在各业务 app 里以 ID 或用户名混存；这里提供统一的解析入口，
业务 app 不必直接依赖 system_mgmt 的模型。
"""

from apps.system_mgmt.models import User


def is_int_identifier(value) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and value.isdigit())


def resolve_actor_user_id(actor):
    """把当前请求用户映射成处理人标识：优先同域用户 ID，找不到时退回用户名。"""
    queryset = User.objects.filter(username=actor.username)
    domain = getattr(actor, "domain", None)
    if domain:
        matched = queryset.filter(domain=domain).first()
        if matched is not None:
            return matched.id
    matched = queryset.first()
    if matched is not None:
        return matched.id
    return actor.username


def find_user(identifier):
    """按 ID 或用户名查用户；空值、布尔值和查不到都返回 None。"""
    if identifier in (None, "") or isinstance(identifier, bool):
        return None
    if is_int_identifier(identifier):
        user = User.objects.filter(id=int(identifier)).first()
        if user is not None:
            return user
    return User.objects.filter(username=str(identifier)).first()
