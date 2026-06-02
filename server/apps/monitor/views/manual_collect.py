import ipaddress

from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.views.monitor_instance import (
    _build_actor_context,
    _ensure_operate_instances,
    _ensure_target_organizations,
)
from apps.rpc.node_mgmt import NodeMgmt


FLOW_ASSET_REQUIRED_FIELDS = {"monitor_object_id", "protocol", "cloud_region_id", "ip", "name"}
FLOW_ASSET_OPTIONAL_FIELDS = {"organizations", "instance_id", "fallback_sampling_rate"}
UPDATE_FLOW_ASSET_REQUIRED_FIELDS = {"instance_id"}
UPDATE_FLOW_ASSET_OPTIONAL_FIELDS = {"name", "organizations", "cloud_region_id", "ip", "fallback_sampling_rate"}
SUPPORTED_FLOW_PROTOCOLS = getattr(FlowOnboardingService, "SUPPORTED_PROTOCOLS", {"netflow", "sflow"})


def _validate_integer_field(field, value):
    if value is None:
        raise ValidationAppException(f"Field {field} cannot be empty")
    if isinstance(value, bool):
        raise ValidationAppException(f"Field {field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValidationAppException(f"Field {field} must be an integer")
        try:
            return int(value)
        except ValueError as exc:
            raise ValidationAppException(f"Field {field} must be an integer") from exc
    raise ValidationAppException(f"Field {field} must be an integer")


def _validate_flow_identity_field(field, value):
    if field in {"monitor_object_id", "cloud_region_id"}:
        return _validate_integer_field(field, value)
    if field == "ip":
        if not isinstance(value, str) or not value.strip():
            raise ValidationAppException("Field ip cannot be empty")
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError as exc:
            raise ValidationAppException("Field ip must be a valid IP address") from exc
    return value


def _validate_protocol(_field, value):
    if not isinstance(value, str) or value not in SUPPORTED_FLOW_PROTOCOLS:
        raise ValidationAppException("Field protocol must be a supported flow protocol")
    return value


def _validate_fallback_sampling_rate(_field, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationAppException("Field fallback_sampling_rate must be a non-negative integer")
    return value


def _validate_organizations(_field, value):
    if not isinstance(value, (list, tuple)):
        raise ValidationAppException("Field organizations must be a list or tuple of integers")

    normalized = []
    seen = set()
    for org_id in value:
        if isinstance(org_id, bool):
            raise ValidationAppException("Field organizations must be a list or tuple of integers")
        if isinstance(org_id, int):
            normalized_id = org_id
        elif isinstance(org_id, str):
            stripped_value = org_id.strip()
            if not stripped_value:
                raise ValidationAppException("Field organizations must be a list or tuple of integers")
            try:
                normalized_id = int(stripped_value)
            except ValueError as exc:
                raise ValidationAppException("Field organizations must be a list or tuple of integers") from exc
        else:
            raise ValidationAppException("Field organizations must be a list or tuple of integers")

        if normalized_id not in seen:
            normalized.append(normalized_id)
            seen.add(normalized_id)

    return normalized


def _validate_existing_flow_instance(instance_id):
    validator = getattr(FlowOnboardingService, "validate_instance_id", None)
    if validator is not None:
        validator(instance_id=instance_id)
    return instance_id


def _build_conflict_permission_checker(request, actor_context):
    def checker(conflicting_instance):
        _ensure_operate_instances(request, [conflicting_instance.id], actor_context)

    return checker


def _validated_request_payload(data, *, required_fields, optional_fields, field_validators=None):
    payload = dict(data)
    allowed_fields = required_fields | optional_fields
    field_validators = field_validators or {}

    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise ValidationAppException(f"Unknown request fields: {', '.join(unknown_fields)}")

    missing_fields = sorted(field for field in required_fields if field not in payload)
    if missing_fields:
        raise ValidationAppException(f"Missing required fields: {', '.join(missing_fields)}")

    for field, validator in field_validators.items():
        if field in payload:
            payload[field] = validator(field, payload[field])

    return {field: payload[field] for field in payload if field in allowed_fields}


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
        payload = _validated_request_payload(
            request.data,
            required_fields=FLOW_ASSET_REQUIRED_FIELDS,
            optional_fields=FLOW_ASSET_OPTIONAL_FIELDS,
            field_validators={
                "monitor_object_id": _validate_flow_identity_field,
                "cloud_region_id": _validate_flow_identity_field,
                "ip": _validate_flow_identity_field,
                "protocol": _validate_protocol,
                "fallback_sampling_rate": _validate_fallback_sampling_rate,
                "organizations": _validate_organizations,
            },
        )
        actor_context = _build_actor_context(request)
        with transaction.atomic():
            instance_id = payload.get("instance_id")
            FlowOnboardingService.lock_monitor_object(
                monitor_object_id=payload["monitor_object_id"],
                require_supported=True,
            )
            if instance_id:
                _validate_existing_flow_instance(instance_id)
                _ensure_operate_instances(request, [instance_id], actor_context)
            else:
                existing_instance = FlowOnboardingService.find_reusable_asset(
                    monitor_object_id=payload["monitor_object_id"],
                    cloud_region_id=payload["cloud_region_id"],
                    ip=payload["ip"],
                    for_update=True,
                )
                if existing_instance:
                    _ensure_operate_instances(request, [existing_instance.id], actor_context)
                    payload["instance_id"] = existing_instance.id
                    payload["allow_deleted_instance_reuse"] = existing_instance.is_deleted
            _ensure_target_organizations(payload.get("organizations", []), actor_context)
            data = FlowOnboardingService.create_or_bind_asset(
                **payload,
                conflict_permission_checker=_build_conflict_permission_checker(request, actor_context),
            )
        return WebUtils.response_success(data)

    @action(methods=['post'], detail=False, url_path='flow_asset/update')
    def update_flow_asset(self, request):
        payload = _validated_request_payload(
            request.data,
            required_fields=UPDATE_FLOW_ASSET_REQUIRED_FIELDS,
            optional_fields=UPDATE_FLOW_ASSET_OPTIONAL_FIELDS,
            field_validators={
                "cloud_region_id": _validate_flow_identity_field,
                "ip": _validate_flow_identity_field,
                "fallback_sampling_rate": _validate_fallback_sampling_rate,
                "organizations": _validate_organizations,
            },
        )
        actor_context = _build_actor_context(request)
        _validate_existing_flow_instance(payload["instance_id"])
        _ensure_operate_instances(request, [payload["instance_id"]], actor_context)
        _ensure_target_organizations(payload.get("organizations", []), actor_context)
        data = FlowOnboardingService.update_asset(
            **payload,
            conflict_permission_checker=_build_conflict_permission_checker(request, actor_context),
        )
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
