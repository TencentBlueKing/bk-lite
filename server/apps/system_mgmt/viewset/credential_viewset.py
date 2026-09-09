from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models.credential import Credential, CredentialType
from apps.system_mgmt.serializers.credential_serializer import CredentialSerializer, CredentialTypeSerializer
from apps.system_mgmt.services.credential_ref_count import attach_public_refs
from apps.system_mgmt.services.credential_service import (
    CredentialServiceError,
    create_credential,
    create_type,
    delete_credential,
    delete_type,
    get_credential,
    list_assignable_groups,
    list_types,
    list_usable_groups,
    public_credential,
    query_credentials,
    set_disabled,
    update_credential,
    update_type,
)
from apps.system_mgmt.utils.operation_log_utils import log_operation

_ERROR_STATUS = {
    "forbidden": 403,
    "not_found": 404,
    "invalid": 400,
    "conflict": 409,
    "immutable": 400,
    "in_use": 409,
    "disabled": 400,
}


def _error_response(exc):
    status_code = _ERROR_STATUS.get(getattr(exc, "code", ""), 400)
    return JsonResponse({"result": False, "message": getattr(exc, "code", "invalid")}, status=status_code)


def _request_actor(request, current_team=None):
    if current_team is None:
        current_team = request.COOKIES.get("current_team")
    return {
        "username": getattr(request.user, "username", ""),
        "domain": getattr(request.user, "domain", "domain.com"),
        "current_team": current_team,
        "group_list": getattr(request.user, "group_list", ()),
        "is_superuser": bool(getattr(request.user, "is_superuser", False)),
    }


def _audit_credential(request, action_type, summary, credential_id, detail):
    log_operation(
        request,
        action_type,
        "system-manager",
        summary,
        target_type="credential",
        target_id=credential_id,
        detail=detail,
    )


class CredentialTypePageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 500

    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw in ("0", "-1"):
            return self.max_page_size
        if raw in (None, ""):
            return self.page_size
        try:
            size = int(raw)
        except (TypeError, ValueError):
            return self.page_size
        if size < 1:
            return self.max_page_size
        return min(size, self.max_page_size)

    def get_paginated_response(self, data):
        return Response({"count": self.page.paginator.count, "items": data})


class CredentialPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw in (None, "", "0", "-1"):
            return self.page_size
        try:
            size = int(raw)
        except (TypeError, ValueError):
            return self.page_size
        if size < 1:
            return self.page_size
        return min(size, self.max_page_size)

    def get_paginated_response(self, data):
        return Response({"count": self.page.paginator.count, "items": data})


class CredentialTypeViewSet(MaintainerViewSet):
    queryset = CredentialType.objects.all().order_by("-is_builtin", "id")
    serializer_class = CredentialTypeSerializer
    pagination_class = CredentialTypePageNumberPagination
    lookup_field = "key"
    lookup_value_regex = r"[A-Za-z][A-Za-z0-9_]*"

    @HasPermission("credential-View")
    def list(self, request, *args, **kwargs):
        items = list_types(
            {
                "search": request.query_params.get("search", ""),
                "category": request.query_params.get("category"),
            }
        )
        page = self.paginate_queryset(items)
        return self.get_paginated_response(page)

    @HasPermission("credential-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(self.get_serializer(instance).data)

    @HasPermission("credential-Add")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            created = create_type(serializer.validated_data, _request_actor(request))
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(
            request,
            "create",
            f"新增凭据类型: {created.name}",
            created.key,
            {"name": created.name, "key": created.key},
        )
        return Response(self.get_serializer(created).data, status=201)

    @HasPermission("credential-Edit")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        try:
            updated = update_type(instance.key, serializer.validated_data, _request_actor(request))
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(
            request,
            "update",
            f"编辑凭据类型: {updated.name}",
            updated.key,
            {"name": updated.name, "key": updated.key},
        )
        return Response(self.get_serializer(updated).data)

    @HasPermission("credential-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("credential-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        name = instance.name
        key = instance.key
        try:
            delete_type(key, _request_actor(request))
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(request, "delete", f"删除凭据类型: {name}", key, {"name": name, "key": key})
        return Response(status=204)

    @action(methods=["GET"], detail=False)
    @HasPermission("credential-View")
    def selectable(self, request, *args, **kwargs):
        items = list_types(
            {
                "search": request.query_params.get("search", ""),
                "category": request.query_params.get("category"),
            }
        )
        return Response(items[:500])


class CredentialViewSet(MaintainerViewSet):
    queryset = Credential.objects.select_related("type").all().order_by("id")
    serializer_class = CredentialSerializer
    pagination_class = CredentialPageNumberPagination
    lookup_field = "credential_id"
    lookup_value_regex = r"crd-[A-Za-z0-9_]+-[0-9a-f]{32}"

    def get_queryset(self):
        return Credential.objects.select_related("type").none()

    @HasPermission("credential-View")
    def list(self, request, *args, **kwargs):
        actor = _request_actor(request)
        filters = {
            "current_team": actor["current_team"],
            "search": request.query_params.get("search", ""),
            "category": request.query_params.get("category"),
            "type": request.query_params.get("type"),
            "group_id": request.query_params.get("group_id"),
            "owner_scope": "manage",
        }
        if "disabled" in request.query_params:
            raw = request.query_params.get("disabled")
            filters["disabled"] = raw.lower() in {"1", "true", "yes"} if isinstance(raw, str) else bool(raw)
        try:
            queryset = query_credentials(filters, actor=actor)
        except CredentialServiceError as exc:
            return _error_response(exc)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(attach_public_refs([public_credential(row) for row in page or []]))

    @HasPermission("credential-View")
    def retrieve(self, request, *args, **kwargs):
        actor = _request_actor(request)
        try:
            payload = get_credential(kwargs.get("credential_id"), actor["current_team"], actor=actor, owner_scope="manage")
        except CredentialServiceError as exc:
            return _error_response(exc)
        return Response(payload)

    @HasPermission("credential-Add")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _request_actor(request)
        payload = dict(serializer.validated_data)
        payload["current_team"] = actor["current_team"]
        try:
            created = create_credential(payload, actor=actor)
            public = get_credential(created.credential_id, actor["current_team"], actor=actor, owner_scope="manage")
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(
            request,
            "create",
            f"新增凭据: {public['name']}",
            public["credential_id"],
            {"name": public["name"], "type": public["type"], "group_id": public["group_id"]},
        )
        return Response(public, status=201)

    @HasPermission("credential-Edit")
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        actor = _request_actor(request)
        payload = dict(serializer.validated_data)
        payload["current_team"] = actor["current_team"]
        try:
            updated = update_credential(kwargs.get("credential_id"), payload, actor=actor)
            public = get_credential(updated.credential_id, actor["current_team"], actor=actor, owner_scope="manage")
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(
            request,
            "update",
            f"编辑凭据: {public['name']}",
            public["credential_id"],
            {"name": public["name"], "type": public["type"], "group_id": public["group_id"]},
        )
        return Response(public)

    @HasPermission("credential-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("credential-Delete")
    def destroy(self, request, *args, **kwargs):
        actor = _request_actor(request)
        credential_id = kwargs.get("credential_id")
        try:
            public = get_credential(credential_id, actor["current_team"], actor=actor, owner_scope="manage")
            delete_credential(credential_id, actor=actor, current_team=actor["current_team"])
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(
            request,
            "delete",
            f"删除凭据: {public['name']}",
            credential_id,
            {"name": public["name"], "type": public["type"], "group_id": public["group_id"]},
        )
        return Response(status=204)

    @action(methods=["GET"], detail=False)
    @HasPermission("credential-View")
    def selectable(self, request, *args, **kwargs):
        actor = _request_actor(request)
        filters = {
            "current_team": actor["current_team"],
            "search": request.query_params.get("search", ""),
            "category": request.query_params.get("category"),
            "type": request.query_params.get("type"),
            "group_id": request.query_params.get("group_id"),
            "disabled": False,
        }
        try:
            queryset = query_credentials(filters, actor=actor)
            size_raw = request.query_params.get("page_size") or 100
            page_raw = request.query_params.get("page") or 1
            size = min(max(int(size_raw), 1), 100)
            page_number = max(int(page_raw), 1)
        except CredentialServiceError as exc:
            return _error_response(exc)
        except (TypeError, ValueError):
            size, page_number = 100, 1
        start = (page_number - 1) * size
        items = [public_credential(row) for row in queryset[start : start + size]]
        return Response(items)

    @action(methods=["GET"], detail=False)
    @HasPermission("credential-View")
    def assignable_groups(self, request, *args, **kwargs):
        try:
            items = list_assignable_groups(actor=_request_actor(request))
        except CredentialServiceError as exc:
            return _error_response(exc)
        return Response(items)

    @action(methods=["GET"], detail=False)
    @HasPermission("credential-View")
    def usable_groups(self, request, *args, **kwargs):
        try:
            items = list_usable_groups(actor=_request_actor(request))
        except CredentialServiceError as exc:
            return _error_response(exc)
        return Response(items)

    @action(methods=["POST"], detail=True)
    @HasPermission("credential-Edit")
    def disable(self, request, *args, **kwargs):
        actor = _request_actor(request)
        disabled = bool(request.data.get("disabled", True))
        try:
            public = set_disabled(
                kwargs.get("credential_id"),
                disabled,
                actor=actor,
                current_team=actor["current_team"],
            )
        except CredentialServiceError as exc:
            return _error_response(exc)
        _audit_credential(
            request,
            "update",
            f"{'停用' if disabled else '启用'}凭据: {public['name']}",
            public["credential_id"],
            {"name": public["name"], "disabled": public["disabled"]},
        )
        return Response(public)
