from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import resolve_assignable_organization_ids, resolve_current_team_data_scope
from apps.core.utils.user_group import normalize_user_group_ids
from apps.rum.services.control import ControlError
from apps.rum.services.monitors import MonitorsService
from apps.rum.services.validation import ValidationError
from apps.rum.views.http import actor_from_request, control_error_response


def _service() -> MonitorsService:
    return MonitorsService()


def _visible_orgs(request) -> set[int]:
    try:
        scope = resolve_current_team_data_scope(request)
    except BaseAppException:
        return set()
    return set(scope.data_team_ids)


def _assignable_orgs(request) -> set[int]:
    try:
        return set(resolve_assignable_organization_ids(request))
    except BaseAppException as exc:
        raise ControlError("forbidden", "organization is not assignable") from exc


class RumMonitorViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("monitors-View")
    def list(self, request):
        return Response(_service().list_monitors(visible_orgs=_visible_orgs(request)))

    @HasPermission("monitors-Operate")
    def create(self, request):
        try:
            return Response(
                _service().create_monitor(
                    actor_from_request(request),
                    request.data,
                    assignable_orgs=_assignable_orgs(request),
                )
            )
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("monitors-Operate")
    def update(self, request, pk=None):
        try:
            return Response(
                _service().update_monitor(
                    actor_from_request(request),
                    pk,
                    request.data,
                    assignable_orgs=_assignable_orgs(request),
                    visible_orgs=_visible_orgs(request),
                )
            )
        except ValidationError as exc:
            return Response({"code": "invalid_argument", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ControlError as exc:
            return control_error_response(exc)

    @HasPermission("monitors-Operate")
    def destroy(self, request, pk=None):
        try:
            _service().delete_monitor(pk, visible_orgs=_visible_orgs(request))
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ControlError as exc:
            return control_error_response(exc)


class RumAlertEventViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[^/]+"

    @HasPermission("alert_events-View")
    def list(self, request):
        params = request.query_params.dict()
        if str(params.get("my_alert") or "") in {"1", "true", "yes"}:
            params["handler"] = str(getattr(request.user, "id", "") or getattr(request.user, "pk", "") or "")
        return Response(_service().list_alert_events(params, visible_orgs=_visible_orgs(request)))

    @HasPermission("alert_events-View")
    def retrieve(self, request, pk=None):
        try:
            return Response(_service().get_alert_event(pk, visible_orgs=_visible_orgs(request)))
        except ControlError as exc:
            return control_error_response(exc)


class RumAlertClaimView(APIView):
    @HasPermission("alert_events-Operate")
    def post(self, request, pk):
        return _disposition_response(lambda service: service.claim_alert(pk, _actor(request), visible_orgs=_visible_orgs(request)))


class RumAlertAssignView(APIView):
    @HasPermission("alert_events-Operate")
    def post(self, request, pk):
        return _disposition_response(
            lambda service: service.assign_alert(pk, _actor(request), request.data.get("handlers") or [], visible_orgs=_visible_orgs(request))
        )


class RumAlertReassignView(APIView):
    @HasPermission("alert_events-Operate")
    def post(self, request, pk):
        return _disposition_response(
            lambda service: service.reassign_alert(pk, _actor(request), request.data.get("handlers") or [], visible_orgs=_visible_orgs(request))
        )


class RumAlertCloseView(APIView):
    @HasPermission("alert_events-Operate")
    def post(self, request, pk):
        return _disposition_response(lambda service: service.close_alert(pk, _actor(request), visible_orgs=_visible_orgs(request)))


class RumAlertDeliveryRetryView(APIView):
    @HasPermission("alert_events-Operate")
    def post(self, request, pk, delivery_id):
        return _disposition_response(
            lambda service: service.retry_alert_delivery(pk, delivery_id, _actor(request), visible_orgs=_visible_orgs(request))
        )


def _actor(request):
    from apps.rum.services.disposition import actor_from_user

    return actor_from_user(request.user)


def _disposition_response(call):
    try:
        return Response(call(_service()))
    except ControlError as exc:
        return control_error_response(exc)


class RumNotificationChannelView(APIView):
    @HasPermission("monitors-View")
    def get(self, request):
        organization_ids = _query_orgs(request)
        if not organization_ids:
            return Response([])
        try:
            channels = _directory().list_channels(request, organization_ids)
        except RuntimeError as exc:
            return Response({"code": "notification_channels_unavailable", "message": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(channels)


class RumNotificationRecipientView(APIView):
    @HasPermission("monitors-View")
    def get(self, request):
        organization_ids = _query_orgs(request)
        if not organization_ids:
            return Response([])
        search = str(request.query_params.get("search") or "")
        try:
            limit = min(100, max(1, int(request.query_params.get("limit") or 20)))
        except (TypeError, ValueError):
            limit = 20
        try:
            recipients = _directory().search_recipients(request, organization_ids, search=search, limit=limit)
        except RuntimeError as exc:
            return Response({"code": "notification_recipients_unavailable", "message": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(recipients)


def _query_orgs(request) -> list[int]:
    raw = str(request.query_params.get("organization_ids") or "")
    orgs = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            orgs.append(int(part))
        except ValueError:
            continue
    visible = _visible_orgs(request)
    if not visible:
        return []
    return [org for org in orgs if org in visible] or list(visible)


class _ChannelDirectory:
    def list_channels(self, request, organization_ids: list[int]) -> list[dict]:
        from apps.rpc.system_mgmt import SystemMgmt

        response = SystemMgmt().list_notification_channels_scoped(
            _actor_context(request, organization_ids[0]),
            teams=organization_ids,
            include_children=request.COOKIES.get("include_children", "0") == "1",
        )
        return _directory_rows(response, "通知渠道目录不可用")

    def search_recipients(self, request, organization_ids: list[int], *, search: str, limit: int) -> list[dict]:
        from apps.rpc.system_mgmt import SystemMgmt

        response = SystemMgmt().search_notification_recipients_scoped(
            _actor_context(request, organization_ids[0]),
            teams=organization_ids,
            include_children=request.COOKIES.get("include_children", "0") == "1",
            search=search,
            limit=limit,
        )
        return _directory_rows(response, "通知接收人目录不可用")


def _directory():
    return _ChannelDirectory()


def _actor_context(request, organization_id: int) -> dict:
    user = request.user
    return {
        "username": user.username,
        "domain": getattr(user, "domain", "domain.com"),
        "current_team": organization_id,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": bool(getattr(user, "is_superuser", False)),
        "group_list": normalize_user_group_ids(getattr(user, "group_list", [])),
    }


def _directory_rows(response, fallback: str) -> list[dict]:
    if not isinstance(response, dict) or response.get("result") is False:
        message = response.get("message") if isinstance(response, dict) else fallback
        raise RuntimeError(message or fallback)
    rows = response.get("data") or []
    if not isinstance(rows, list):
        raise RuntimeError(fallback)
    return rows
