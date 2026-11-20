"""Authenticated administrator UI; machine calls use the OpenAPI gateway."""

import hashlib

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.models import EnvironmentInstallGrant
from apps.node_mgmt.serializers.environment_install import (
    EnvironmentBundleRequestSerializer,
    EnvironmentComponentOptionsSerializer,
    EnvironmentGrantIDSerializer,
    EnvironmentGrantListSerializer,
    EnvironmentResultListSerializer,
)
from apps.node_mgmt.services.environment_bundle import classify_export_error, export_environment_bundle
from apps.node_mgmt.services.environment_install import EnvironmentInstallService
from apps.node_mgmt.views.installer import _validate_install_target_organizations
from apps.system_mgmt.models import SystemAPIToken


class EnvironmentInstallViewSet(ViewSet):
    @staticmethod
    def _grants(request):
        scope = resolve_current_team_data_scope(request)
        return EnvironmentInstallGrant.objects.filter(
            team=scope.current_team,
            owner=request.user.username,
            domain=request.user.domain,
        ).select_related("token", "package", "cloud_region")

    @action(detail=False, methods=["post"])
    @HasPermission("cloud_region_node-Edit")
    def export(self, request):
        serializer = EnvironmentBundleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        denied = _validate_install_target_organizations(request, [{"organizations": [data["organization"]]}])
        if denied is not None:
            return denied
        try:
            grant, artifact = export_environment_bundle(
                owner=request.user.username,
                domain=request.user.domain,
                **data,
            )
        except (ValueError, ObjectDoesNotExist, OSError) as exc:
            # Release files and configuration can contain credentials; never return their errors verbatim.
            return WebUtils.response_error(
                {"error_code": classify_export_error(exc)},
                "环境安装包导出预检失败，请核对发布文件、固定素材、CA 及云区域下载配置",
            )
        response = WebUtils.response_file(artifact, f"install-controller-{grant.id}.run")
        response["Cache-Control"] = "no-store"
        response["X-Environment-Grant-ID"] = str(grant.id)
        response["X-Artifact-SHA256"] = hashlib.sha256(artifact).hexdigest()
        return response

    @action(detail=False, methods=["get"])
    @HasPermission("cloud_region_node-Edit")
    def components(self, request):
        serializer = EnvironmentComponentOptionsSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return WebUtils.response_success(EnvironmentInstallService.component_options(serializer.validated_data["cloud_region_id"]))

    @action(detail=False, methods=["get"])
    @HasPermission("cloud_region_node-Edit")
    def grants(self, request):
        try:
            serializer = EnvironmentGrantListSerializer(data=getattr(request, "query_params", {}))
            serializer.is_valid(raise_exception=True)
            query = serializer.validated_data
            grants = self._grants(request)
            if "cloud_region_id" in query:
                grants = grants.filter(cloud_region_id=query["cloud_region_id"])
            total = grants.count()
            offset = (query["page"] - 1) * query["page_size"]
            grants = grants.annotate(used_nodes=Count("attempts")).order_by("-created_at", "-id")[offset : offset + query["page_size"]]
            data = [
                {
                    "id": str(grant.id),
                    "cloud_region_id": grant.cloud_region_id,
                    "organization": grant.team,
                    "package_version": grant.package_version,
                    "package_sha256": grant.package_sha256,
                    "required_components": grant.required_components,
                    "max_nodes": grant.max_nodes,
                    "used_nodes": grant.used_nodes,
                    "enabled": grant.token.enabled,
                    "expires_at": grant.token.expires_at,
                    "created_at": grant.created_at,
                }
                for grant in grants
            ]
            return WebUtils.response_success({"count": total, "items": data})
        except BaseAppException:
            return WebUtils.response_403("安装授权范围不可访问")

    @action(detail=False, methods=["post"])
    @HasPermission("cloud_region_node-Edit")
    def revoke(self, request):
        serializer = EnvironmentGrantIDSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                grant = self._grants(request).select_for_update(of=("self",)).get(pk=serializer.validated_data["grant_id"])
                SystemAPIToken.objects.filter(pk=grant.token_id).update(enabled=False)
            return WebUtils.response_success()
        except (BaseAppException, ObjectDoesNotExist):
            return WebUtils.response_403("安装授权范围不可访问")

    @action(detail=False, methods=["post"])
    @HasPermission("cloud_region_node-Edit")
    def results(self, request):
        serializer = EnvironmentResultListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            grant = self._grants(request).get(pk=serializer.validated_data["grant_id"])
            query = serializer.validated_data
            total = grant.attempts.count()
            offset = (query["page"] - 1) * query["page_size"]
            rows = list(
                grant.attempts.order_by("-created_at", "-id").values(
                    "id",
                    "node_id",
                    "ip",
                    "node_name",
                    "created_at",
                    "registered_at",
                    "last_heartbeat_at",
                    "failure_stage",
                    "error_code",
                    "last_reported_at",
                )[offset : offset + query["page_size"]]
            )
            return WebUtils.response_success({"count": total, "items": EnvironmentInstallService.describe_attempts(grant, rows)})
        except (BaseAppException, ObjectDoesNotExist):
            return WebUtils.response_403("安装授权范围不可访问")
