from io import BytesIO

import pandas as pd
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.cmdb.constants.constants import OPERATE, VIEW
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.service_tree import ServiceTreeService
from apps.cmdb.utils.base import format_group_params, format_groups_params, get_current_team_from_request, get_organization_and_children_ids
from apps.cmdb.views.instance import InstanceViewSet
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.utils.web_utils import WebUtils


def _user_groups(request):
    current_team = get_current_team_from_request(request)
    include_children = request.COOKIES.get("include_children") == "1"
    if include_children:
        team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
        return format_groups_params(team_ids)
    return format_group_params(current_team)


class ServiceTreeViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _load_system(self, request, system_uuid: str, operator: str):
        instance = InstanceManage.query_entity_by_uuid(system_uuid)
        if not instance:
            return None, WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        if instance.get("model_id") != "system":
            return None, WebUtils.response_error("仅应用系统支持服务树", status_code=status.HTTP_400_BAD_REQUEST)
        permission_error = self.require_instance_permission(request, instance, operator=operator)
        if permission_error:
            return None, permission_error
        return instance, None

    def _is_visible(self, request):
        return lambda item: self.require_instance_permission(request, item, operator=VIEW) is None

    def _uuid_list(self, raw):
        if raw in (None, ""):
            return []
        if not isinstance(raw, list):
            return None
        return [item for item in raw if str(item).strip()]

    def _hosts_visible(self, request, host_uuids: list[str]):
        wanted = [str(item).strip() for item in host_uuids if str(item).strip()]
        hosts = InstanceManage.query_entity_by_uuids(wanted) or []
        found = {str(item.get("inst_uuid") or ""): item for item in hosts}
        for uuid in wanted:
            host = found.get(uuid)
            if not host or host.get("model_id") != "host":
                return None, WebUtils.response_error("主机不存在", status_code=status.HTTP_400_BAD_REQUEST)
            denied = self.require_instance_permission(request, host, operator=VIEW)
            if denied:
                return None, WebUtils.response_error("主机不可见", status_code=status.HTTP_403_FORBIDDEN)
        return wanted, None

    @action(detail=False, methods=["get"], url_path=r"(?P<system_uuid>.+?)/tree")
    @HasPermission("asset_info-View")
    def tree(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, VIEW)
        if error:
            return error
        return WebUtils.response_success(ServiceTreeService.get_tree(instance, is_visible=self._is_visible(request)))

    @action(detail=False, methods=["get"], url_path=r"(?P<system_uuid>.+?)/hosts")
    @HasPermission("asset_info-View")
    def hosts(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, VIEW)
        if error:
            return error
        node_uuid = request.query_params.get("node_uuid") or system_uuid
        try:
            return WebUtils.response_success(ServiceTreeService.list_node_hosts(instance, node_uuid, is_visible=self._is_visible(request)))
        except ValidationAppException as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/children")
    @HasPermission("asset_info-Add")
    def create_child(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        try:
            result = ServiceTreeService.create_child(
                system=instance,
                parent_uuid=request.data.get("parent_uuid") or system_uuid,
                kind=request.data.get("kind") or "",
                inst_name=request.data.get("inst_name") or "",
                operator=request.user.username,
                allowed_org_ids=InstanceViewSet._get_allowed_org_ids(request),
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/rename")
    @HasPermission("asset_info-Edit")
    def rename(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        try:
            result = ServiceTreeService.rename_node(
                system=instance,
                node_uuid=request.data.get("node_uuid") or "",
                inst_name=request.data.get("inst_name") or "",
                operator=request.user.username,
                user_groups=_user_groups(request),
                roles=request.user.roles,
                allowed_org_ids=InstanceViewSet._get_allowed_org_ids(request),
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/delete_node")
    @HasPermission("asset_info-Delete")
    def delete_node(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        try:
            ServiceTreeService.delete_node(
                system=instance,
                node_uuid=request.data.get("node_uuid") or "",
                operator=request.user.username,
                user_groups=_user_groups(request),
                roles=request.user.roles,
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success({})

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/assign")
    @HasPermission("asset_info-Edit")
    def assign(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        host_uuids = self._uuid_list(request.data.get("host_uuids"))
        if host_uuids is None:
            return WebUtils.response_error("host_uuids 必须是列表", status_code=status.HTTP_400_BAD_REQUEST)
        visible_hosts, denied = self._hosts_visible(request, host_uuids)
        if denied:
            return denied
        try:
            result = ServiceTreeService.assign_hosts(
                system=instance,
                application_uuid=request.data.get("application_uuid") or "",
                host_uuids=visible_hosts,
                operator=request.user.username,
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/transfer")
    @HasPermission("asset_info-Edit")
    def transfer(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        target_uuid = request.data.get("target_app") or ""
        target = InstanceManage.query_entity_by_uuid(target_uuid)
        if not target or self.require_instance_permission(request, target, operator=VIEW) is not None:
            return WebUtils.response_error("目标应用不可见", status_code=status.HTTP_403_FORBIDDEN)
        host_uuids = self._uuid_list(request.data.get("host_uuids"))
        if host_uuids is None:
            return WebUtils.response_error("host_uuids 必须是列表", status_code=status.HTTP_400_BAD_REQUEST)
        visible_hosts, denied = self._hosts_visible(request, host_uuids)
        if denied:
            return denied
        try:
            result = ServiceTreeService.transfer_hosts(
                system=instance,
                source_app=request.data.get("source_app") or "",
                target_app=target_uuid,
                host_uuids=visible_hosts,
                operator=request.user.username,
                target_visible=True,
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/unbind")
    @HasPermission("asset_info-Edit")
    def unbind(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        host_uuids = self._uuid_list(request.data.get("host_uuids"))
        if host_uuids is None:
            return WebUtils.response_error("host_uuids 必须是列表", status_code=status.HTTP_400_BAD_REQUEST)
        visible_hosts, denied = self._hosts_visible(request, host_uuids)
        if denied:
            return denied
        try:
            result = ServiceTreeService.unbind_hosts(
                system=instance,
                application_uuid=request.data.get("application_uuid") or request.data.get("source_app") or "",
                host_uuids=visible_hosts,
                operator=request.user.username,
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/application_systems")
    @HasPermission("asset_info-View")
    def application_systems(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, VIEW)
        if error:
            return error
        app_uuids = self._uuid_list(request.data.get("uuids"))
        if app_uuids is None:
            return WebUtils.response_error("uuids 必须是列表", status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(ServiceTreeService.systems_for_applications(app_uuids))

    @action(detail=False, methods=["post"], url_path=r"(?P<system_uuid>.+?)/import")
    @HasPermission("asset_info-Add")
    def import_tree(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, OPERATE)
        if error:
            return error
        upload = request.FILES.get("file")
        if upload is None:
            return WebUtils.response_error("请上传导入文件", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            rows = _read_import_rows(upload)
            result = ServiceTreeService.import_rows(
                system=instance,
                rows=rows,
                operator=request.user.username,
                allowed_org_ids=InstanceViewSet._get_allowed_org_ids(request),
                is_visible=self._is_visible(request),
            )
        except (ValidationAppException, BaseAppException) as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["get"], url_path=r"(?P<system_uuid>.+?)/export")
    @HasPermission("asset_info-View")
    def export_tree(self, request, system_uuid: str):
        instance, error = self._load_system(request, system_uuid, VIEW)
        if error:
            return error
        rows = ServiceTreeService.export_rows(instance, is_visible=self._is_visible(request))
        frame = pd.DataFrame(rows, columns=["应用系统", "应用", "主机标识"])
        buffer = BytesIO()
        frame.to_excel(buffer, index=False)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="service_tree.xlsx"'
        return response


def _read_import_rows(upload) -> list[dict]:
    name = str(getattr(upload, "name", "") or "").lower()
    payload = upload.read()
    buffer = BytesIO(payload)
    if name.endswith(".csv"):
        frame = pd.read_csv(buffer)
    else:
        frame = pd.read_excel(buffer)
    return frame.fillna("").to_dict("records")
