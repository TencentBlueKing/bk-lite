"""轮播列表的组织可见性、条目校验与播放可用状态。"""

from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.operation_analysis.models.carousel import CAROUSEL_MAX_ITEMS, CAROUSEL_RESOURCE_TYPES, CanvasCarousel, CanvasCarouselItem
from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.services.user_messages import oa_message

CANVAS_MODELS = {
    "dashboard": Dashboard,
    "topology": Topology,
    "architecture": Architecture,
    "screen": Screen,
    "report": Report,
    "networkTopology": NetworkTopology,
}

RESOURCE_TYPE_VALUES = {value for value, _label in CAROUSEL_RESOURCE_TYPES}


def group_id_set(groups) -> set[int]:
    result = set()
    for value in groups or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def normalize_group_list(groups) -> list[int]:
    seen = set()
    ordered = []
    for value in groups or []:
        try:
            group_id = int(value)
        except (TypeError, ValueError):
            continue
        if group_id in seen:
            continue
        seen.add(group_id)
        ordered.append(group_id)
    return ordered


def viewer_org_ids(view, request) -> list[int]:
    """与画布列表同一套当前组织（含子组织开关）范围。"""
    current_team = view._parse_current_team_cookie(request)
    include_children = request.COOKIES.get("include_children", "0") == "1"
    if include_children:
        tree = getattr(request.user, "group_tree", []) or []
        child_ids = view.extract_child_group_ids(tree, current_team)
        normalized = normalize_group_list(child_ids)
        if normalized:
            return normalized
    if not current_team:
        return []
    return [int(current_team)]


def name_conflicts(name: str, groups, *, exclude_id=None) -> bool:
    target = group_id_set(groups)
    if not name or not target:
        return False
    queryset = CanvasCarousel.objects.filter(name=name).only("id", "groups")
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    for row in queryset:
        if group_id_set(row.groups) & target:
            return True
    return False


def _reference_pairs(items):
    pairs = []
    for item in items:
        resource_type = item["resource_type"] if isinstance(item, dict) else item.resource_type
        canvas_id = item["canvas_id"] if isinstance(item, dict) else item.canvas_id
        pairs.append((resource_type, canvas_id))
    return pairs


def playable_item_stats(request, carousels) -> dict[int, dict[str, int]]:
    """列表上的有效张数和有效时长。按画布类型各查一次可见集合，不返回画布名称。"""
    from apps.operation_analysis.services.directory_service import visible_canvas_queryset

    ids_by_type = defaultdict(set)
    for carousel in carousels:
        for item in carousel.items.all():
            if item.resource_type in CANVAS_MODELS:
                ids_by_type[item.resource_type].add(item.canvas_id)
    visible = set()
    for resource_type, canvas_ids in ids_by_type.items():
        visible_ids = visible_canvas_queryset(request, resource_type).filter(id__in=canvas_ids).values_list("id", flat=True)
        visible.update((resource_type, canvas_id) for canvas_id in visible_ids)
    stats = {}
    for carousel in carousels:
        playable = 0
        duration = 0
        for item in carousel.items.all():
            if (item.resource_type, item.canvas_id) not in visible:
                continue
            playable += 1
            duration += carousel.default_dwell_seconds if item.dwell_seconds is None else item.dwell_seconds
        stats[carousel.id] = {"playable_count": playable, "duration_seconds": duration}
    return stats


def load_canvas_visibility(request, items):
    """存在性与目录树可见性各按类型批量查询。

    可见口径与目录树一致：父目录启用，目录和画布都在当前组织范围内。
    """
    from apps.operation_analysis.services.directory_service import visible_canvas_queryset

    ids_by_type = defaultdict(set)
    for resource_type, canvas_id in _reference_pairs(items):
        if resource_type in CANVAS_MODELS:
            ids_by_type[resource_type].add(canvas_id)
    found = {}
    visible = set()
    for resource_type, canvas_ids in ids_by_type.items():
        model = CANVAS_MODELS[resource_type]
        rows = model.objects.filter(id__in=canvas_ids).only("id", "name", "groups")
        for canvas in rows:
            found[(resource_type, canvas.id)] = canvas
        visible_ids = visible_canvas_queryset(request, resource_type).filter(id__in=canvas_ids).values_list("id", flat=True)
        visible.update((resource_type, canvas_id) for canvas_id in visible_ids)
    return found, visible


def ensure_references_visible(request, items) -> None:
    invalid_type = next((resource_type for resource_type, _canvas_id in _reference_pairs(items) if resource_type not in CANVAS_MODELS), None)
    if invalid_type is not None:
        raise ValidationError({"items": oa_message("messages.carousel_resource_type_invalid", "画布类型无效")})
    visible = load_canvas_visibility(request, items)[1]
    for resource_type, canvas_id in _reference_pairs(items):
        if (resource_type, canvas_id) not in visible:
            raise ValidationError({"items": oa_message("messages.carousel_canvas_not_visible", "条目引用的画布不存在或当前组织不可见")})


def _actor_fields(request, *, include_created: bool):
    user = getattr(request, "user", None)
    username = getattr(user, "username", "") or ""
    domain = getattr(user, "domain", "") or "domain.com"
    fields = {
        "updated_by": username[:32],
        "updated_by_domain": domain[:100],
    }
    if include_created:
        fields["created_by"] = username[:32]
        fields["domain"] = domain[:100]
    return fields


def _reject_duplicate_canvas():
    raise ValidationError({"items": oa_message("messages.carousel_item_duplicate", "同一张画布不能重复加入")})


def _validate_item_payloads(items):
    if len(items) > CAROUSEL_MAX_ITEMS:
        raise ValidationError({"items": oa_message("messages.carousel_item_limit", "每个轮播列表最多 50 个条目")})
    seen_ids = set()
    seen_canvases = set()
    for item in items:
        item_id = item.get("id")
        if item_id is not None:
            if item_id in seen_ids:
                _reject_duplicate_canvas()
            seen_ids.add(item_id)
        pair = (item.get("resource_type"), item.get("canvas_id"))
        if pair in seen_canvases:
            _reject_duplicate_canvas()
        seen_canvases.add(pair)


def replace_carousel_items(request, carousel: CanvasCarousel, items: list[dict]) -> None:
    _validate_item_payloads(items)
    existing = {item.id: item for item in carousel.items.all()}
    changed = []
    kept_ids = []
    for payload in items:
        item_id = payload.get("id")
        current = existing.get(item_id) if item_id in existing else None
        reference_changed = current is None or current.resource_type != payload["resource_type"] or current.canvas_id != payload["canvas_id"]
        if reference_changed:
            changed.append(payload)
        if current is not None:
            kept_ids.append(current.id)
    if changed:
        ensure_references_visible(request, changed)

    carousel.items.exclude(id__in=kept_ids).delete()
    for position, payload in enumerate(items):
        item_id = payload.get("id")
        current = existing.get(item_id) if item_id in existing else None
        dwell_seconds = payload.get("dwell_seconds")
        if current is None:
            CanvasCarouselItem.objects.create(
                carousel=carousel,
                resource_type=payload["resource_type"],
                canvas_id=payload["canvas_id"],
                dwell_seconds=dwell_seconds,
                position=position,
            )
            continue
        current.resource_type = payload["resource_type"]
        current.canvas_id = payload["canvas_id"]
        current.dwell_seconds = dwell_seconds
        current.position = position
        current.save(update_fields=["resource_type", "canvas_id", "dwell_seconds", "position"])


@transaction.atomic
def create_carousel(request, validated: dict) -> CanvasCarousel:
    items = validated.pop("items", [])
    _validate_item_payloads(items)
    ensure_references_visible(request, items)
    if name_conflicts(validated["name"], validated["groups"]):
        raise ValidationError({"name": oa_message("messages.carousel_name_conflict", "同一组织内已有同名轮播列表")})
    carousel = CanvasCarousel.objects.create(**validated, **_actor_fields(request, include_created=True))
    CanvasCarouselItem.objects.bulk_create(
        [
            CanvasCarouselItem(
                carousel=carousel,
                resource_type=payload["resource_type"],
                canvas_id=payload["canvas_id"],
                dwell_seconds=payload.get("dwell_seconds"),
                position=position,
            )
            for position, payload in enumerate(items)
        ]
    )
    return carousel


def viewer_org_ids_from_request(request) -> list[int]:
    """请求级组织范围。ViewSet 与服务共用 cookie 语义。"""
    from apps.core.utils.viewset_utils import AuthViewSet

    return viewer_org_ids(AuthViewSet, request)


@transaction.atomic
def update_carousel(request, carousel: CanvasCarousel, validated: dict) -> CanvasCarousel:
    locked = CanvasCarousel.objects.select_for_update().get(pk=carousel.pk)
    items = validated.pop("items", None)
    next_name = validated.get("name", locked.name)
    next_groups = validated.get("groups", locked.groups)
    if name_conflicts(next_name, next_groups, exclude_id=locked.id):
        raise ValidationError({"name": oa_message("messages.carousel_name_conflict", "同一组织内已有同名轮播列表")})
    for field, value in validated.items():
        setattr(locked, field, value)
    for field, value in _actor_fields(request, include_created=False).items():
        setattr(locked, field, value)
    locked.save()
    if items is not None:
        replace_carousel_items(request, locked, items)
    return locked


@transaction.atomic
def append_carousel_item(request, carousel: CanvasCarousel, payload: dict) -> CanvasCarouselItem:
    locked = CanvasCarousel.objects.select_for_update().get(pk=carousel.pk)
    if locked.items.count() >= CAROUSEL_MAX_ITEMS:
        raise ValidationError({"items": oa_message("messages.carousel_item_limit", "每个轮播列表最多 50 个条目")})
    if locked.items.filter(resource_type=payload["resource_type"], canvas_id=payload["canvas_id"]).exists():
        _reject_duplicate_canvas()
    ensure_references_visible(request, [payload])
    last = locked.items.order_by("-position", "-id").only("position").first()
    position = 0 if last is None else last.position + 1
    item = CanvasCarouselItem.objects.create(
        carousel=locked,
        resource_type=payload["resource_type"],
        canvas_id=payload["canvas_id"],
        dwell_seconds=payload.get("dwell_seconds"),
        position=position,
    )
    for field, value in _actor_fields(request, include_created=False).items():
        setattr(locked, field, value)
    locked.save(update_fields=["updated_by", "updated_by_domain", "updated_at"])
    return item


def describe_carousel(carousel: CanvasCarousel, request) -> dict:
    rows = list(carousel.items.all())
    canvases, visible_keys = load_canvas_visibility(request, rows)
    items = []
    for item in rows:
        canvas = canvases.get((item.resource_type, item.canvas_id))
        exists = canvas is not None
        visible = (item.resource_type, item.canvas_id) in visible_keys
        payload = {
            "id": item.id,
            "resource_type": item.resource_type,
            "canvas_id": item.canvas_id,
            "position": item.position,
            "dwell_seconds": item.dwell_seconds,
            "resolved_dwell_seconds": item.dwell_seconds if item.dwell_seconds is not None else carousel.default_dwell_seconds,
            "exists": exists,
            "visible": visible,
            "available": visible,
        }
        if visible and canvas is not None:
            payload["canvas_name"] = canvas.name
            payload["canvas_group_ids"] = sorted(group_id_set(canvas.groups))
        items.append(payload)
    return {
        "id": carousel.id,
        "name": carousel.name,
        "desc": carousel.desc or "",
        "groups": normalize_group_list(carousel.groups),
        "default_dwell_seconds": carousel.default_dwell_seconds,
        "created_by": carousel.created_by,
        "updated_by": carousel.updated_by,
        "created_at": carousel.created_at,
        "updated_at": carousel.updated_at,
        "items": items,
    }
