from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import MonitorInstance, MonitorObject, CollectConfig, MonitorObjectOrganizationRule
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.rpc.node_mgmt import NodeMgmt


class MonitorInstanceVieSet(viewsets.ViewSet):

    @action(methods=['get'], detail=False, url_path='query_params_enum/(?P<name>[^/.]+)')
    def get_query_params_enum(self, request, name):
        data = InstanceSearch.get_query_params_enum(name)
        return WebUtils.response_success(data)

    @action(methods=['get'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/list')
    def monitor_instance_list(self, request, monitor_object_id):
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
        )
        qs = permission_filter(MonitorInstance, permission, team_key="monitorinstanceorganization__organization__in", id_key="id__in")
        page, page_size = request.GET.get("page", 1), request.GET.get("page_size", 10)
        data = MonitorObjectService.get_monitor_instance(
            int(monitor_object_id),
            int(page),
            int(page_size),
            request.GET.get("name"),
            qs,
            bool(request.GET.get("add_metrics", False)),
        )
        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for instance_info in data["results"]:
            if instance_info["instance_id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["instance_id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/search')
    def monitor_instance_search(self, request, monitor_object_id):

        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise BaseAppException("Monitor object does not exist")

        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
        )
        qs = permission_filter(MonitorInstance, permission, team_key="monitorinstanceorganization__organization__in", id_key="id__in")

        search_obj = InstanceSearch(
            monitor_obj,
            dict(**request.data),
            qs=qs,
        )
        data = search_obj.search()
        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for instance_info in data["results"]:
            if instance_info["instance_id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["instance_id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION
        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/generate_instance_id')
    def generate_monitor_instance_id(self, request, monitor_object_id):
        result = MonitorObjectService.generate_monitor_instance_id(
            int(monitor_object_id),
            request.data["monitor_instance_name"],
            request.data["interval"],
        )
        return WebUtils.response_success(result)

    @action(methods=['post'], detail=False, url_path='(?P<monitor_object_id>[^/.]+)/check_monitor_instance')
    def check_monitor_instance(self, request, monitor_object_id):
        MonitorObjectService.check_monitor_instance(
            int(monitor_object_id),
            request.data
        )
        return WebUtils.response_success()

    @action(methods=['get'], detail=False, url_path='autodiscover_monitor_instance')
    def autodiscover_monitor_instance(self, request):
        MonitorObjectService.autodiscover_monitor_instance()
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='remove_monitor_instance')
    def remove_monitor_instance(self, request):
        instance_ids = request.data.get("instance_ids", [])
        MonitorInstance.objects.filter(id__in=instance_ids).update(is_deleted=True)
        if request.data.get("clean_child_config"):
            config_objs = CollectConfig.objects.filter(monitor_instance_id__in=instance_ids)
            child_configs, configs = [], []
            for config in config_objs:
                if config.is_child:
                    child_configs.append(config.id)
                else:
                    configs.append(config.id)
            # 删除子配置
            NodeMgmt().delete_child_configs(child_configs)
            # 删除配置
            NodeMgmt().delete_configs(configs)
            # 删除配置对象
            config_objs.delete()

        # 同步删除实例关联的分组规则
        MonitorObjectOrganizationRule.objects.filter(monitor_instance_id__in=instance_ids).delete()
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='update_monitor_instance')
    def update_monitor_instance(self, request):
        MonitorObjectService.update_instance(
            request.data.get("instance_id"),
            request.data.get("name"),
            request.data.get("organizations", []),
        )
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='instances_remove_organizations')
    def instances_remove_organizations(self, request):
        """删除监控对象实例组织"""
        instance_ids = request.data.get("instance_ids", [])
        organizations = request.data.get("organizations", [])
        MonitorObjectService.remove_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='instances_add_organizations')
    def instances_add_organizations(self, request):
        """添加监控对象实例组织"""
        instance_ids = request.data.get("instance_ids", [])
        organizations = request.data.get("organizations", [])
        MonitorObjectService.add_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()

    @action(methods=['post'], detail=False, url_path='set_instances_organizations')
    def set_instances_organizations(self, request):
        """设置监控对象实例组织"""
        instance_ids = request.data.get("instance_ids", [])
        organizations = request.data.get("organizations", [])
        MonitorObjectService.set_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()