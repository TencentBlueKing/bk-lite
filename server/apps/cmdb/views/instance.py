from django.http import HttpResponse, JsonResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.cmdb.constants.constants import (
    PERMISSION_INSTANCES,
    OPERATE,
    VIEW,
    NETWORK_TOPO_DEFAULT_HOP,
    NETWORK_TOPO_MAX_HOP,
)
from apps.cmdb.models.change_record import (
    INSTANCE_EDIT_CORRECTABLE_SCENARIOS,
    ORDINARY_ATTRIBUTE_CHANGE,
)
from apps.cmdb.instance_ops.extensions import get_instance_enterprise_extension
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.base import (
    format_group_params,
    format_groups_params,
    get_current_team_from_request,
    get_organization_and_children_ids,
)
from apps.cmdb.services.topology_theme import get_topo_themes
from apps.cmdb.services.rack_room import get_room_layout, get_rack_layout
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.core.utils.team_utils import get_current_team


class InstanceViewSet(CmdbPermissionMixin, viewsets.ViewSet):
    @staticmethod
    def _get_allowed_org_ids(request) -> list[int]:
        current_team = get_current_team_from_request(request)
        include_children = request.COOKIES.get("include_children") == "1"
        user_group_ids = [i["id"] for i in request.user.group_list]

        if getattr(request.user, "is_superuser", False):
            return GroupUtils.get_all_child_groups(current_team, include_self=True, group_list=None) if include_children else [
                current_team
            ]

        allowed_org_ids = GroupUtils.get_user_authorized_child_groups(
            user_group_list=user_group_ids,
            target_group_id=current_team,
            include_children=include_children,
        )
        if not allowed_org_ids:
            raise BaseAppException("抱歉！您没有该组织的权限或组织选择无效")
        return allowed_org_ids

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
        return WebUtils.response_success(dict(insts=instance_list, count=count))

    @HasPermission("asset_info-View")
    def retrieve(self, request, pk: str):
        instance = InstanceManage.query_entity_by_id(int(pk))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回
            instance["permission"] = [VIEW, OPERATE]
            return WebUtils.response_success(instance)

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
        return WebUtils.response_success(instance)

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
        meta = get_instance_enterprise_extension().handle_upload(
            request=request, model_id=model_id, attr_id=attr_id, uploaded_file=uploaded
        )
        return WebUtils.response_success(meta)

    @HasPermission("asset_info-View")
    @action(detail=False, methods=["get"], url_path="download_file/(?P<file_id>[^/]+)")
    def download_file(self, request, file_id: str):
        """获取附件/图片的短时效预签名直链。

        校验实例读权限后返回预签名 URL（JSON）。前端经 axios（带令牌）调用本接口拿到
        URL，再直接用于 <img src> / 下载——浏览器对 MinIO 的图片显示与下载导航不受 CORS
        限制，从而绕开「直链请求不带令牌」的鉴权问题。
        """

        def _check_read(inst_id):
            if inst_id is None:
                return False
            instance = InstanceManage.query_entity_by_id(int(inst_id))
            return bool(instance) and self._check_instance_read_permission(request, instance)

        as_attachment = request.query_params.get("download") == "1"
        url = get_instance_enterprise_extension().handle_download(
            request=request, file_id=file_id, check_read_permission=_check_read,
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
        model_id = request.data.get("model_id")
        allowed_org_ids = self._get_allowed_org_ids(request)
        inst = InstanceManage.instance_create(
            model_id,
            request.data.get("instance_info"),
            request.user.username,
            allowed_org_ids=allowed_org_ids,
        )
        return WebUtils.response_success(inst)

    @HasPermission("asset_info-Delete")
    def destroy(self, request, pk: int):
        instance = InstanceManage.query_entity_by_id(pk)
        if not instance:
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

        InstanceManage.instance_batch_delete(
            user_groups,
            request.user.roles,
            [int(pk)],
            request.user.username,
        )
        return WebUtils.response_success()

    @HasPermission("asset_info-Delete")
    @action(detail=False, methods=["post"], url_path="batch_delete")
    def instance_batch_delete(self, request):
        instances = InstanceManage.query_entity_by_ids(request.data)
        if not instances:
            return WebUtils.response_error(error_message="实例不存在", status_code=status.HTTP_404_NOT_FOUND)

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
            InstanceManage.instance_batch_delete(
                user_groups,
                request.user.roles,
                request.data,
                request.user.username,
            )
        except BaseAppException as e:
            return WebUtils.response_error(error_message=e.message, status_code=status.HTTP_403_FORBIDDEN)
        return WebUtils.response_success()

    @HasPermission("asset_info-Edit")
    def partial_update(self, request, pk: int):
        instance = InstanceManage.query_entity_by_id(pk)
        if not instance:
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

        update_attr = {k: v for k, v in request.data.items() if k != "_scenario"}
        scenario = request.data.get("_scenario") or ORDINARY_ATTRIBUTE_CHANGE
        if scenario not in INSTANCE_EDIT_CORRECTABLE_SCENARIOS:
            scenario = ORDINARY_ATTRIBUTE_CHANGE

        inst = InstanceManage.instance_update(
            user_groups,
            request.user.roles,
            int(pk),
            update_attr,
            request.user.username,
            allowed_org_ids=allowed_org_ids,
            scenario=scenario,
        )
        return WebUtils.response_success(inst)

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="batch_update")
    def instance_batch_update(self, request):
        inst_ids = request.data.get("inst_ids")
        if not isinstance(inst_ids, list) or not inst_ids:
            return WebUtils.response_error("inst_ids 必须是非空数组", status_code=status.HTTP_400_BAD_REQUEST)
        update_data = request.data.get("update_data")
        if not isinstance(update_data, dict) or not update_data:
            return WebUtils.response_error("update_data 必须是非空对象", status_code=status.HTTP_400_BAD_REQUEST)

        instances = InstanceManage.query_entity_by_ids(inst_ids)
        if not instances:
            return WebUtils.response_success()

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
            InstanceManage.batch_instance_update(
                user_groups,
                request.user.roles,
                request.data["inst_ids"],
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
        src_inst_id = request.data.get("src_inst_id")
        dst_inst_id = request.data.get("dst_inst_id")
        src_inst = InstanceManage.query_entity_by_id(src_inst_id)
        dst_inst = InstanceManage.query_entity_by_id(dst_inst_id)

        if not src_inst:
            return WebUtils.response_error("源实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        if not dst_inst:
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
            asso = InstanceManage.instance_association_create(request.data, request.user.username)
            return WebUtils.response_success(asso)
        except BaseAppException as e:
            return WebUtils.response_error(error_message=e.message, status_code=status.HTTP_400_BAD_REQUEST)

    @HasPermission("asset_info-Delete Associate")
    @action(detail=False, methods=["delete"], url_path="association/(?P<id>.+?)")
    def instance_association_delete(self, request, id: int):
        asso_id = int(id)
        # 删除前必须做与 instance_association_create 对称的对象级权限校验，
        # 否则仅凭菜单级 "asset_info-Delete Associate" 权限即可越权清除跨组织边。
        asso_info = InstanceManage.instance_association_by_asso_id(asso_id)
        if not asso_info:
            return WebUtils.response_error("关联关系不存在", status_code=status.HTTP_404_NOT_FOUND)

        for endpoint_key, endpoint_label in (("src", "源"), ("dst", "目标")):
            endpoint_inst = asso_info.get(endpoint_key)
            if not endpoint_inst:
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

        InstanceManage.instance_association_delete(asso_id, request.user.username)
        return WebUtils.response_success()

    @action(
        detail=False,
        methods=["get"],
        url_path="association_instance_list/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def instance_association_instance_list(self, request, model_id: str, inst_id: int):
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(
            request,
            instance,
            operator=VIEW,
        )
        if permission_error:
            return permission_error

        asso_insts = InstanceManage.instance_association_instance_list(model_id, int(inst_id))
        return WebUtils.response_success(asso_insts)

    @action(
        detail=False,
        methods=["get"],
        url_path="instance_association/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def instance_association(self, request, model_id: str, inst_id: int):
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        asso_insts = InstanceManage.instance_association(model_id, int(inst_id))
        return WebUtils.response_success(asso_insts)

    @HasPermission("asset_info-Add")
    @action(methods=["get"], detail=False, url_path=r"(?P<model_id>.+?)/download_template")
    def download_template(self, request, model_id):
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f"attachment;filename={f'{model_id}_import_template.xlsx'}"
        response.write(InstanceManage.download_import_template(model_id).read())
        return response

    @HasPermission("asset_info-Add")
    @action(methods=["post"], detail=False, url_path=r"(?P<model_id>.+?)/inst_import")
    def inst_import(self, request, model_id):
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
                current_team = int(current_team_raw)
            except (TypeError, ValueError):
                return JsonResponse(
                    {
                        "data": [],
                        "result": False,
                        "message": "当前组织参数无效，请刷新页面后重试",
                    }
                )

            include_children = request.COOKIES.get("include_children") == "1"
            user_group_ids = [i["id"] for i in request.user.group_list]

            if getattr(request.user, "is_superuser", False):
                allowed_org_ids = (
                    GroupUtils.get_all_child_groups(current_team, include_self=True, group_list=None) if include_children else [current_team]
                )
            else:
                allowed_org_ids = GroupUtils.get_user_authorized_child_groups(
                    user_group_list=user_group_ids,
                    target_group_id=current_team,
                    include_children=include_children,
                )

            if not allowed_org_ids:
                return JsonResponse(
                    {
                        "data": [],
                        "result": False,
                        "message": "抱歉！您没有该组织的权限或组织选择无效",
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
        # 获取导出参数
        attr_list = request.data.get("attr_list", [])
        association_list = request.data.get("association_list", [])
        inst_ids = request.data.get("inst_ids", [])

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f"attachment;filename={f'{model_id}_export.xlsx'}"
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request, model_id)

        response.write(
            InstanceManage.inst_export(
                model_id=model_id,
                ids=inst_ids,
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
        return WebUtils.response_success(result)

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

        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"topo_search/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def topo_search(self, request, model_id: str, inst_id: int):
        instance = InstanceManage.query_entity_by_id(inst_id)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = InstanceManage.topo_search_lite(
            int(inst_id),
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
        前端传入 model_id / inst_id / parent_id（父节点列表），后端返回该节点为中心的下一层拓扑数据。
        """
        inst_id = request.data.get("inst_id")
        parent_ids = request.data.get("parent_id") or []

        if inst_id is None:
            return WebUtils.response_error("inst_id不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            inst_id = int(inst_id)
        except (TypeError, ValueError):
            return WebUtils.response_error("inst_id不合法", status_code=status.HTTP_400_BAD_REQUEST)

        if not isinstance(parent_ids, list):
            parent_ids = [parent_ids]

        instance = InstanceManage.query_entity_by_id(inst_id)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        result = InstanceManage.topo_search_expand(
            inst_id,
            parent_ids,
            depth=2,
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"topo_search_test_config/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def topo_search_test_config(self, request, model_id: str, inst_id: int):
        instance = InstanceManage.query_entity_by_id(inst_id)
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        result = InstanceManage.topo_search_test_config(int(inst_id), model_id)
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
        url_path=r"network_topo/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def network_topo(self, request, model_id: str, inst_id: int):
        """网络设备拓扑：以该设备为中心按 depth 跳展开接口直连。

        depth 查询参数控制展开层数（默认 2，钳制到 [1, NETWORK_TOPO_MAX_HOP]）；
        前端首屏传 depth=2，点击对端增量展开传 depth=1。节点上限 100 由服务层兜底。
        """
        instance = InstanceManage.query_entity_by_id(int(inst_id))
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

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=instance["model_id"]
        )
        result = InstanceManage.network_topology(
            int(inst_id),
            instance["model_id"],
            depth=depth,
            permission_map=permissions_map,
            user=request.user,
        )
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"room_layout/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def room_layout(self, request, model_id: str, inst_id: int):
        """机房俯视平面图：返回该机房下机柜的 row/col/类型/U 占用率，供平面图布局。"""
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=instance["model_id"]
        )
        result = get_room_layout(int(inst_id), permission_map=permissions_map, user=request.user)
        return WebUtils.response_success(result)

    @action(
        detail=False,
        methods=["get"],
        url_path=r"rack_layout/(?P<model_id>.+?)/(?P<inst_id>.+?)",
    )
    @HasPermission("asset_info-View")
    def rack_layout(self, request, model_id: str, inst_id: int):
        """机柜正视 U 图：返回机柜 u_count 及其 contains 设备的 U 位排布。"""
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=instance["model_id"]
        )
        result = get_rack_layout(int(inst_id), permission_map=permissions_map, user=request.user)
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
