from django.http import HttpResponse, JsonResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action

from apps.cmdb.constants import PERMISSION_INSTANCES, OPERATE, VIEW, APP_NAME
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import format_group_params, get_cmdb_rules, format_groups_params
from apps.cmdb.utils.permisssion_util import CmdbRulesFormatUtil
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.permission_utils import get_permission_rules, get_permissions_rules
from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt


class InstanceViewSet(viewsets.ViewSet):
    @HasPermission("asset_info-View")
    @action(methods=["post"], detail=False)
    def search(self, request):
        """
        TODO 搜索存在问题
        query_list [{field: "inst_name", type: "str*", value: "allure(weops-prod)"}] 搜索失败
        query_list [{field: "inst_name", type: "str=", value: "allure(weops-prod)"}] 搜索成果
        """
        model_id = request.data['model_id']
        page, page_size = int(request.data.get("page", 1)), int(request.data.get("page_size", 10))
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_INSTANCES}.{model_id}")
        team = _permission_rules.get("team", [])
        _team = format_groups_params(teams=team)
        rules = _permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        inst_names = list(permission_instances_map.keys())

        instance_list, count = InstanceManage.instance_list(
            _team,
            request.user.roles,
            model_id,
            request.data.get("query_list", []),
            page,
            page_size,
            request.data.get("order", ""),
            inst_names=inst_names
        )
        self.add_instance_permission(instances=instance_list, permission_instances_map=permission_instances_map,
                                     team_id=current_team, teams=set(team))
        return WebUtils.response_success(dict(insts=instance_list, count=count))

    @staticmethod
    def check_creator(request, instance):
        return instance.get("_creator") == request.user.username

    @staticmethod
    def check_instance_permission(request, instance, operator=VIEW):
        model_id = instance["model_id"]
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_INSTANCES}.{model_id}"
                                                 )
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        rules = _permission_rules.get("instance", [])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_INSTANCES,
                                                                   operator=operator,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=instance)
        return has_permission

    @HasPermission("asset_info-View")
    def retrieve(self, request, pk: str):
        instance = InstanceManage.query_entity_by_id(int(pk))
        if not instance:
            return WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)

        if self.check_creator(request, instance):
            # 如果是自己创建的实例，直接返回
            instance["permission"] = [VIEW, OPERATE]
            return WebUtils.response_success(instance)

        model_id = instance["model_id"]
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_INSTANCES}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        team = _permission_rules.get("team", [])
        _team = format_groups_params(teams=team)
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_INSTANCES,
                                                                   operator=VIEW,
                                                                   model_id=model_id,
                                                                   permission_instances_map=permission_instances_map,
                                                                   team_id=current_team,
                                                                   instance=instance)
        if not has_permission:
            return WebUtils.response_error("抱歉！您没有此实力的权限", status_code=status.HTTP_403_FORBIDDEN)

        self.add_instance_permission(instances=[instance], permission_instances_map=permission_instances_map,
                                     team_id=current_team, teams=set(team))
        return WebUtils.response_success(instance)

    @staticmethod
    def add_instance_permission(instances, permission_instances_map, team_id, teams: set):
        """
        给实例添加权限信息
        instances: 实例列表
        permission_instances_map: {inst_name: [VIEW, OPERATE], ...}
        """
        for instance in instances:
            if instance["inst_name"] in permission_instances_map:
                instance['permission'] = permission_instances_map[instance["inst_name"]]
            else:
                team_ids = instance.get("organization", [])
                if team_id and int(team_id) in team_ids:
                    instance['permission'] = [VIEW, OPERATE]
                elif set(team_ids) & teams:
                    # 实例关联的组织在用户有权限的组织内
                    instance['permission'] = [VIEW, OPERATE]
                else:
                    instance['permission'] = []

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
        if not self.check_creator(request, instance):
            has_permission = self.check_instance_permission(request, instance, operator=OPERATE)
            if not has_permission:
                return WebUtils.response_error(response_data=[], error_message="抱歉！您没有此实例的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

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
            return WebUtils.response_success()

        model_id = instances[0]["model_id"]
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_INSTANCES}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        for instance in instances:
            if not self.check_creator(request, instance):
                model_id = instance["model_id"]
                has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_INSTANCES,
                                                                           operator=OPERATE,
                                                                           model_id=model_id,
                                                                           permission_instances_map=permission_instances_map,
                                                                           team_id=current_team,
                                                                           instance=instance)

                if not has_permission:
                    return WebUtils.response_error(response_data=[],
                                                   error_message=f"抱歉！您没有此实例[{instance['inst_name']}]的权限",
                                                   status_code=status.HTTP_403_FORBIDDEN)

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
        if not self.check_creator(request, instance):
            has_permission = self.check_instance_permission(request, instance, operator=OPERATE)
            if not has_permission:
                return WebUtils.response_error(response_data=[], error_message="抱歉！您没有此实例的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

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
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_INSTANCES}.{model_id}"
                                                 )
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        for instance in instances:
            if not self.check_creator(request, instance):
                has_permission = CmdbRulesFormatUtil.has_object_permission(obj_type=PERMISSION_INSTANCES,
                                                                           operator=OPERATE,
                                                                           model_id=model_id,
                                                                           permission_instances_map=permission_instances_map,
                                                                           team_id=current_team,
                                                                           instance=instance)

                if not has_permission:
                    return WebUtils.response_error(response_data=[],
                                                   error_message=f"抱歉！您没有此实例[{instance['inst_name']}]的权限",
                                                   status_code=status.HTTP_403_FORBIDDEN)

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

        if not self.check_creator(request, src_inst):
            if not self.check_instance_permission(request, src_inst, operator=OPERATE):
                return WebUtils.response_error(response_data=[],
                                               error_message=f"抱歉！您没有此实例[{src_inst['inst_name']}]的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

        if not self.check_creator(request, dst_inst):
            if not self.check_instance_permission(request, dst_inst, operator=OPERATE):
                return WebUtils.response_error(response_data=[],
                                               error_message=f"抱歉！您没有此实例[{dst_inst['inst_name']}]的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

        asso = InstanceManage.instance_association_create(request.data, request.user.username)
        return WebUtils.response_success(asso)

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
        if not self.check_creator(request, instance):
            if not self.check_instance_permission(request, instance, operator=VIEW):
                return WebUtils.response_error(response_data=[], error_message="抱歉！您没有此实例的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)
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
        if not self.check_creator(request, instance):
            if not self.check_instance_permission(request, instance, operator=VIEW):
                return WebUtils.response_error(response_data=[], error_message="抱歉！您没有此实例的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

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
            # 检查是否上传了文件
            uploaded_file = request.data.get("file")
            if not uploaded_file:
                return JsonResponse({
                    "data": [], 
                    "result": False, 
                    "message": "请上传Excel文件"
                })
            
            import_result = InstanceManage().inst_import_support_edit(
                model_id=model_id,
                file_stream=uploaded_file.file,
                operator=request.user.username,
            )
            
            # 根据返回的结果结构判断成功或失败
            if isinstance(import_result, dict):
                return JsonResponse({
                    "data": [], 
                    "result": import_result["success"], 
                    "message": import_result["message"]
                })
            else:
                # 兼容旧的字符串返回格式
                is_success = not str(import_result).startswith("数据导入失败")
                return JsonResponse({
                    "data": [], 
                    "result": is_success, 
                    "message": str(import_result)
                })
                
        except Exception as e:
            logger.error(f"模型 {model_id} 数据导入异常: {str(e)}", exc_info=True)
            return JsonResponse({
                "data": [], 
                "result": False, 
                "message": f"数据导入异常，请检查文件格式和内容: {str(e)}"
            })

    @HasPermission("asset_info-View")
    @action(methods=["post"], detail=False, url_path=r"(?P<model_id>.+?)/inst_export")
    def inst_export(self, request, model_id):
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permission_rules(user=request.user,
                                                 current_team=current_team, app_name=APP_NAME,
                                                 permission_key=f"{PERMISSION_INSTANCES}.{model_id}")
        rules = _permission_rules.get("instance", [])
        _team = format_groups_params(teams=_permission_rules.get("team", []))
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_list(rules=rules)
        inst_names = list(permission_instances_map.keys())

        # 获取导出参数
        attr_list = request.data.get("attr_list", [])
        association_list = request.data.get("association_list", [])
        inst_ids = request.data.get("inst_ids", [])

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f"attachment;filename={f'{model_id}_export.xlsx'}"
        response.write(InstanceManage.inst_export(
            model_id,
            inst_ids,
            _team,
            inst_names,
            attr_list=attr_list,
            association_list=association_list
        ).read())
        return response

    @HasPermission("search-View")
    @action(methods=["post"], detail=False)
    def fulltext_search(self, request):
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permissions_rules(user=request.user,
                                                  current_team=current_team, app_name=APP_NAME,
                                                  permission_key=PERMISSION_INSTANCES
                                                  )
        _team = format_groups_params(teams=[int(current_team)])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_count_list(
            rules=_permission_rules.get("data", []))
        inst_names = list(permission_instances_map.keys())

        result = InstanceManage.fulltext_search(
            user_groups=_team,
            roles=[],
            search=request.data.get("search", ""),
            inst_names=inst_names
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
            return WebUtils.response_error(response_data=[], error_message="实例不存在",
                                           status_code=status.HTTP_404_NOT_FOUND)
        if not self.check_creator(request, instance):
            if not self.check_instance_permission(request, instance, operator=VIEW):
                return WebUtils.response_error(response_data=[], error_message="抱歉！您没有此实例的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

        result = InstanceManage.topo_search(int(inst_id))
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
            return WebUtils.response_error(response_data=[], error_message="实例不存在",
                                           status_code=status.HTTP_404_NOT_FOUND)

        if not self.check_creator(request, instance):
            if not self.check_instance_permission(request, instance, operator=VIEW):
                return WebUtils.response_error(response_data=[], error_message="抱歉！您没有此实例的权限",
                                               status_code=status.HTTP_403_FORBIDDEN)

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

    @action(methods=["get"], detail=False, url_path=r"(?P<model_id>.+?)/show_field/detail")
    @HasPermission("asset_info-View")
    def get_info(self, request, model_id):
        result = InstanceManage.get_info(model_id, request.user.username)
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path=r"model_inst_count")
    @HasPermission("asset_info-View")
    def model_inst_count(self, request):
        current_team = request.COOKIES.get("current_team")
        _permission_rules = get_permissions_rules(user=request.user,
                                                  current_team=current_team, app_name=APP_NAME,
                                                  permission_key=PERMISSION_INSTANCES
                                                  )
        _team = format_groups_params(teams=[int(current_team)])
        permission_instances_map = CmdbRulesFormatUtil().format_permission_instances_count_list(
            rules=_permission_rules.get("data", []))
        inst_names = list(permission_instances_map.keys())
        result = InstanceManage.model_inst_count(user_groups=_team, inst_names=inst_names)
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
        _data = [{"proxy_id": i['id'], "proxy_name": i['name']} for i in data]
        return WebUtils.response_success(_data)
