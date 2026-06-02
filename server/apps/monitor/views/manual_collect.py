from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.views.monitor_instance import (
    _build_actor_context,
    _ensure_operate_instances,
    _ensure_target_organizations,
)
from apps.rpc.node_mgmt import NodeMgmt


class ManualCollect(viewsets.ViewSet):

    @action(methods=['get'], detail=False, url_path='cloud_region_list')
    def cloud_area_list(self, request):
        data = NodeMgmt().cloud_region_list()
        return WebUtils.response_success(data)

    # 创建手动监控实例
    @action(methods=['post'], detail=False, url_path='create_manual_instance')
    def create_manual_instance(self, request):
        actor_context = _build_actor_context(request)
        _ensure_target_organizations(request.data.get("organizations", []), actor_context)
        data = ManualCollectService.create_manual_collect_instance(request.data)
        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='flow_asset')
    def flow_asset(self, request):
        actor_context = _build_actor_context(request)
        with transaction.atomic():
            FlowOnboardingService.lock_monitor_object(monitor_object_id=request.data["monitor_object_id"])
            instance_id = request.data.get("instance_id")
            payload = dict(request.data)
            if instance_id:
                _ensure_operate_instances(request, [instance_id], actor_context)
            else:
                existing_instance = FlowOnboardingService.find_existing_asset(
                    monitor_object_id=request.data["monitor_object_id"],
                    cloud_region_id=request.data["cloud_region_id"],
                    ip=request.data["ip"],
                    for_update=True,
                )
                if existing_instance:
                    _ensure_operate_instances(request, [existing_instance.id], actor_context)
                    payload["instance_id"] = existing_instance.id
            _ensure_target_organizations(request.data.get("organizations", []), actor_context)
            data = FlowOnboardingService.create_or_bind_asset(**payload)
        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='flow_asset/update')
    def update_flow_asset(self, request):
        actor_context = _build_actor_context(request)
        _ensure_operate_instances(request, [request.data["instance_id"]], actor_context)
        _ensure_target_organizations(request.data.get("organizations", []), actor_context)
        data = FlowOnboardingService.update_asset(**request.data)
        return WebUtils.response_success(data)

    # 生成安装命令
    @action(methods=['post'], detail=False, url_path='generate_install_command')
    def generate_install_command(self, request):
        actor_context = _build_actor_context(request)
        _ensure_operate_instances(request, [request.data["instance_id"]], actor_context)
        data = ManualCollectService.generate_install_command(request.data["instance_id"], request.data["cloud_region_id"])
        return WebUtils.response_success(data)

    # 检查手动采集状态
    @action(methods=['post'], detail=False, url_path='check_collect_status')
    def check_collect_status(self, request):
        actor_context = _build_actor_context(request)
        _ensure_operate_instances(request, [request.data["instance_id"]], actor_context)
        success = ManualCollectService.check_collect_status(request.data["monitor_object_id"], request.data["instance_id"])
        return WebUtils.response_success(dict(success=success))
