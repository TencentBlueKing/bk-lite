from django.db import transaction

from apps.core.utils.team_utils import get_current_team
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.models.canvas_draft import CanvasDraftCheckpoint
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY
from apps.operation_analysis.services.canvas_draft.codec import canvas_to_payload, decode_yaml, encode_yaml
from apps.operation_analysis.services.canvas_draft.constants import CHECKPOINT_LABEL_MAX_LENGTH, HISTORY_LIMIT
from apps.operation_analysis.services.canvas_draft.errors import DraftAccessDenied, DraftNotFound, DraftValidationFailed
from apps.operation_analysis.services.canvas_draft.validation import validate_projectable
from apps.operation_analysis.services.import_export.export_service import ExportService


def _username(user) -> str:
    return getattr(user, "username", "") or ""


def resolve_canvas(request, resource_type: str, resource_id: int):
    meta = CANVAS_TYPE_REGISTRY.get(resource_type)
    if meta is None:
        raise DraftNotFound()
    canvas = meta.model.objects.filter(pk=resource_id).first()
    if canvas is None:
        raise DraftNotFound()
    if getattr(canvas, "is_build_in", False):
        raise DraftAccessDenied()
    team = get_current_team(request)
    visible = meta.model.objects.filter(pk=resource_id)
    if not visible.filter(build_json_membership_query(visible, "groups", [team])).exists():
        raise DraftAccessDenied()
    return canvas, ObjectType(resource_type)


def _visible_datasource_maps(request) -> tuple[dict[str, int], dict[int, str]]:
    team = get_current_team(request)
    queryset = DataSourceAPIModel.objects.all()
    queryset = queryset.filter(build_json_membership_query(queryset, "groups", [team]))
    key_to_id: dict[str, int] = {}
    id_to_key: dict[int, str] = {}
    for datasource in queryset:
        key = ExportService.generate_business_key(datasource, ObjectType.DATASOURCE)
        key_to_id[key] = datasource.id
        id_to_key[datasource.id] = key
    return key_to_id, id_to_key


def _latest_checkpoint(resource_type: str, resource_id: int, username: str) -> CanvasDraftCheckpoint | None:
    return (
        CanvasDraftCheckpoint.objects.filter(
            resource_type=resource_type,
            resource_id=resource_id,
            username=username,
        )
        .order_by("-id")
        .first()
    )


def _yaml_context(canvas, object_type: ObjectType, request, username: str) -> dict:
    frame = _latest_checkpoint(object_type.value, canvas.pk, username)
    payload = frame.payload if frame else canvas_to_payload(canvas, object_type)
    revision = frame.id if frame else 0
    _, id_to_key = _visible_datasource_maps(request)
    yaml_text = encode_yaml(canvas, payload, object_type, id_to_key, {})
    return {"revision": revision, "payload": payload, "yaml": yaml_text}


def get_yaml(request, resource_type: str, resource_id: int) -> dict:
    canvas, object_type = resolve_canvas(request, resource_type, resource_id)
    return _yaml_context(canvas, object_type, request, _username(request.user))


def preview_yaml(request, resource_type: str, resource_id: int, yaml_content: str) -> dict:
    canvas, object_type = resolve_canvas(request, resource_type, resource_id)
    key_to_id, id_to_key = _visible_datasource_maps(request)
    payload = decode_yaml(yaml_content, canvas=canvas, object_type=object_type, datasource_key_to_id=key_to_id)
    yaml_text = encode_yaml(canvas, payload, object_type, id_to_key, {})
    return {"payload": payload, "yaml": yaml_text}


def checkpoint(request, resource_type: str, resource_id: int, payload: dict) -> dict:
    canvas, object_type = resolve_canvas(request, resource_type, resource_id)
    username = _username(request.user)
    view_sets = payload.get("view_sets", canvas.view_sets)
    validate_projectable(object_type, view_sets, filters=payload.get("filters"))
    stored = canvas_to_payload(canvas, object_type)
    stored.update({key: payload[key] for key in stored if key in payload})
    stored["view_sets"] = view_sets
    with transaction.atomic():
        frame = CanvasDraftCheckpoint.objects.create(
            resource_type=resource_type,
            resource_id=resource_id,
            username=username,
            payload=stored,
        )
        stale_ids = list(
            CanvasDraftCheckpoint.objects.filter(
                resource_type=resource_type,
                resource_id=resource_id,
                username=username,
            )
            .order_by("-id")
            .values_list("id", flat=True)[HISTORY_LIMIT:]
        )
        if stale_ids:
            CanvasDraftCheckpoint.objects.filter(id__in=stale_ids).delete()
    return {"id": frame.id, "payload": stored}


def restore(request, resource_type: str, resource_id: int, checkpoint_id: int) -> dict:
    canvas, object_type = resolve_canvas(request, resource_type, resource_id)
    username = _username(request.user)
    frame = CanvasDraftCheckpoint.objects.filter(
        id=checkpoint_id,
        resource_type=resource_type,
        resource_id=resource_id,
        username=username,
    ).first()
    if frame is None:
        raise DraftNotFound()
    return {"id": frame.id, "payload": frame.payload}


def list_history(request, resource_type: str, resource_id: int) -> list[dict]:
    canvas, object_type = resolve_canvas(request, resource_type, resource_id)
    username = _username(request.user)
    _, id_to_key = _visible_datasource_maps(request)
    frames = CanvasDraftCheckpoint.objects.filter(
        resource_type=resource_type,
        resource_id=resource_id,
        username=username,
    ).order_by(
        "-id"
    )[:HISTORY_LIMIT]
    return [
        {
            "id": frame.id,
            "label": frame.label or "",
            "created_at": frame.created_at,
            "yaml": encode_yaml(canvas, frame.payload, object_type, id_to_key, {}),
        }
        for frame in frames
    ]


def update_checkpoint_label(
    request,
    resource_type: str,
    resource_id: int,
    checkpoint_id: int,
    label,
) -> dict:
    resolve_canvas(request, resource_type, resource_id)
    username = _username(request.user)
    frame = CanvasDraftCheckpoint.objects.filter(
        id=checkpoint_id,
        resource_type=resource_type,
        resource_id=resource_id,
        username=username,
    ).first()
    if frame is None:
        raise DraftNotFound()
    if label is None:
        normalized = ""
    elif not isinstance(label, str):
        raise DraftValidationFailed([{"field": "label", "message": "label 必须是字符串"}])
    else:
        normalized = label.strip()[:CHECKPOINT_LABEL_MAX_LENGTH]
    frame.label = normalized
    frame.save(update_fields=["label", "updated_at"])
    return {"id": frame.id, "label": frame.label}


def delete_for_resource(resource_type: str, resource_id: int) -> None:
    CanvasDraftCheckpoint.objects.filter(resource_type=resource_type, resource_id=resource_id).delete()
