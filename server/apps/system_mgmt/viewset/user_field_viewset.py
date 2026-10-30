from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models.user_field import UserFieldDefinition
from apps.system_mgmt.services.user_field_catalog import (
    UserFieldError,
    create_definition,
    delete_definition,
    disable_definition,
    serialize_definition,
    update_definition,
)
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.viewset_utils import ViewSetUtils

_ERROR_KEYS = {
    "invalid field key": "error.invalid_field_key",
    "invalid field type": "error.invalid_field_type",
    "field name required": "error.field_name_required",
    "field key exists": "error.field_key_exists",
    "field key immutable": "error.field_key_immutable",
    "field type locked": "error.field_type_locked",
    "field still mapped": "error.field_still_mapped",
    "field cannot be deleted": "error.field_cannot_be_deleted",
}


def _loader(request):
    locale = getattr(getattr(request, "user", None), "locale", None) or "zh-Hans"
    return LanguageLoader(app="system_mgmt", default_lang=locale)


def _error(request, error):
    loader = _loader(request)
    key = _ERROR_KEYS.get(error.message, "error.invalid_profile")
    return JsonResponse({"result": False, "message": loader.get(key, error.message)}, status=400)


USER_FIELD_LIST_LIMIT = 200


class UserFieldViewSet(ViewSetUtils):
    @action(detail=False, methods=["GET"])
    @HasPermission("user_fields-View")
    def search(self, request):
        queryset = UserFieldDefinition.objects.order_by("id")
        if request.GET.get("enabled_only") == "1":
            queryset = queryset.filter(is_enabled=True)
        rows = [serialize_definition(item) for item in queryset[:USER_FIELD_LIST_LIMIT]]
        return JsonResponse({"result": True, "data": rows})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_fields-Add")
    def create_field(self, request):
        try:
            definition = create_definition(
                name=request.data.get("name"),
                key=request.data.get("key"),
                field_type=request.data.get("field_type"),
                description=request.data.get("description", ""),
            )
        except UserFieldError as error:
            return _error(request, error)
        log_operation(request, "create", "system-manager", f"新增用户字段: {definition.name} ({definition.key})")
        return JsonResponse({"result": True, "data": serialize_definition(definition)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_fields-Edit")
    def update_field(self, request):
        definition = UserFieldDefinition.objects.filter(id=request.data.get("id")).first()
        if definition is None:
            return JsonResponse({"result": False, "message": _loader(request).get("error.field_not_found", "field not found")}, status=404)
        try:
            definition = update_definition(
                definition,
                name=request.data.get("name", definition.name),
                description=request.data.get("description", definition.description),
                field_type=request.data.get("field_type"),
                key=request.data.get("key"),
            )
        except UserFieldError as error:
            return _error(request, error)
        log_operation(request, "update", "system-manager", f"编辑用户字段: {definition.name} ({definition.key})")
        return JsonResponse({"result": True, "data": serialize_definition(definition)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_fields-Edit")
    def disable_field(self, request):
        definition = UserFieldDefinition.objects.filter(id=request.data.get("id")).first()
        if definition is None:
            return JsonResponse({"result": False, "message": _loader(request).get("error.field_not_found", "field not found")}, status=404)
        try:
            definition = disable_definition(definition)
        except UserFieldError as error:
            return _error(request, error)
        log_operation(request, "update", "system-manager", f"停用用户字段: {definition.name} ({definition.key})")
        return JsonResponse({"result": True, "data": serialize_definition(definition)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_fields-Delete")
    def delete_field(self, request):
        definition = UserFieldDefinition.objects.filter(id=request.data.get("id")).first()
        if definition is None:
            return JsonResponse({"result": False, "message": _loader(request).get("error.field_not_found", "field not found")}, status=404)
        label = f"{definition.name} ({definition.key})"
        try:
            delete_definition(definition)
        except UserFieldError as error:
            return _error(request, error)
        log_operation(request, "delete", "system-manager", f"删除用户字段: {label}")
        return JsonResponse({"result": True})
