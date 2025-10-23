import logging
from functools import wraps
from typing import Any, Callable

from django.views.generic.base import View

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.viewset_utils import GenericViewSetFun
from apps.core.utils.web_utils import WebUtils
from apps.opspilot.models import KnowledgeBase

logger = logging.getLogger("app")


def _extract_request(args: tuple) -> Any:
    """从参数中提取请求对象"""
    request = args[0]
    if isinstance(request, View):
        return args[1] if len(args) > 1 else None
    return request


class CheckKnowledgePermission(GenericViewSetFun):
    def __init__(self, model, params_key="", id_field="id"):
        self.model = model
        self.params_key = params_key
        self.id_field = id_field

    def __call__(self, task_definition) -> Callable:
        @wraps(task_definition)
        def wrapper(*args, **kwargs):
            request = _extract_request(args)
            if not request.user.is_superuser:
                params = request.GET.dict() or request.data
                if kwargs.get("pk"):
                    instance = self.model.objects.get(id=kwargs["pk"]).knowledge_base
                elif self.params_key:
                    instance = self.model.objects.get(**{self.id_field: params.get(self.params_key)}).knowledge_base
                else:
                    instance = KnowledgeBase.objects.get(id=params.get("knowledge_base_id"))
                current_team = request.COOKIES.get("current_team", "0")
                has_permission = self.get_has_permission(request.user, instance, current_team)
                if not has_permission:
                    loader = LanguageLoader(app="opspilot", default_lang="en")
                    message = loader.get("error.insufficient_permissions") or "insufficient permissions"
                    return WebUtils.response_403(message)
            return task_definition(*args, **kwargs)

        return wrapper
