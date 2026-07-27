from collections.abc import Mapping

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.open_base import OpenAPIViewSet
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.k3s_onboarding import K3SOnboardingService
from apps.monitor.views.monitor_instance import (
    _build_actor_context,
    _ensure_operate_instances,
    _ensure_target_organizations,
)


def _payload(data, *, required, optional=()):
    if not isinstance(data, Mapping):
        raise ValidationAppException("Request body must be an object")
    allowed = set(required) | set(optional)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValidationAppException(
            f"Unknown request fields: {', '.join(unknown)}"
        )
    missing = sorted(field for field in required if field not in data)
    if missing:
        raise ValidationAppException(
            f"Missing required fields: {', '.join(missing)}"
        )
    return {field: data[field] for field in allowed if field in data}


class K3SOnboardingViewSet(viewsets.ViewSet):
    @action(methods=["post"], detail=False, url_path="create_instance")
    def create_instance(self, request):
        data = _payload(
            request.data,
            required={
                "monitor_object_id",
                "instance_id",
                "name",
                "organizations",
            },
        )
        actor_context = _build_actor_context(request)
        _ensure_target_organizations(
            data["organizations"],
            actor_context,
        )
        result = K3SOnboardingService.create_instance(**data)
        return WebUtils.response_success(result)

    @action(methods=["post"], detail=False, url_path="install_command")
    def install_command(self, request):
        data = _payload(
            request.data,
            required={"instance_id", "cloud_region_id"},
        )
        actor_context = _build_actor_context(request)
        _ensure_operate_instances(
            request,
            [data["instance_id"]],
            actor_context,
        )
        result = K3SOnboardingService.generate_install_commands(**data)
        return WebUtils.response_success(result)

    @action(methods=["get"], detail=False, url_path="verify")
    def verify(self, request):
        data = _payload(
            request.query_params,
            required={"instance_id"},
        )
        actor_context = _build_actor_context(request)
        _ensure_operate_instances(
            request,
            [data["instance_id"]],
            actor_context,
        )
        result = K3SOnboardingService.verify_reporting(data["instance_id"])
        return WebUtils.response_success(result)


class K3SOnboardingOpenViewSet(OpenAPIViewSet):
    @action(methods=["post"], detail=False, url_path="render")
    def render(self, request):
        data = _payload(request.data, required={"token"})
        result = K3SOnboardingService.render_manifest(data["token"])
        response = HttpResponse(
            result["yaml"],
            content_type="text/yaml; charset=utf-8",
        )
        response["X-Token-Remaining-Usage"] = str(
            result["remaining_usage"]
        )
        return response
