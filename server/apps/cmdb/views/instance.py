from django.http import HttpResponse, JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.cmdb.constants.constants import NETWORK_TOPO_DEFAULT_HOP, NETWORK_TOPO_MAX_HOP, OPERATE, PERMISSION_INSTANCES, VIEW
from apps.cmdb.instance_ops.extensions import get_instance_enterprise_extension
from apps.cmdb.models.change_record import INSTANCE_EDIT_CORRECTABLE_SCENARIOS, ORDINARY_ATTRIBUTE_CHANGE
from apps.cmdb.serializers.application_resource_overview import ApplicationResourceEntrySerializer, ApplicationResourceTopologyQuerySerializer
from apps.cmdb.serializers.k8s_resource_overview import (
    K8sLayerQuerySerializer,
    K8sPageQuerySerializer,
    K8sResourceKindSerializer,
    K8sResourceListQuerySerializer,
)
from apps.cmdb.services.application_resource_overview import ApplicationResourceOverviewService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.k8s_resource_overview import K8sResourceOverviewService
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.model_visibility import BusinessModelVisibility
from apps.cmdb.services.module_push import CmdbToMonitorPushService, build_cmdb_push_actor_scope
from apps.cmdb.services.rack_room import get_rack_layout, get_room_layout, list_racks_grouped_by_room
from apps.cmdb.services.topology_theme import get_topo_themes
from apps.cmdb.utils.base import format_group_params, format_groups_params, get_current_team_from_request, get_organization_and_children_ids
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.current_team_scope import resolve_assignable_organization_ids
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from apps.system_mgmt.utils.group_utils import GroupUtils


class InstanceViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    @staticmethod
    def _transport_instance(instance):
        """对外响应剥离图内部字段。"""
        return {key: value for key, value in dict(instance or {}).items() if key not in {"_id", "_labels"}}

    K8S_CHILD_MODELS = ("k8s_namespace", "k8s_workload", "k8s_pod", "k8s_node")

    @staticmethod
    def _is_instance_model_visible(instance: dict) -> bool:
        model_id = instance.get("model_id")
        if not model_id:
            return True
        return BusinessModelVisibility.is_visible(ModelManage.search_model_info(model_id))

    @staticmethod
    def _is_model_visible(model_id: str) -> bool:
        return BusinessModelVisibility.is_visible(ModelManage.search_model_info(model_id))

    def _k8s_resource_context(self, request, cluster_uuid):
        instance = InstanceManage.query_entity_by_uuid(cluster_uuid)
        if not instance:
            return None, None, WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        if instance.get("model_id") != "k8s_cluster":
            return None, None, WebUtils.response_error("实例不是 k8s_cluster", status_code=status.HTTP_400_BAD_REQUEST)
        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return None, None, permission_error
        permission_maps = {model_id: CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id) for model_id in self.K8S_CHILD_MODELS}
        return instance, permission_maps, None

    @staticmethod
    def _get_allowed_org_ids(request) -> list[int]:
        # 超级管理员：不按当前组织裁剪，通过 system_mgmt NATS 取该用户可分配的组织。
        if getattr(request.user, "is_superuser", False):
            return list(resolve_assignable_organization_ids(request))

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        user_group_ids = [i["id"] for i in request.user.group_list]

        allowed_org_ids = GroupUtils.get_user_authorized_child_groups(
            user_group_list=user_group_ids,
            target_group_id=current_team,
            include_children=include_children,
        )
        if not allowed_org_ids:
            raise BaseAppException("抱歉！您没有该组织的权限或组织选择无效")
        return allowed_org_ids

    def _layout_user_groups(self, request):
        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
            return format_groups_params(team_ids)
        return format_group_params(current_team)

    def _attach_layout_item_permissions(self, request, items, default_model=None):
        if not items:
            return
        if getattr(request.user, "is_superuser", False):
            for item in items:
                item["permission"] = [VIEW, OPERATE]
                item.pop("_creator", None)
            return
        by_model = {}
        for item in items:
            model_id = item.get("model_id") or default_model or ""
            by_model.setdefault(model_id, []).append(item)
        for model_id, group in by_model.items():
            permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)
            for item in group:
                item.setdefault("organization", [])
            self.add_instance_permission(group, permissions_map, request.user.username)
            for item in group:
                item.pop("_creator", None)

    def _transport_layout_instance(self, instance):
        transported = self._transport_instance(instance)
        transported.pop("_creator", None)
        return transported

    @staticmethod
    def _parse_positive_int(value, field_name, default):
        if value in (None, ""):
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} 必须是整数")
        if parsed < 1:
            raise ValueError(f"{field_name} 必须大于等于 1")
        return parsed

    @staticmethod
    def _normalize_query_list(query_list):
        """
        Normalize request.data['query_list'] into a flat list of valid query dicts.

        Front-end request format stays unchanged:
        - query_list can be a dict (single condition) or list (multiple conditions)
        - list items can be dicts or nested lists (legacy wrapping)

        The graph layer will AND all conditions by default (param_type="AND").
        """
        if query_list is None:
            return []

        if isinstance(query_list, dict):
            query_list = [query_list]

        if not isinstance(query_list, list):
            return []

        normalized = []

        def add_condition(item):
            if not item or not isinstance(item, dict):
                return

            field = item.get("field")
            _type = item.get("type")
            if not field or not _type:
                return

            if _type == "time":
                start = item.get("start")
                end = item.get("end")
                if not start or not end:
                    return
                normalized.append({"field": field, "type": _type, "start": start, "end": end})
                return

            if item.get("accurate") is True:
                normalized.append(
                    {
                        "field": field,
                        "type": _type,
                        "value": item.get("value"),
                        "accurate": True,
                    }
                )
                return

            if "value" not in item:
                return

            value = item.get("value")
            if value is None:
                return
            if isinstance(value, str) and value == "":
                return
            if isinstance(value, list) and not value:
                return

            normalized.append({"field": field, "type": _type, "value": value})

        def walk(node):
            if node is None:
                return
            if isinstance(node, dict):
                add_condition(node)
                return
            if isinstance(node, list):
                for sub in node:
                    walk(sub)

        walk(query_list)
        return normalized

    # -------------------------------------------------------------------------
    # Permission methods - delegated to CmdbPermissionMixin
    # These wrappers maintain backward compatibility with existing code.
    # -------------------------------------------------------------------------

    def check_creator_and_organizations(self, request, instance):
        """Check if user is creator with org access. Delegates to mixin."""
        return self.is_creator_with_org_access(request, instance)

    def organizations(self, request, instance):
        """Get user's organizations for instance. Delegates to mixin."""
        return self.get_user_organizations(request, instance, "organization")

    @staticmethod
    def add_instance_permission(instances, permission_instances_map, creator):
        """
        给实例添加权限信息
        :param creator: 创建人
        :param instances : 实例
        :param permission_instances_map: 权限数据
        {4: {'inst_names': ['VC-同名'], 'permission_instances_map': {'VC-同名': ['View']}, 'team': []},
        6: {'inst_names': ['VC3'], 'permission_instances_map': {'VC3': ['View', 'Operate']}, 'team': []}}
        一条数据可以在多个组织下，每个组织可以配置不同的实例权限
        需要把所有组织的实例权限合并后，赋值给实例 因为有可能组织A只有查看权限，组织B有操作权限，所以要合并实例在多个组织下的权限再赋值
        """

        organizations_instances_map = CmdbRulesFormatUtil.format_organizations_instances_map(permission_instances_map)
        for instance in instances:
            _creator = instance.get("_creator")
            if _creator == creator:
                instance["permission"] = [VIEW, OPERATE]
                continue

            instance["permission"] = []

            organizations = instance["organization"]
            # 多个实力权限都可以配置一样
            for organization in organizations:
                if organization not in organizations_instances_map:
                    continue
                for _permission in organizations_instances_map[organization]["permission"]:
                    if _permission not in instance["permission"]:
                        instance["permission"].append(_permission)

            permission_data = organizations_instances_map.get(instance["inst_name"])
            if not permission_data:
                continue

            organization_permission_map = permission_data.get("organization_permission_map", {})
            for organization in organizations:
                for _permission in organization_permission_map.get(organization, set()):
                    if _permission not in instance["permission"]:
                        instance["permission"].append(_permission)

    @HasPermission("asset_info-View")
    @action(methods=["post"], detail=False)
    def search(self, request):
        """
        查询实例权限：
        1. 若前端不做组织筛选，默认查询组织 get_current_team(request)
            若做组织筛选，则查询所选组织
        2. 用户所在的组织，and （组织单独设置的实例权限过滤条件 or 创建人是我）
        3. 若有额外的字段过滤条件，则在上述基础上做and过滤

        请求参数:
            - model_id: 模型ID（必填）
            - query_list: 查询条件列表（可选）
            - page: 页码（可选，默认1）
            - page_size: 每页大小（可选，默认10）
            - order: 排序字段（可选）
            - case_sensitive: 是否区分大小写（可选，默认True，仅对str*类型有效）
        """
        model_id = request.data.get("model_id")
        if not model_id:
            return WebUtils.response_error("model_id不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        if not self._is_model_visible(model_id):
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)

        query_list = self._normalize_query_list(request.data.get("query_list", []))
        try:
            page = self._parse_positive_int(request.data.get("page", 1), field_name="page", default=1)
            page_size = self._parse_positive_int(request.data.get("page_size", 10), field_name="page_size", default=10)
        except ValueError as err:
            return WebUtils.response_error(error_message=str(err), status_code=status.HTTP_400_BAD_REQUEST)

        case_sensitive = request.data.get("case_sensitive", True)
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id)
        instance_list, count = InstanceManage.instance_list(
            model_id=model_id,
            params=query_list,
            page=page,
            page_size=page_size,
            order=request.data.get("order", ""),
            permission_map=permissions_map,
            creator=request.user.username,
            case_sensitive=case_sensitive,
        )
        self.add_instance_permission(
            instances=instance_list,
            permission_instances_map=permissions_map,
            creator=request.user.username,
        )
        return WebUtils.response_success(dict(insts=[self._transport_instance(item) for item in instance_list], count=count))

    @HasPermission("asset_info-View")
    def retrieve(self, request, pk: str):
        if str(pk).isdigit():
            return WebUtils.response_error("请使用 inst_uuid 定位实例，不再支持数字 ID", status_code=status.HTTP_400_BAD_REQUEST)
        instance = InstanceManage.query_entity_by_uuid(pk)
        if not instance or not self._is_instance_model_visible(instance):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回
            instance["permission"] = [VIEW, OPERATE]
            return WebUtils.response_success(self._transport_instance(instance))

        organizations = self.organizations(request, instance)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        model_id = instance["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=instance,
        )
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        self.add_instance_permission(
            instances=[instance],
            permission_instances_map=permissions_map,
            creator=request.user.username,
        )
        return WebUtils.response_success(self._transport_instance(instance))

    @HasPermission("asset_info-Edit")
    @action(methods=["post"], detail=True, url_path="push_to_monitor")
    def push_to_monitor(self, request, pk=None):
        """显式推送到监控：无级联，带 causation。"""
        if str(pk).isdigit():
            return WebUtils.response_error("请使用 inst_uuid 定位实例，不再支持数字 ID", status_code=status.HTTP_400_BAD_REQUEST)
        instance = InstanceManage.query_entity_by_uuid(pk)
        if not instance or not self._is_instance_model_visible(instance):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if not self.check_creator_and_organizations(request, instance):
            organizations = self.organizations(request, instance)
            if not organizations:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)
            has_permission = self.check_instance_permission(request, instance, operator=OPERATE)
            if not has_permission:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        actor_scope = build_cmdb_push_actor_scope(request)
        try:
            result = CmdbToMonitorPushService.push_instance(pk, actor_scope=actor_scope)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("[push_to_monitor] failed inst_uuid=%s", pk)
            return WebUtils.response_error("推送到监控失败", status_code=status.HTTP_502_BAD_GATEWAY)
        return WebUtils.response_success(result)

    # ---- 附件/图片文件（企业版；社区版返回未启用） -----------------------

    def _check_instance_read_permission(self, request, instance) -> bool:
        """实例读权限判定（与 retrieve 一致），供附件下载校权复用。"""
        if self.check_creator_and_organizations(request, instance):
            return True
        if not self.organizations(request, instance):
            return False
        model_id = instance["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)
        return CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=instance,
        )

    @HasPermission("asset_info-Add")
    @action(detail=False, methods=["post"], url_path="upload_file")
    def upload_file(self, request):
        """附件/图片预上传：校验后存入对象存储，返回文件元数据（含 file_id）。"""
        model_id = request.data.get("model_id")
        attr_id = request.data.get("attr_id")
        uploaded = request.FILES.get("file")
        if not model_id or not attr_id:
            return WebUtils.response_error("model_id 和 attr_id 不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        if not uploaded:
            return WebUtils.response_error("未接收到文件", status_code=status.HTTP_400_BAD_REQUEST)
        meta = get_instance_enterprise_extension().handle_upload(request=request, model_id=model_id, attr_id=attr_id, uploaded_file=uploaded)
        return WebUtils.response_success(meta)

    @HasPermission("asset_info-View")
    @action(detail=False, methods=["get"], url_path="download_file/(?P<file_id>[^/]+)")
    def download_file(self, request, file_id: str):
        """获取附件/图片的短时效预签名直链。

        校验实例读权限后返回预签名 URL（JSON）。前端经 axios（带令牌）调用本接口拿到
        URL，再直接用于 <img src> / 下载——浏览器对 MinIO 的图片显示与下载导航不受 CORS
        限制，从而绕开「直链请求不带令牌」的鉴权问题。
        """

        def _check_read(inst_uuid):
            if inst_uuid is None:
                return False
            instance = InstanceManage.query_entity_by_uuid(str(inst_uuid))
            return bool(instance) and self._check_instance_read_permission(request, instance)

        as_attachment = request.query_params.get("download") == "1"
        url = get_instance_enterprise_extension().handle_download(
            request=request,
            file_id=file_id,
            check_read_permission=_check_read,
            as_attachment=as_attachment,
        )
        return WebUtils.response_success({"url": url})

    @HasPermission("asset_info-Add")
    @action(detail=False, methods=["delete"], url_path="delete_file/(?P<file_id>[^/]+)")
    def delete_file(self, request, file_id: str):
        """删除尚未提交的临时文件（仅上传者本人）。"""
        get_instance_enterprise_extension().handle_delete_temp(request=request, file_id=file_id)
        return WebUtils.response_success()

    @HasPermission("asset_info-Add")
    def create(self, request):
        import uuid

        from apps.cmdb.services.operation_service import OperationConflict, OperationService

        model_id = request.data.get("model_id")
        from apps.cmdb.services.module_ingest import strip_system_link_fields

        instance_info = strip_system_link_fields(request.data.get("instance_info"))
        if not model_id or not self._is_model_visible(model_id):
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)
        allowed_org_ids = self._get_allowed_org_ids(request)
        idempotency_key = request.headers.get("Idempotency-Key") or uuid.uuid4().hex
        try:
            started = OperationService.start(
                operator=request.user.username,
                idempotency_key=idempotency_key,
                action="instance.create",
                target={"model_id": model_id},
                request_payload=instance_info,
            )
            inst = OperationService.execute_graph(
                started.operation,
                graph_write=lambda operation_id: InstanceManage.instance_create(
                    model_id,
                    instance_info,
                    request.user.username,
                    allowed_org_ids=allowed_org_ids,
                    record_change=False,
                    operation_id=operation_id,
                    schedule_post_actions=False,
                ),
                events=[("change_record", {}), ("auto_relation", {})],
            )
        except OperationConflict as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_409_CONFLICT)
        response = WebUtils.response_success(self._transport_instance(inst))
        response["X-CMDB-Operation-ID"] = str(started.operation.operation_id)
        return response

    @HasPermission("asset_info-Delete")
    def destroy(self, request, pk: str):
        if str(pk).isdigit():
            return WebUtils.response_error("请使用 inst_uuid 定位实例，不再支持数字 ID", status_code=status.HTTP_400_BAD_REQUEST)
        instance = InstanceManage.query_entity_by_uuid(pk)
        if not instance or not self._is_instance_model_visible(instance):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if not self.check_creator_and_organizations(request, instance):
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

            has_permission = self.check_instance_permission(request, instance, operator=OPERATE)
            if not has_permission:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
            user_groups = format_groups_params(team_ids)
        else:
            user_groups = format_group_params(current_team)

        InstanceManage.instance_batch_delete_by_uuids(
            user_groups,
            request.user.roles,
            [pk],
            request.user.username,
        )
        return WebUtils.response_success()

    @HasPermission("asset_info-Delete")
    @action(detail=False, methods=["post"], url_path="batch_delete")
    def instance_batch_delete(self, request):
        inst_uuids = request.data.get("inst_uuids") if isinstance(request.data, dict) else None
        if not isinstance(inst_uuids, list) or not inst_uuids:
            return WebUtils.response_error("inst_uuids 必须是非空数组", status_code=status.HTTP_400_BAD_REQUEST)
        instances = InstanceManage.query_entity_by_uuids(inst_uuids)
        if not instances:
            return WebUtils.response_error(error_message="实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        if any(not self._is_instance_model_visible(instance) for instance in instances):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        model_id = instances[0]["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)
        for instance in instances:
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

            if not self.check_creator_and_organizations(request, instance):
                has_permission = CmdbRulesFormatUtil.has_object_permission(
                    obj_type=PERMISSION_INSTANCES,
                    operator=OPERATE,
                    model_id=model_id,
                    permission_instances_map=permissions_map,
                    instance=instance,
                )

                if not has_permission:
                    return WebUtils.response_error(
                        response_data=[],
                        error_message=f"抱歉！您没有此实例[{instance['inst_name']}]的权限",
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
            user_groups = format_groups_params(team_ids)
        else:
            user_groups = format_group_params(current_team)

        try:
            InstanceManage.instance_batch_delete_by_uuids(
                user_groups,
                request.user.roles,
                inst_uuids,
                request.user.username,
            )
        except BaseAppException as e:
            return WebUtils.response_error(error_message=e.message, status_code=status.HTTP_403_FORBIDDEN)
        return WebUtils.response_success()

    @HasPermission("asset_info-Edit")
    def partial_update(self, request, pk: str):
        import uuid

        from apps.cmdb.services.operation_service import OperationConflict, OperationService

        if str(pk).isdigit():
            return WebUtils.response_error("请使用 inst_uuid 定位实例，不再支持数字 ID", status_code=status.HTTP_400_BAD_REQUEST)
        instance = InstanceManage.query_entity_by_uuid(pk)
        if not instance or not self._is_instance_model_visible(instance):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if not self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接执行更新
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

            has_permission = self.check_instance_permission(request, instance, operator=OPERATE)
            if not has_permission:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
            user_groups = format_groups_params(team_ids)
        else:
            user_groups = format_group_params(current_team)
        allowed_org_ids = self._get_allowed_org_ids(request)

        from apps.cmdb.services.module_ingest import strip_system_link_fields

        update_attr = strip_system_link_fields({k: v for k, v in request.data.items() if k != "_scenario"})
        scenario = request.data.get("_scenario") or ORDINARY_ATTRIBUTE_CHANGE
        if scenario not in INSTANCE_EDIT_CORRECTABLE_SCENARIOS:
            scenario = ORDINARY_ATTRIBUTE_CHANGE

        idempotency_key = request.headers.get("Idempotency-Key") or uuid.uuid4().hex
        try:
            started = OperationService.start(
                operator=request.user.username,
                idempotency_key=idempotency_key,
                action="instance.update",
                target={"model_id": instance["model_id"], "inst_uuid": pk},
                request_payload={"update_attr": update_attr, "scenario": scenario},
            )
            inst = OperationService.execute_graph(
                started.operation,
                graph_write=lambda operation_id: InstanceManage.instance_update_by_uuid(
                    user_groups,
                    request.user.roles,
                    pk,
                    update_attr,
                    request.user.username,
                    allowed_org_ids=allowed_org_ids,
                    scenario=scenario,
                    record_change=False,
                    operation_id=operation_id,
                    schedule_post_actions=False,
                ),
                events=[
                    ("change_record", {"before_data": instance, "scenario": scenario}),
                    ("auto_relation", {}),
                ],
            )
        except OperationConflict as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_409_CONFLICT)
        response = WebUtils.response_success(self._transport_instance(inst))
        response["X-CMDB-Operation-ID"] = str(started.operation.operation_id)
        return response

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="batch_update")
    def instance_batch_update(self, request):
        inst_uuids = request.data.get("inst_uuids")
        if not isinstance(inst_uuids, list) or not inst_uuids:
            return WebUtils.response_error("inst_uuids 必须是非空数组", status_code=status.HTTP_400_BAD_REQUEST)
        update_data = request.data.get("update_data")
        if not isinstance(update_data, dict) or not update_data:
            return WebUtils.response_error("update_data 必须是非空对象", status_code=status.HTTP_400_BAD_REQUEST)

        instances = InstanceManage.query_entity_by_uuids(inst_uuids)
        if not instances:
            return WebUtils.response_success()
        if any(not self._is_instance_model_visible(instance) for instance in instances):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        model_id = instances[0]["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)
        for instance in instances:
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error("抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN)

            if not self.check_creator_and_organizations(request, instance):
                has_permission = CmdbRulesFormatUtil.has_object_permission(
                    obj_type=PERMISSION_INSTANCES,
                    operator=OPERATE,
                    model_id=model_id,
                    permission_instances_map=permissions_map,
                    instance=instance,
                )

                if not has_permission:
                    return WebUtils.response_error(
                        response_data=[],
                        error_message=f"抱歉！您没有此实例[{instance['inst_name']}]的权限",
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
            user_groups = format_groups_params(team_ids)
        else:
            user_groups = format_group_params(current_team)
        allowed_org_ids = self._get_allowed_org_ids(request)

        try:
            InstanceManage.batch_instance_update_by_uuids(
                user_groups,
                request.user.roles,
                request.data["inst_uuids"],
                request.data["update_data"],
                request.user.username,
                allowed_org_ids=allowed_org_ids,
            )
        except BaseAppException as e:
            return WebUtils.response_error(error_message=e.message, status_code=status.HTTP_403_FORBIDDEN)
        return WebUtils.response_success()

    @HasPermission("asset_info-Add Associate")
    @action(detail=False, methods=["post"], url_path="association")
    def instance_association_create(self, request):
        src_inst_uuid = request.data.get("src_inst_uuid")
        dst_inst_uuid = request.data.get("dst_inst_uuid")
        src_inst = InstanceManage.query_entity_by_uuid(src_inst_uuid)
        dst_inst = InstanceManage.query_entity_by_uuid(dst_inst_uuid)

        if not src_inst or not self._is_instance_model_visible(src_inst):
            return WebUtils.response_error("源实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        if not dst_inst or not self._is_instance_model_visible(dst_inst):
            return WebUtils.response_error("目标实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        # 检查源实例权限
        if not self.check_creator_and_organizations(request, src_inst):
            organizations = self.organizations(request, src_inst)
            if not organizations:
                return WebUtils.response_error(
                    f"抱歉！您没有此实例[{src_inst['inst_name']}]的权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if not self.check_instance_permission(request, src_inst, operator=OPERATE):
                return WebUtils.response_error(
                    f"抱歉！您没有此实例[{src_inst['inst_name']}]的权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # 检查目标实例权限
        if not self.check_creator_and_organizations(request, dst_inst):
            organizations = self.organizations(request, dst_inst)
            if not organizations:
                return WebUtils.response_error(
                    f"抱歉！您没有此实例[{dst_inst['inst_name']}]的权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if not self.check_instance_permission(request, dst_inst, operator=OPERATE):
                return WebUtils.response_error(
                    f"抱歉！您没有此实例[{dst_inst['inst_name']}]的权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        try:
            asso = InstanceManage.instance_association_create_by_uuid(
                src_inst_uuid=src_inst_uuid,
                dst_inst_uuid=dst_inst_uuid,
                model_asst_id=request.data.get("model_asst_id"),
                operator=request.user.username,
            )
            return WebUtils.response_success(asso)
        except BaseAppException as e:
            return WebUtils.response_error(error_message=e.message, status_code=status.HTTP_400_BAD_REQUEST)

    @HasPermission("asset_info-Delete Associate")
    @action(
        detail=False,
        methods=["delete"],
        url_path=("association/(?P<src_inst_uuid>[^/]+)/(?P<dst_inst_uuid>[^/]+)/" "(?P<model_asst_id>[^/]+)"),
    )
    def instance_association_delete(self, request, src_inst_uuid: str, dst_inst_uuid: str, model_asst_id: str):
        # 删除前必须做与 instance_association_create 对称的对象级权限校验，
        # 否则仅凭菜单级 "asset_info-Delete Associate" 权限即可越权清除跨组织边。
        endpoints = [
            (InstanceManage.query_entity_by_uuid(src_inst_uuid), "源"),
            (InstanceManage.query_entity_by_uuid(dst_inst_uuid), "目标"),
        ]
        for endpoint_inst, endpoint_label in endpoints:
            if not endpoint_inst or not self._is_instance_model_visible(endpoint_inst):
                return WebUtils.response_error(
                    f"{endpoint_label}实例不存在",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            if self.check_creator_and_organizations(request, endpoint_inst):
                continue
            if not self.organizations(request, endpoint_inst):
                return WebUtils.response_error(
                    f"抱歉！您没有此实例[{endpoint_inst.get('inst_name')}]的权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if not self.check_instance_permission(request, endpoint_inst, operator=OPERATE):
                return WebUtils.response_error(
                    f"抱歉！您没有此实例[{endpoint_inst.get('inst_name')}]的权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        try:
            deleted = InstanceManage.instance_association_delete_by_key(
                src_inst_uuid=src_inst_uuid,
                dst_inst_uuid=dst_inst_uuid,
                model_asst_id=model_asst_id,
                operator=request.user.username,
            )
        except BaseAppException as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_404_NOT_FOUND)
        return WebUtils.response_success(deleted)

    @action(
        detail=False,
        methods=["get"],
        url_path="association_instance_list/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def instance_association_instance_list(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance or not self._is_instance_model_visible(instance):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(
            request,
            instance,
            operator=VIEW,
        )
        if permission_error:
            return permission_error

        asso_insts = InstanceManage.instance_association_instance_list_by_uuid(
            model_id,
            inst_uuid,
            business_only=True,
            language=request.user.locale,
        )
        for group in asso_insts:
            group["inst_list"] = [self._transport_instance(item) for item in group.get("inst_list", [])]
        return WebUtils.response_success(asso_insts)

    @action(
        detail=False,
        methods=["get"],
        url_path="instance_association/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def instance_association(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance or not self._is_instance_model_visible(instance):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        # 返回关联边列表（非关联实例分组）
        asso_edges = InstanceManage.instance_association_by_uuid(
            model_id,
            inst_uuid,
            business_only=True,
            language=request.user.locale,
        )
        return WebUtils.response_success(asso_edges)

    @HasPermission("asset_info-Add")
    @action(methods=["get"], detail=False, url_path=r"(?P<model_id>.+?)/download_template")
    def download_template(self, request, model_id):
        if not self._is_model_visible(model_id):
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f"attachment;filename={f'{model_id}_import_template.xlsx'}"
        response.write(InstanceManage.download_import_template(model_id).read())
        return response

    @HasPermission("asset_info-Add")
    @action(methods=["post"], detail=False, url_path=r"(?P<model_id>.+?)/inst_import")
    def inst_import(self, request, model_id):
        if not self._is_model_visible(model_id):
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)
        try:
            current_team_raw = get_current_team(request)
            if not current_team_raw:
                return JsonResponse(
                    {
                        "data": [],
                        "result": False,
                        "message": "请先选择组织后再导入",
                    }
                )

            try:
                int(current_team_raw)
            except (TypeError, ValueError):
                return JsonResponse(
                    {
                        "data": [],
                        "result": False,
                        "message": "当前组织参数无效，请刷新页面后重试",
                    }
                )

            try:
                allowed_org_ids = self._get_allowed_org_ids(request)
            except BaseAppException as exc:
                return JsonResponse(
                    {
                        "data": [],
                        "result": False,
                        "message": str(exc),
                    }
                )

            # 检查是否上传了文件
            uploaded_file = request.data.get("file")
            if not uploaded_file:
                return JsonResponse({"data": [], "result": False, "message": "请上传Excel文件"})

            import_result = InstanceManage().inst_import_support_edit(
                model_id=model_id,
                file_stream=uploaded_file.file,
                operator=request.user.username,
                allowed_org_ids=allowed_org_ids,
            )

            # 根据返回的结果结构判断成功或失败
            if isinstance(import_result, dict):
                return JsonResponse(
                    {
                        "data": [],
                        "result": import_result["success"],
                        "message": import_result["message"],
                    }
                )
            else:
                # 兼容旧的字符串返回格式
                is_success = not str(import_result).startswith("数据导入失败")
                return JsonResponse({"data": [], "result": is_success, "message": str(import_result)})

        except Exception as e:
            logger.error(f"模型 {model_id} 数据导入异常: {str(e)}", exc_info=True)
            return JsonResponse(
                {
                    "data": [],
                    "result": False,
                    "message": f"数据导入异常，请检查文件格式和内容: {str(e)}",
                }
            )

    @HasPermission("asset_info-View")
    @action(methods=["post"], detail=False, url_path=r"(?P<model_id>.+?)/inst_export")
    def inst_export(self, request, model_id):
        if not self._is_model_visible(model_id):
            return WebUtils.response_error("模型不存在", status_code=status.HTTP_404_NOT_FOUND)
        # 获取导出参数
        attr_list = request.data.get("attr_list", [])
        association_list = request.data.get("association_list", [])
        inst_uuids = request.data.get("inst_uuids", [])
        selected_instances = InstanceManage.query_entity_by_uuids(inst_uuids) if inst_uuids else []
        if inst_uuids and len(selected_instances) != len(set(inst_uuids)):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        export_ids = [item["_id"] for item in selected_instances]

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f"attachment;filename={f'{model_id}_export.xlsx'}"
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id)

        response.write(
            InstanceManage.inst_export(
                model_id=model_id,
                ids=export_ids,
                permissions_map=permissions_map,
                attr_list=attr_list,
                association_list=association_list,
                creator=request.user.username,
            ).read()
        )
        return response

    @HasPermission("search-View")
    @action(methods=["post"], detail=False)
    def fulltext_search(self, request):
        """全文检索（兼容旧接口）"""
        search = request.data.get("search", "")
        # 为每个模型构建权限映射（与 search 方法保持一致）
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="")

        result = InstanceManage.fulltext_search(search=search, permission_map=permissions_map, creator=request.user.username)
        return WebUtils.response_success([self._transport_instance(item) for item in result])

    @HasPermission("search-View")
    @action(methods=["post"], detail=False, url_path="fulltext_search/stats")
    def fulltext_search_stats(self, request):
        """
        全文检索 - 模型统计接口
        返回搜索结果中每个模型的总数统计

        请求参数:
            - search: 搜索关键词（必填）
            - case_sensitive: 是否精确匹配（可选，默认False即不区分大小写模糊匹配）

        返回示例:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "total": 156,
                    "model_stats": [
                        {"model_id": "Center", "count": 45},
                        {"model_id": "阿里云", "count": 23}
                    ]
                }
            }
        """
        search = request.data.get("search", "")
        case_sensitive = request.data.get("case_sensitive", False)

        if not search:
            return WebUtils.response_error("search keyword is required")

        # 构建权限映射
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="")

        result = InstanceManage.fulltext_search_stats(
            search=search,
            permission_map=permissions_map,
            creator=request.user.username,
            case_sensitive=case_sensitive,
        )

        return WebUtils.response_success(result)

    @HasPermission("search-View")
    @action(methods=["post"], detail=False, url_path="fulltext_search/by_model")
    def fulltext_search_by_model(self, request):
        """
        全文检索 - 模型数据查询接口
        返回指定模型的分页数据

        请求参数:
            - search: 搜索关键词（必填）
            - model_id: 模型ID（必填）
            - page: 页码（可选，默认1）
            - page_size: 每页大小（可选，默认10，最大100）
            - case_sensitive: 是否精确匹配（可选，默认False即不区分大小写模糊匹配）

        返回示例:
            {
                "code": 200,
                "message": "success",
                "data": {
                    "model_id": "Center",
                    "total": 45,
                    "page": 1,
                    "page_size": 10,
                    "data": [{...}, {...}]
                }
            }
        """
        search = request.data.get("search", "")
        model_id = request.data.get("model_id", "")
        page = request.data.get("page", 1)
        page_size = request.data.get("page_size", 10)
        case_sensitive = request.data.get("case_sensitive", False)

        if not search:
            return WebUtils.response_error("search keyword is required")

        if not model_id:
            return WebUtils.response_error("model_id is required")

        # 参数校验
        try:
            page = int(page)
            page_size = int(page_size)
        except (ValueError, TypeError):
            return WebUtils.response_error("page and page_size must be integers")

        if page < 1:
            return WebUtils.response_error("page must be >= 1")

        if page_size < 1 or page_size > 100:
            return WebUtils.response_error("page_size must be between 1 and 100")

        # 构建权限映射
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="")

        result = InstanceManage.fulltext_search_by_model(
            search=search,
            model_id=model_id,
            permission_map=permissions_map,
            creator=request.user.username,
            page=page,
            page_size=page_size,
            case_sensitive=case_sensitive,
        )

        result["data"] = [self._transport_instance(item) for item in result.get("data", [])]
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"topo_search/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def topo_search(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = InstanceManage.topo_search_lite_by_uuid(
            inst_uuid,
            depth=3,
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"topo_search_expand",
    )
    @HasPermission("asset_info-View")
    def topo_search_expand_post(self, request):
        """
        用于拓扑第3层节点点击“+”后的二次查询：
        前端传入 model_id / inst_uuid / parent_uuid（父节点列表），后端返回该节点为中心的下一层拓扑数据。
        """
        inst_uuid = request.data.get("inst_uuid")
        parent_uuids = request.data.get("parent_uuid") or []

        if not inst_uuid:
            return WebUtils.response_error("inst_uuid不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        if str(inst_uuid).isdigit():
            return WebUtils.response_error("请使用 inst_uuid 定位实例，不再支持数字 ID", status_code=status.HTTP_400_BAD_REQUEST)

        if not isinstance(parent_uuids, list):
            parent_uuids = [parent_uuids]

        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        try:
            result = InstanceManage.topo_search_expand_by_uuid(
                inst_uuid,
                parent_uuids,
                depth=2,
                permission_map=permissions_map,
                user=request.user,
            )
        except BaseAppException as exc:
            return WebUtils.response_error(exc.message, status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"topo_search_test_config/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def topo_search_test_config(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        result = InstanceManage.topo_search_test_config_by_uuid(inst_uuid, model_id)
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"k8s_resource_overview/(?P<cluster_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def k8s_resource_overview(self, request, cluster_uuid: str):
        cluster, permission_maps, error = self._k8s_resource_context(request, cluster_uuid)
        if error:
            return error
        # K8s 概览服务尚未切 UUID：视图层解析后桥接图内部 ID
        result = K8sResourceOverviewService.get_overview(cluster["_id"], permission_maps=permission_maps, user=request.user)
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"k8s_resource_layer/(?P<cluster_uuid>.+?)/(?P<layer>.+?)",
    )
    @HasPermission("asset_info-View")
    def k8s_resource_layer(self, request, cluster_uuid: str, layer: str):
        cluster, permission_maps, error = self._k8s_resource_context(request, cluster_uuid)
        if error:
            return error
        serializer = K8sLayerQuerySerializer(data=request.query_params, context={"layer": layer})
        serializer.is_valid(raise_exception=True)
        result = K8sResourceOverviewService.get_layer(
            cluster["_id"],
            layer,
            permission_maps=permission_maps,
            user=request.user,
            **serializer.validated_data,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"k8s_workload_pods/(?P<cluster_uuid>.+?)/(?P<workload_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def k8s_workload_pods(self, request, cluster_uuid: str, workload_uuid: str):
        cluster, permission_maps, error = self._k8s_resource_context(request, cluster_uuid)
        if error:
            return error
        serializer = K8sPageQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        workload = InstanceManage.query_entity_by_uuid(workload_uuid)
        if not workload or workload.get("model_id") != "k8s_workload":
            return WebUtils.response_error("Workload 实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        # K8s 服务尚未切 UUID：桥接图内部 ID
        result = K8sResourceOverviewService.get_workload_pods(
            cluster["_id"],
            workload["_id"],
            permission_maps=permission_maps,
            user=request.user,
            **serializer.validated_data,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"k8s_unowned_pods/(?P<cluster_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def k8s_unowned_pods(self, request, cluster_uuid: str):
        cluster, permission_maps, error = self._k8s_resource_context(request, cluster_uuid)
        if error:
            return error
        serializer = K8sPageQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = K8sResourceOverviewService.get_unowned_pods(
            cluster["_id"],
            permission_maps=permission_maps,
            user=request.user,
            **serializer.validated_data,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"k8s_resource_list/(?P<cluster_uuid>.+?)/(?P<kind>.+?)",
    )
    @HasPermission("asset_info-View")
    def k8s_resource_list(self, request, cluster_uuid: str, kind: str):
        cluster, permission_maps, error = self._k8s_resource_context(request, cluster_uuid)
        if error:
            return error
        kind_serializer = K8sResourceKindSerializer(data={"kind": kind})
        kind_serializer.is_valid(raise_exception=True)
        serializer = K8sResourceListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = K8sResourceOverviewService.list_resources(
            cluster["_id"],
            kind_serializer.validated_data["kind"],
            permission_maps=permission_maps,
            user=request.user,
            **serializer.validated_data,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"topo_themes/(?P<model_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def topo_themes(self, request, model_id: str):
        """返回模型可用的拓扑主题（如 ["network"]），前端据此决定渲染哪些主题 tab。"""
        return WebUtils.response_success({"themes": get_topo_themes(model_id)})

    @action(
        detail=False,
        methods=["get"],
        url_path=r"application_resource_apps/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def application_resource_apps(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        serializer = ApplicationResourceEntrySerializer(data={"model_id": model_id})
        serializer.is_valid(raise_exception=True)
        if model_id != "system":
            return WebUtils.response_error("仅应用系统支持应用列表入口", status_code=status.HTTP_400_BAD_REQUEST)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        # 图遍历仍用内部 _id；对外节点身份已由 overview service 输出为 inst_uuid
        applications = ApplicationResourceOverviewService.list_system_applications(instance["_id"], permission_map=permissions_map, user=request.user)
        return WebUtils.response_success({"applications": applications})

    @action(
        detail=False,
        methods=["get"],
        url_path=r"application_resource_topology/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def application_resource_topology(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        serializer = ApplicationResourceTopologyQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        depth = serializer.validated_data["depth"]

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = ApplicationResourceOverviewService.build_application_topology(
            instance["_id"],
            instance["model_id"],
            depth=depth,
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"application_resource_resources/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def application_resource_resources(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = ApplicationResourceOverviewService.build_application_resources(
            instance["_id"],
            instance["model_id"],
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"application_resource_instances/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def application_resource_instances(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        node_uuids = request.data.get("node_uuids")
        if not isinstance(node_uuids, list):
            return WebUtils.response_error("node_uuids 必须是数组", status_code=status.HTTP_400_BAD_REQUEST)
        nodes = InstanceManage.query_entity_by_uuids(node_uuids) if node_uuids else []
        if node_uuids and len(nodes) != len({str(v) for v in node_uuids}):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = ApplicationResourceOverviewService.build_topology_instance_groups(
            node_ids=[item["_id"] for item in nodes],
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["post"],
        url_path=r"application_resource_export/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def application_resource_export(self, request, model_id: str, inst_uuid: str):
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        node_uuids = request.data.get("node_uuids")
        if not isinstance(node_uuids, list):
            return WebUtils.response_error("node_uuids 必须是数组", status_code=status.HTTP_400_BAD_REQUEST)
        nodes = InstanceManage.query_entity_by_uuids(node_uuids) if node_uuids else []
        if node_uuids and len(nodes) != len({str(v) for v in node_uuids}):
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        content = ApplicationResourceOverviewService.export_topology_instance_groups_excel(
            node_ids=[item["_id"] for item in nodes],
            permission_map=permissions_map,
            user=request.user,
        )
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="application_topology_instances.xlsx"'
        return response

    @action(detail=False, methods=["get"], url_path=r"ipam_view/(?P<inst_uuid>.+?)")
    @HasPermission("asset_info-View")
    def ipam_view(self, request, inst_uuid: str):
        """子网 IP 视图数据：容量/利用率/状态计数/落库 IP 列表。"""
        from apps.cmdb.services.ipam_view import build_ipam_view

        subnet = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not subnet:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, subnet, operator=VIEW)
        if permission_error:
            return permission_error

        data = build_ipam_view(subnet)
        for ip in data.get("ips") or []:
            if isinstance(ip, dict):
                ip.setdefault("organization", [])
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="ip")
        self.add_instance_permission(data["ips"], permissions_map, request.user.username)
        return WebUtils.response_success(data)

    @action(detail=False, methods=["post"], url_path="ipam_ip")
    @HasPermission("asset_info-Add,asset_info-Edit,asset_info-Delete")
    def ipam_ip(self, request):
        """IP 视图手工登记：分配状态、IP 类型、使用人、IP 状态、MAC、描述。"""
        from apps.cmdb.services.ipam_edit import (
            ACTION_DELETE,
            ACTION_NOOP,
            ACTION_UPDATE,
            IpamEditError,
            decide_manual_ip_action,
            execute_manual_ip_action,
            find_ip_in_subnet,
            required_asset_permission,
            user_has_asset_permission,
            validate_ip_belongs_to_subnet,
        )
        from apps.cmdb.services.ipam_view import _query_subnet_ips

        subnet_uuid = str(request.data.get("subnet_inst_uuid") or "").strip()
        ip_addr = str(request.data.get("ip_addr") or "").strip()
        if not subnet_uuid or not ip_addr:
            return WebUtils.response_error("subnet_inst_uuid 与 ip_addr 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        subnet = InstanceManage.query_entity_by_uuid(subnet_uuid)
        if not subnet or subnet.get("model_id") != "subnet":
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, subnet, operator=VIEW)
        if permission_error:
            return permission_error

        try:
            validate_ip_belongs_to_subnet(ip_addr, subnet)
            existing = find_ip_in_subnet(_query_subnet_ips(subnet.get("_id")), ip_addr)
            action = decide_manual_ip_action(existing, request.data.get("ip_allocated_status"))
        except (IpamEditError, BaseAppException) as exc:
            status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)
            if status_code >= 500:
                status_code = status.HTTP_400_BAD_REQUEST
            return WebUtils.response_error(str(exc), status_code=status_code)

        needed = required_asset_permission(action)
        if needed and not user_has_asset_permission(request.user, needed):
            return WebUtils.response_error("抱歉！您没有此操作的权限", status_code=status.HTTP_403_FORBIDDEN)

        if action == ACTION_NOOP:
            return WebUtils.response_success({"action": ACTION_NOOP, "ip": None})

        if action in {ACTION_UPDATE, ACTION_DELETE} and existing:
            permission_error = self.require_instance_permission(request, existing, operator=OPERATE)
            if permission_error:
                return permission_error

        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            team_ids = get_organization_and_children_ids(tree_data=request.user.group_tree, target_id=current_team)
            user_groups = format_groups_params(team_ids)
        else:
            user_groups = format_group_params(current_team)

        try:
            allowed_org_ids = self._get_allowed_org_ids(request)
            result = execute_manual_ip_action(
                action=action,
                subnet=subnet,
                existing=existing,
                ip_addr=ip_addr,
                allocated_status=request.data.get("ip_allocated_status"),
                ip_status=request.data.get("ip_status"),
                ip_type=request.data.get("ip_type"),
                ip_user=request.data.get("ip_user"),
                mac=request.data.get("mac"),
                description=request.data.get("description") or "",
                operator=request.user.username,
                allowed_org_ids=allowed_org_ids,
                user_groups=user_groups,
                roles=request.user.roles,
            )
        except (IpamEditError, BaseAppException) as exc:
            status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)
            if status_code >= 500:
                status_code = status.HTTP_400_BAD_REQUEST
            return WebUtils.response_error(str(exc), status_code=status_code)

        ip = result.get("ip")
        if isinstance(ip, dict):
            result = {**result, "ip": self._transport_instance(ip)}
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"network_topo/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def network_topo(self, request, model_id: str, inst_uuid: str):
        """网络设备拓扑：以该设备为中心按 depth 跳展开接口直连。

        depth 查询参数控制展开层数（默认 2，钳制到 [1, NETWORK_TOPO_MAX_HOP]）；
        前端首屏传 depth=2，点击对端增量展开传 depth=1。节点上限 100 由服务层兜底。
        """
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        try:
            depth = int(request.query_params.get("depth", NETWORK_TOPO_DEFAULT_HOP))
        except (TypeError, ValueError):
            depth = NETWORK_TOPO_DEFAULT_HOP
        depth = max(1, min(depth, NETWORK_TOPO_MAX_HOP))

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = InstanceManage.network_topology_by_uuid(
            inst_uuid,
            instance["model_id"],
            depth=depth,
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"room_layout/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def room_layout(self, request, model_id: str, inst_uuid: str):
        """机房俯视平面图：返回该机房下机柜的 row/col/类型/U 占用率，供平面图布局。"""
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        # rack/room 服务尚未切 UUID：桥接图内部 ID
        result = get_room_layout(instance["_id"], permission_map=permissions_map, user=request.user)
        self._attach_layout_item_permissions(
            request,
            (result.get("racks") or []) + (result.get("unplaced") or []),
            default_model="rack",
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"rack_layout/(?P<model_id>.+?)/(?P<inst_uuid>.+?)",
    )
    @HasPermission("asset_info-View")
    def rack_layout(self, request, model_id: str, inst_uuid: str):
        """机柜正视 U 图：返回机柜 u_count 及其 contains 设备的 U 位排布。"""
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = get_rack_layout(instance["_id"], permission_map=permissions_map, user=request.user)
        self._attach_layout_item_permissions(
            request,
            (result.get("placed") or []) + (result.get("unplaced") or []),
        )
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path="rack_room_layout")
    @HasPermission("asset_info-Add,asset_info-Edit")
    def rack_room_layout(self, request):
        """机房/机柜布局变更：新建或选择已有并放置，或移出布局。不删除实例。"""
        from apps.cmdb.services.rack_room_edit import (
            ACTION_PLACE_EXISTING,
            ACTION_UNPLACE,
            RackRoomEditError,
            execute_layout_action,
            required_asset_permission,
            user_has_asset_permission,
        )

        action = str(request.data.get("action") or "").strip()
        scope = str(request.data.get("scope") or "").strip()
        container_uuid = str(request.data.get("container_inst_uuid") or "").strip()
        if not action or not scope or not container_uuid:
            return WebUtils.response_error("action、scope 与 container_inst_uuid 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        container = InstanceManage.query_entity_by_uuid(container_uuid)
        expected_model = "server_room" if scope == "room" else "rack"
        if not container or container.get("model_id") != expected_model:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, container, operator=VIEW)
        if permission_error:
            return permission_error

        needed = required_asset_permission(action)
        if needed and not user_has_asset_permission(request.user, needed):
            return WebUtils.response_error("抱歉！您没有此操作的权限", status_code=status.HTTP_403_FORBIDDEN)

        existing = None
        existing_uuid = str(request.data.get("inst_uuid") or "").strip()
        if action in {ACTION_PLACE_EXISTING, ACTION_UNPLACE}:
            if not existing_uuid:
                return WebUtils.response_error("inst_uuid 不能为空", status_code=status.HTTP_400_BAD_REQUEST)
            existing = InstanceManage.query_entity_by_uuid(existing_uuid)
            if not existing:
                return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)
            permission_error = self.require_instance_permission(request, existing, operator=OPERATE)
            if permission_error:
                return permission_error

        try:
            result = execute_layout_action(
                action=action,
                scope=scope,
                container=container,
                operator=request.user.username,
                allowed_org_ids=self._get_allowed_org_ids(request),
                user_groups=self._layout_user_groups(request),
                roles=request.user.roles,
                existing=existing,
                instance_info=request.data.get("instance_info") or None,
                model_id=request.data.get("model_id"),
                row=request.data.get("row"),
                col=request.data.get("col"),
                u_start=request.data.get("u_start"),
                u_size=request.data.get("u_size"),
            )
        except (RackRoomEditError, BaseAppException) as exc:
            status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)
            if status_code >= 500:
                status_code = status.HTTP_400_BAD_REQUEST
            return WebUtils.response_error(str(exc), status_code=status_code)

        instance = result.get("instance")
        if isinstance(instance, dict):
            result = {**result, "instance": self._transport_layout_instance(instance)}
        return WebUtils.response_success(result)

    @action(detail=False, methods=["get"], url_path="rack_room_layout_candidates")
    @HasPermission("asset_info-Add,asset_info-Edit")
    def rack_room_layout_candidates(self, request):
        """布局选择已有：可放置与已在其它容器的灰色候选。已在当前图上的不返回。"""
        from apps.cmdb.services.rack_room_edit import RackRoomEditError, list_layout_candidates

        scope = str(request.query_params.get("scope") or "").strip()
        container_uuid = str(request.query_params.get("container_inst_uuid") or "").strip()
        model_id = str(request.query_params.get("model_id") or "").strip()
        if not scope or not container_uuid or not model_id:
            return WebUtils.response_error("scope、container_inst_uuid 与 model_id 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        container = InstanceManage.query_entity_by_uuid(container_uuid)
        expected_model = "server_room" if scope == "room" else "rack"
        if not container or container.get("model_id") != expected_model:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, container, operator=VIEW)
        if permission_error:
            return permission_error

        try:
            page = self._parse_positive_int(request.query_params.get("page"), "page", 1)
            page_size = self._parse_positive_int(request.query_params.get("page_size"), "page_size", 20)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=model_id)
        try:
            result = list_layout_candidates(
                scope=scope,
                container=container,
                model_id=model_id,
                permission_map=permissions_map,
                page=page,
                page_size=page_size,
                search=request.query_params.get("search") or "",
            )
        except (RackRoomEditError, BaseAppException) as exc:
            status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)
            if status_code >= 500:
                status_code = status.HTTP_400_BAD_REQUEST
            return WebUtils.response_error(str(exc), status_code=status_code)

        items = result.get("items") or []
        self._attach_layout_item_permissions(request, items, default_model=model_id)
        result = {
            **result,
            "items": [self._transport_layout_instance(item) for item in items],
        }
        return WebUtils.response_success(result)

    @action(detail=False, methods=["get"], url_path="racks_grouped_by_room")
    @HasPermission("asset_info-View")
    def racks_grouped_by_room(self, request):
        """机柜选择器：按机房分组返回可见机柜，搜索同时匹配机房名与机柜名。分页单位为机房。"""
        try:
            page = self._parse_positive_int(request.query_params.get("page"), "page", 1)
            page_size = self._parse_positive_int(request.query_params.get("page_size"), "page_size", 20)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        if page_size > 100:
            return WebUtils.response_error("page_size 必须在 1 到 100 之间", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            result = list_racks_grouped_by_room(
                room_permission_map=CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="server_room"),
                rack_permission_map=CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id="rack"),
                user=request.user,
                creator=request.user.username,
                search=str(request.query_params.get("search") or ""),
                page=page,
                page_size=page_size,
            )
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(result)

    @action(
        methods=["post"],
        detail=False,
        url_path=r"(?P<model_id>.+?)/show_field/settings",
    )
    @HasPermission("asset_info-View")
    def create_or_update(self, request, model_id):
        data = dict(
            model_id=model_id,
            created_by=request.user.username,
            show_fields=request.data,
        )
        result = InstanceManage.create_or_update(data)
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path=r"(?P<model_id>.+?)/show_field/detail")
    @HasPermission("asset_info-View")
    def get_info(self, request, model_id):
        result = InstanceManage.get_info(model_id, request.user.username)
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path=r"model_inst_count")
    @HasPermission("asset_info-View")
    def model_inst_count(self, request):
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id="")
        result = InstanceManage.model_inst_count(permissions_map=permissions_map, creator=request.user.username)
        return WebUtils.response_success(result)

    @action(methods=["GET"], detail=False)
    @HasPermission("asset_info-View")
    def list_proxys(self, requests, *args, **kwargs):
        """
        查询云区域数据
        TODO 等节点管理开放接口后再对接接口
        """
        node_mgmt = NodeMgmt()
        data = node_mgmt.cloud_region_list() or []
        _data = []
        for item in data:
            if not isinstance(item, dict):
                continue
            proxy_id = item.get("id")
            proxy_name = item.get("name")
            if proxy_id is None or proxy_name is None:
                continue
            _data.append({"proxy_id": proxy_id, "proxy_name": proxy_name})
        return WebUtils.response_success(_data)

    @action(detail=False, methods=["post"], url_path="ipam_reconcile")
    @HasPermission("asset_info-Edit")
    def ipam_reconcile(self, request):
        """创建或复用一个异步 IPAM 对账作业。"""
        from apps.cmdb.services.ipam_reconcile_job import IPAMReconcileJob

        result = IPAMReconcileJob.enqueue(trigger="manual")
        return WebUtils.response_success({"run_id": str(result.run.run_id), "status": result.run.status, "reused": result.reused})
