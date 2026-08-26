from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.operation_analysis.services.canvas_draft.errors import DraftAccessDenied, DraftNotFound, DraftValidationFailed
from apps.operation_analysis.services.canvas_draft.service import checkpoint, get_yaml, list_history, preview_yaml, restore, update_checkpoint_label


def _resource_id(pk) -> int:
    try:
        return int(pk)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"pk": ["资源 ID 必须是整数"]}) from exc


def _payload_object(request) -> dict:
    payload = request.data.get("payload")
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValidationError({"payload": ["payload 必须是对象"]})
    return payload


def _translate(exc):
    if isinstance(exc, DraftAccessDenied):
        raise PermissionDenied("无权读写该画布草稿") from exc
    if isinstance(exc, DraftNotFound):
        raise NotFound("画布不存在") from exc
    raise exc


class CanvasDraftViewSet(ViewSet):
    @HasPermission("view-EditChart")
    @action(detail=True, methods=["get"], url_path="yaml")
    def yaml(self, request, resource_type=None, pk=None):
        try:
            data = get_yaml(request, resource_type, _resource_id(pk))
            return Response({"revision": data["revision"], "yaml": data["yaml"]})
        except (DraftAccessDenied, DraftNotFound) as exc:
            _translate(exc)

    @HasPermission("view-EditChart")
    @action(detail=True, methods=["post"], url_path="yaml/preview")
    def preview(self, request, resource_type=None, pk=None):
        try:
            data = preview_yaml(
                request,
                resource_type,
                _resource_id(pk),
                request.data.get("yaml") or request.data.get("yaml_content") or "",
            )
            return Response({"payload": data["payload"], "yaml": data["yaml"]})
        except DraftValidationFailed as exc:
            return Response(
                {"detail": "草稿校验失败", "data": {"errors": exc.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (DraftAccessDenied, DraftNotFound) as exc:
            _translate(exc)

    @HasPermission("view-EditChart")
    @action(detail=True, methods=["post"], url_path="checkpoints")
    def checkpoints(self, request, resource_type=None, pk=None):
        try:
            data = checkpoint(
                request,
                resource_type,
                _resource_id(pk),
                _payload_object(request),
            )
            return Response({"id": data["id"], "payload": data["payload"]})
        except DraftValidationFailed as exc:
            return Response(
                {"detail": "草稿校验失败", "data": {"errors": exc.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (DraftAccessDenied, DraftNotFound) as exc:
            _translate(exc)

    @HasPermission("view-EditChart")
    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, resource_type=None, pk=None):
        try:
            return Response(list_history(request, resource_type, _resource_id(pk)))
        except (DraftAccessDenied, DraftNotFound) as exc:
            _translate(exc)

    @HasPermission("view-EditChart")
    @action(detail=True, methods=["patch"], url_path=r"checkpoints/(?P<checkpoint_id>[^/.]+)")
    def update_checkpoint(self, request, resource_type=None, pk=None, checkpoint_id=None):
        try:
            checkpoint_id = int(checkpoint_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"checkpoint_id": ["必须是整数"]}) from exc
        if "label" not in request.data:
            raise ValidationError({"label": ["必须提供 label"]})
        try:
            data = update_checkpoint_label(
                request,
                resource_type,
                _resource_id(pk),
                checkpoint_id,
                request.data.get("label"),
            )
            return Response(data)
        except DraftValidationFailed as exc:
            return Response(
                {"detail": "草稿校验失败", "data": {"errors": exc.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (DraftAccessDenied, DraftNotFound) as exc:
            _translate(exc)

    @HasPermission("view-EditChart")
    @action(detail=True, methods=["post"], url_path="restore")
    def restore_checkpoint(self, request, resource_type=None, pk=None):
        checkpoint_id = request.data.get("checkpoint_id")
        try:
            checkpoint_id = int(checkpoint_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"checkpoint_id": ["必须是整数"]}) from exc
        try:
            data = restore(
                request,
                resource_type,
                _resource_id(pk),
                checkpoint_id,
            )
            return Response({"id": data["id"], "payload": data["payload"]})
        except (DraftAccessDenied, DraftNotFound) as exc:
            _translate(exc)
