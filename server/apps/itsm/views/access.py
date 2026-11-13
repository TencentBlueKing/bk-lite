"""ITSM 请求边界：统一对象范围与预期错误响应。"""

from functools import wraps

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import get_object_or_404
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import Ticket


def api_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except (ObjectDoesNotExist, Http404):
            return WebUtils.response_error("记录不存在", status_code=404)
        except (S3Error, HTTPError):
            return WebUtils.response_error("附件存储暂不可用，请重试", status_code=502)
        except FlowableError:
            return WebUtils.response_error("流程引擎暂不可用，操作未完成", status_code=502)
        except PermissionError:
            return WebUtils.response_403("无权执行此操作")
        except (ValueError, KeyError, TypeError) as exc:
            errors = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
            return WebUtils.response_error({"errors": errors}, "请求参数或表单校验失败")

    return wrapped


def domain_of(request):
    return getattr(request.user, "domain", "") or ""


def ticket_scope(request):
    return Ticket.objects.filter(domain=domain_of(request)).visible_to(
        getattr(request.user, "username", ""),
        see_all=bool(getattr(request.user, "is_superuser", False)),
        domain=domain_of(request),
    )


def get_ticket(request, ticket_id):
    return get_object_or_404(ticket_scope(request), id=ticket_id)


def has_permission(request, permission):
    if getattr(request.user, "is_superuser", False):
        return True
    permissions = getattr(request.user, "permission", {})
    return permission in (permissions.get("itsm", set()) if isinstance(permissions, dict) else permissions)


def method_permission(read, write):
    """同一资源的查询与写入使用各自的菜单权限。"""
    from apps.core.decorators.api_permission import HasPermission

    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            request = args[0] if hasattr(args[0], "method") else args[1]
            permission = read if request.method in {"GET", "HEAD"} else write
            return HasPermission(permission)(view)(*args, **kwargs)

        return wrapped

    return decorate
