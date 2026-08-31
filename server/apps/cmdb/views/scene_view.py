from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.cmdb.constants.field_constraints import TAG_ATTR_ID
from apps.cmdb.models.scene_view import SceneView
from apps.cmdb.serializers.scene_view import SceneViewSerializer
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.scene_view import (
    build_visible_scene_query,
    can_edit_scene,
    can_publish_global,
    can_publish_org,
    collect_all_scene_instances,
    execute_scene_query,
    merge_model_workbooks,
    user_org_ids,
)
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils

_MAX_PAGE_SIZE = 200
_DEFAULT_PAGE_SIZE = 20
_MAX_INST_NAME_SEARCH = 128


def _transport_instance(instance):
    return {key: value for key, value in dict(instance or {}).items() if key not in {"_id", "_labels"}}


def _model_table_columns(model_id: str, creator: str) -> list[dict]:
    attrs = ModelManage.search_model_attr(model_id) or []
    info = InstanceManage.get_info(model_id, creator)
    keys = (info or {}).get("show_fields") or [item.get("attr_id") for item in attrs]
    attr_map = {item.get("attr_id"): item for item in attrs}
    columns = []
    for key in keys:
        if not key:
            continue
        attr = attr_map.get(key) or {}
        columns.append(
            {
                "attr_id": key,
                "attr_name": attr.get("attr_name") or key,
                "attr_type": attr.get("attr_type") or "str",
            }
        )
    return columns


def _union_tag_options(model_ids: list[str]) -> list[str]:
    """标签候选项只来自模型上 attr_type=tag 的 option.options，不扫实例。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for model_id in model_ids:
        attrs = ModelManage.search_model_attr(model_id) or []
        tag_field = next(
            (item for item in attrs if item.get("attr_id") == TAG_ATTR_ID and item.get("attr_type") == "tag"),
            None,
        )
        if not tag_field:
            continue
        option = tag_field.get("option") or {}
        rows = option.get("options") if isinstance(option, dict) else []
        for row in rows or []:
            key = str((row or {}).get("key") or "").strip()
            value = str((row or {}).get("value") or "").strip()
            if not key or not value:
                continue
            token = f"{key}:{value}"
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return ordered


class SceneViewViewSet(viewsets.ModelViewSet):
    queryset = SceneView.objects.all().order_by("-updated_at")
    serializer_class = SceneViewSerializer
    http_method_names = ["get", "post", "put", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        query = build_visible_scene_query(
            username=user.username,
            domain=getattr(user, "domain", "") or "",
            org_ids=user_org_ids(user),
        )
        return SceneView.objects.filter(query).order_by("-updated_at")

    def _log_saved(self, scene: SceneView) -> None:
        logger.info(
            "event=scene_view_saved scene_id=%s visibility=%s model_count=%s",
            scene.id,
            scene.visibility,
            len(scene.model_ids or []),
        )

    def _forbidden_visibility(self, request, visibility: str):
        if visibility == SceneView.Visibility.ORGANIZATION and not can_publish_org(request.user):
            return WebUtils.response_error("没有组织共享权限", status_code=status.HTTP_403_FORBIDDEN)
        if visibility == SceneView.Visibility.GLOBAL and not can_publish_global(request.user):
            return WebUtils.response_error("没有全局视图权限", status_code=status.HTTP_403_FORBIDDEN)
        return None

    def _save_visibility_fields(self, request, visibility: str, existing: SceneView | None = None) -> dict:
        if visibility == SceneView.Visibility.ORGANIZATION:
            if existing and existing.visibility == SceneView.Visibility.ORGANIZATION and existing.organization:
                return {"visibility": visibility, "organization": existing.organization}
            team = get_current_team(request)
            try:
                org_id = int(team)
            except (TypeError, ValueError):
                raise ValueError("组织共享需要当前组织")
            return {"visibility": visibility, "organization": org_id}
        return {"visibility": visibility, "organization": None}

    @HasPermission("asset_info-View")
    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return WebUtils.response_success(
            {
                "count": len(serializer.data),
                "results": serializer.data,
                "capabilities": {
                    "can_org_share": can_publish_org(request.user),
                    "can_global": can_publish_global(request.user),
                },
            }
        )

    @HasPermission("asset_info-View")
    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return WebUtils.response_success(serializer.data)

    @HasPermission("asset_info-View")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        visibility = serializer.validated_data.get("visibility") or SceneView.Visibility.PERSONAL
        denied = self._forbidden_visibility(request, visibility)
        if denied:
            return denied
        try:
            extra = self._save_visibility_fields(request, visibility)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        scene = serializer.save(
            created_by=request.user.username,
            updated_by=request.user.username,
            domain=getattr(request.user, "domain", "") or "",
            updated_by_domain=getattr(request.user, "domain", "") or "",
            **extra,
        )
        self._log_saved(scene)
        return WebUtils.response_success(self.get_serializer(scene).data)

    @HasPermission("asset_info-View")
    def update(self, request, *args, **kwargs):
        scene = self.get_object()
        if not can_edit_scene(request.user, scene):
            return WebUtils.response_error("不能修改他人的视图", status_code=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(scene, data=request.data)
        serializer.is_valid(raise_exception=True)
        visibility = serializer.validated_data.get("visibility") or SceneView.Visibility.PERSONAL
        denied = self._forbidden_visibility(request, visibility)
        if denied:
            return denied
        try:
            extra = self._save_visibility_fields(request, visibility, existing=scene)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        scene = serializer.save(
            updated_by=request.user.username,
            updated_by_domain=getattr(request.user, "domain", "") or "",
            **extra,
        )
        self._log_saved(scene)
        return WebUtils.response_success(self.get_serializer(scene).data)

    @HasPermission("asset_info-View")
    def destroy(self, request, *args, **kwargs):
        scene = self.get_object()
        if not can_edit_scene(request.user, scene):
            return WebUtils.response_error("不能删除他人的视图", status_code=status.HTTP_403_FORBIDDEN)
        scene_id = scene.id
        visibility = scene.visibility
        scene.delete()
        logger.info(
            "event=scene_view_deleted scene_id=%s visibility=%s model_count=%s",
            scene_id,
            visibility,
            0,
        )
        return WebUtils.response_success({})

    @action(methods=["post"], detail=True)
    @HasPermission("asset_info-View")
    def execute(self, request, *args, **kwargs):
        scene = self.get_object()
        try:
            page = _parse_positive_int(request.data.get("page", 1), default=1)
            page_size = _parse_positive_int(
                request.data.get("page_size", _DEFAULT_PAGE_SIZE),
                default=_DEFAULT_PAGE_SIZE,
                max_value=_MAX_PAGE_SIZE,
            )
            pagination = _parse_model_pagination(request.data.get("pagination"))
            searches = _parse_model_searches(request.data.get("searches"))
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        result = execute_scene_query(
            model_ids=scene.model_ids or [],
            tags=scene.tags or [],
            tag_match=scene.tag_match or SceneView.TagMatch.AND,
            creator=request.user.username,
            page=page,
            page_size=page_size,
            pagination=pagination,
            searches=searches,
            permission_map_loader=lambda model_id: CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id),
        )
        models = [
            {
                "model_id": item["model_id"],
                "count": item["count"],
                "insts": [_transport_instance(inst) for inst in item.get("insts") or []],
                "columns": _model_table_columns(item["model_id"], request.user.username),
            }
            for item in result.get("models") or []
        ]
        return WebUtils.response_success({"total": result.get("total", 0), "models": models})

    @action(methods=["get"], detail=False)
    @HasPermission("asset_info-View")
    def tag_options(self, request, *args, **kwargs):
        raw = request.query_params.get("model_ids") or ""
        model_ids = [item.strip() for item in raw.split(",") if item.strip()]
        return WebUtils.response_success({"tags": _union_tag_options(model_ids)})

    @action(methods=["post"], detail=True, url_path="save_as")
    @HasPermission("asset_info-View")
    def save_as(self, request, *args, **kwargs):
        source = self.get_object()
        name = str(request.data.get("name") or "").strip() or f"{source.name}"
        copy = SceneView.objects.create(
            name=name,
            visibility=SceneView.Visibility.PERSONAL,
            organization=None,
            model_ids=list(source.model_ids or []),
            tags=list(source.tags or []),
            tag_match=source.tag_match or SceneView.TagMatch.AND,
            created_by=request.user.username,
            updated_by=request.user.username,
            domain=getattr(request.user, "domain", "") or "",
            updated_by_domain=getattr(request.user, "domain", "") or "",
        )
        self._log_saved(copy)
        return WebUtils.response_success(self.get_serializer(copy).data)

    @action(methods=["post"], detail=True)
    @HasPermission("asset_info-View")
    def export(self, request, *args, **kwargs):
        scene = self.get_object()

        def permission_map_loader(model_id):
            return CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id)

        hits = collect_all_scene_instances(
            model_ids=scene.model_ids or [],
            tags=scene.tags or [],
            tag_match=scene.tag_match or SceneView.TagMatch.AND,
            creator=request.user.username,
            permission_map_loader=permission_map_loader,
        )
        if not hits["total"]:
            return WebUtils.response_error("没有匹配的实例", status_code=status.HTTP_400_BAD_REQUEST)

        sheets = []
        for item in hits["models"]:
            ids = [inst.get("_id") for inst in item.get("insts") or [] if inst.get("_id") is not None]
            if not ids:
                continue
            columns = _model_table_columns(item["model_id"], request.user.username)
            attr_list = [col["attr_id"] for col in columns]
            payload = InstanceManage.inst_export(
                model_id=item["model_id"],
                ids=ids,
                permissions_map=permission_map_loader(item["model_id"]),
                creator=request.user.username,
                attr_list=attr_list,
            )
            sheets.append((item["model_id"], payload))
        if not sheets:
            return WebUtils.response_error("没有匹配的实例", status_code=status.HTTP_400_BAD_REQUEST)

        workbook = merge_model_workbooks(sheets)
        logger.info(
            "event=scene_view_exported scene_id=%s visibility=%s model_count=%s hit_total=%s",
            scene.id,
            scene.visibility,
            len(sheets),
            hits["total"],
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f"attachment;filename=scene_view_{scene.id}.xlsx"
        return response


def _parse_model_pagination(raw) -> dict[str, tuple[int, int]]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("分页参数无效")
    parsed: dict[str, tuple[int, int]] = {}
    for model_id, spec in raw.items():
        key = str(model_id or "").strip()
        if not key:
            continue
        if not isinstance(spec, dict):
            raise ValueError("分页参数无效")
        page = _parse_positive_int(spec.get("page", 1), default=1)
        page_size = _parse_positive_int(
            spec.get("page_size", _DEFAULT_PAGE_SIZE),
            default=_DEFAULT_PAGE_SIZE,
            max_value=_MAX_PAGE_SIZE,
        )
        parsed[key] = (page, page_size)
    return parsed


def _parse_model_searches(raw) -> dict[str, object]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("搜索参数无效")
    parsed: dict[str, object] = {}
    for model_id, spec in raw.items():
        key = str(model_id or "").strip()
        if not key:
            continue
        if isinstance(spec, str):
            text = spec.strip()
            if text:
                parsed[key] = text[:_MAX_INST_NAME_SEARCH]
            continue
        if isinstance(spec, dict):
            parsed[key] = spec
    return parsed


def _parse_positive_int(value, *, default, max_value=None):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("页码参数无效") from exc
    if parsed < 1:
        raise ValueError("页码参数无效")
    if max_value is not None:
        return min(parsed, max_value)
    return parsed
