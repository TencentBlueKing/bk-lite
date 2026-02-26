from django.http import HttpResponse, JsonResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.cmdb.constants.constants import PERMISSION_INSTANCES, OPERATE, VIEW
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.base import format_group_params, get_organization_and_children_ids
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt
from apps.system_mgmt.utils.group_utils import GroupUtils


class InstanceViewSet(CmdbPermissionMixin, viewsets.ViewSet):
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
                normalized.append(
                    {"field": field, "type": _type, "start": start, "end": end}
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

        organizations_instances_map = (
            CmdbRulesFormatUtil.format_organizations_instances_map(
                permission_instances_map
            )
        )
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
                for _permission in organizations_instances_map[organization][
                    "permission"
                ]:
                    if _permission not in instance["permission"]:
                        instance["permission"].append(_permission)

            if not instance["permission"]:
                if instance["inst_name"] in organizations_instances_map:
                    instance["permission"] = list(
                        organizations_instances_map[instance["inst_name"]]["permission"]
                    )

    @HasPermission("asset_info-View")
    @action(methods=["post"], detail=False)
    def search(self, request):
        """
        查询实例权限：
        1. 若前端不做组织筛选，默认查询组织 request.COOKIES.get("current_team")
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
            return WebUtils.response_error(
                "model_id不能为空", status_code=status.HTTP_400_BAD_REQUEST
            )

        query_list = self._normalize_query_list(request.data.get("query_list", []))
        page, page_size = (
            int(request.data.get("page", 1)),
            int(request.data.get("page_size", 10)),
        )
        case_sensitive = request.data.get("case_sensitive", True)
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request, model_id
        )
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
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回
            instance["permission"] = [VIEW, OPERATE]
            return WebUtils.response_success(instance)

        organizations = self.organizations(request, instance)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        model_id = instance["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id
        )

        has_permission = CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=VIEW,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=instance,
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        self.add_instance_permission(
            instances=[instance],
            permission_instances_map=permissions_map,
            creator=request.user.username,
        )
        return WebUtils.response_success(instance)

    @HasPermission("asset_info-Add")
    def create(self, request):
        model_id = request.data.get("model_id")
        inst = InstanceManage.instance_create(
            model_id,
            request.data.get("instance_info"),
            request.user.username,
        )
        return WebUtils.response_success(inst)

    @HasPermission("asset_info-Delete")
    def destroy(self, request, pk: int):
        instance = InstanceManage.query_entity_by_id(pk)
        if not instance:
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if not self.check_creator_and_organizations(request, instance):
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

            has_permission = self.check_instance_permission(
                request, instance, operator=OPERATE
            )
            if not has_permission:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

        InstanceManage.instance_batch_delete(
            format_group_params(request.COOKIES.get("current_team")),
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
            return WebUtils.response_error(
                error_message="实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        model_id = instances[0]["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id
        )
        for instance in instances:
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

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

        InstanceManage.instance_batch_delete(
            request.user.group_list,
            request.user.roles,
            request.data,
            request.user.username,
        )
        return WebUtils.response_success()

    @HasPermission("asset_info-Edit")
    def partial_update(self, request, pk: int):
        instance = InstanceManage.query_entity_by_id(pk)
        if not instance:
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if not self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接执行更新
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

            has_permission = self.check_instance_permission(
                request, instance, operator=OPERATE
            )
            if not has_permission:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

        inst = InstanceManage.instance_update(
            request.user.group_list,
            request.user.roles,
            int(pk),
            request.data,
            request.user.username,
        )
        return WebUtils.response_success(inst)

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="batch_update")
    def instance_batch_update(self, request):
        instances = InstanceManage.query_entity_by_ids(request.data["inst_ids"])
        if not instances:
            return WebUtils.response_success()

        model_id = instances[0]["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id
        )
        for instance in instances:
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

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

        InstanceManage.batch_instance_update(
            request.user.group_list,
            request.user.roles,
            request.data["inst_ids"],
            request.data["update_data"],
            request.user.username,
        )
        return WebUtils.response_success()

    @HasPermission("asset_info-Add Associate")
    @action(detail=False, methods=["post"], url_path="association")
    def instance_association_create(self, request):
        src_inst_id = request.data.get("src_inst_id")
        dst_inst_id = request.data.get("dst_inst_id")
        src_inst = InstanceManage.query_entity_by_id(src_inst_id)
        dst_inst = InstanceManage.query_entity_by_id(dst_inst_id)

        if not src_inst:
            return WebUtils.response_error(
                "源实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )
        if not dst_inst:
            return WebUtils.response_error(
                "目标实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

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
            asso = InstanceManage.instance_association_create(
                request.data, request.user.username
            )
            return WebUtils.response_success(asso)
        except BaseAppException as e:
            return WebUtils.response_error(
                error_message=e.message, status_code=status.HTTP_400_BAD_REQUEST
            )

    @HasPermission("asset_info-Delete Associate")
    @action(detail=False, methods=["delete"], url_path="association/(?P<id>.+?)")
    def instance_association_delete(self, request, id: int):
        InstanceManage.instance_association_delete(int(id), request.user.username)
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
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回关联实例列表
            organizations = self.organizations(request, instance)
            # 再次确认用户所在的组织
            if not organizations:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

            has_permission = self.check_instance_permission(
                request, instance, operator=VIEW
            )
            if not has_permission:
                return WebUtils.response_error(
                    "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
                )

        asso_insts = InstanceManage.instance_association_instance_list(
            model_id, int(inst_id)
        )
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
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回关联信息
            asso_insts = InstanceManage.instance_association(model_id, int(inst_id))
            return WebUtils.response_success(asso_insts)

        organizations = self.organizations(request, instance)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = self.check_instance_permission(
            request, instance, operator=VIEW
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        asso_insts = InstanceManage.instance_association(model_id, int(inst_id))
        return WebUtils.response_success(asso_insts)

    @HasPermission("asset_info-Add")
    @action(
        methods=["get"], detail=False, url_path=r"(?P<model_id>.+?)/download_template"
    )
    def download_template(self, request, model_id):
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f"attachment;filename={f'{model_id}_import_template.xlsx'}"
        )
        response.write(InstanceManage.download_import_template(model_id).read())
        return response

    @HasPermission("asset_info-Add")
    @action(methods=["post"], detail=False, url_path=r"(?P<model_id>.+?)/inst_import")
    def inst_import(self, request, model_id):
        try:
            current_team_raw = request.COOKIES.get("current_team")
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
                    GroupUtils.get_all_child_groups(
                        current_team, include_self=True, group_list=None
                    )
                    if include_children
                    else [current_team]
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
                return JsonResponse(
                    {"data": [], "result": False, "message": "请上传Excel文件"}
                )

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
                return JsonResponse(
                    {"data": [], "result": is_success, "message": str(import_result)}
                )

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

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f"attachment;filename={f'{model_id}_export.xlsx'}"
        )
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request, model_id
        )

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
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=""
        )

        result = InstanceManage.fulltext_search(
            search=search, permission_map=permissions_map, creator=request.user.username
        )
        return WebUtils.response_success(result)

    @HasPermission("search-View")
    @action(methods=["post"], detail=False, url_path="fulltext_search/stats")
    def fulltext_search_stats(self, request):
        """
        全文检索 - 模型统计接口
        返回搜索结果中每个模型的总数统计

        请求参数:
            - search: 搜索关键词（必填）
            - case_sensitive: 是否区分大小写（可选，默认False即模糊匹配）

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
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=""
        )

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
            - case_sensitive: 是否区分大小写（可选，默认False即模糊匹配）

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
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=""
        )

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
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回拓扑搜索结果
            result = InstanceManage.topo_search_lite(int(inst_id), depth=3)
            return WebUtils.response_success(result)

        organizations = self.organizations(request, instance)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = self.check_instance_permission(
            request, instance, operator=VIEW
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = InstanceManage.topo_search_lite(int(inst_id), depth=3)
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
            return WebUtils.response_error(
                "inst_id不能为空", status_code=status.HTTP_400_BAD_REQUEST
            )
        try:
            inst_id = int(inst_id)
        except (TypeError, ValueError):
            return WebUtils.response_error(
                "inst_id不合法", status_code=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(parent_ids, list):
            parent_ids = [parent_ids]

        instance = InstanceManage.query_entity_by_id(inst_id)
        if not instance:
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if self.check_creator_and_organizations(request, instance):
            result = InstanceManage.topo_search_expand(inst_id, parent_ids, depth=2)
            return WebUtils.response_success(result)

        organizations = self.organizations(request, instance)
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = self.check_instance_permission(
            request, instance, operator=VIEW
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = InstanceManage.topo_search_expand(inst_id, parent_ids, depth=2)
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
            return WebUtils.response_error(
                "实例不存在", status_code=status.HTTP_404_NOT_FOUND
            )

        if self.check_creator_and_organizations(request, instance):
            # 如果是自己创建的实例，直接返回测试配置拓扑搜索结果
            result = InstanceManage.topo_search_test_config(int(inst_id), model_id)
            return WebUtils.response_success(result)

        organizations = self.organizations(request, instance)
        # 再次确认用户所在的组织
        if not organizations:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        has_permission = self.check_instance_permission(
            request, instance, operator=VIEW
        )
        if not has_permission:
            return WebUtils.response_error(
                "抱歉！您没有此实例的权限", status_code=status.HTTP_403_FORBIDDEN
            )

        result = InstanceManage.topo_search_test_config(int(inst_id), model_id)
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

    @action(
        methods=["get"], detail=False, url_path=r"(?P<model_id>.+?)/show_field/detail"
    )
    @HasPermission("asset_info-View")
    def get_info(self, request, model_id):
        result = InstanceManage.get_info(model_id, request.user.username)
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path=r"model_inst_count")
    @HasPermission("asset_info-View")
    def model_inst_count(self, request):
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request, model_id=""
        )
        result = InstanceManage.model_inst_count(
            permissions_map=permissions_map, creator=request.user.username
        )
        return WebUtils.response_success(result)

    @action(methods=["GET"], detail=False)
    @HasPermission("asset_info-View")
    def list_proxys(self, requests, *args, **kwargs):
        """
        查询云区域数据
        TODO 等节点管理开放接口后再对接接口
        """
        node_mgmt = NodeMgmt()
        data = node_mgmt.cloud_region_list()
        _data = [{"proxy_id": i["id"], "proxy_name": i["name"]} for i in data]
        return WebUtils.response_success(_data)
