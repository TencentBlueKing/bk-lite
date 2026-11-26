from django.db import transaction
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.utils import viewset_utils
from apps.job_mgmt.serializers.organization_batch import SelectionSerializer
from apps.job_mgmt.services.resource_organizations import SELECTION_LIMIT, plan_organizations, write_organizations
from apps.job_mgmt.utils.team_authz import normalize_team
from apps.job_mgmt.views.mixins import BatchDeleteMixin
from apps.system_mgmt.models import Group
from apps.system_mgmt.utils.operation_log_utils import log_operation


class OrganizationBatchMixin(BatchDeleteMixin):
    organization_preview_fields = ("id", "name", "team")
    batch_delete_fields = ("id", "team")
    normalize_membership_for_edit = False
    batch_delete_serializer_class = SelectionSerializer

    def validate_changed_organizations(self, changed, operation, organization):
        """应用资源特有的组织约束。"""

    def write_changed_organizations(self, changed, operation, organization, user):
        write_organizations(changed, model=self.queryset.model, user=user)

    def get_selection_ids(self, request):
        visible = self.get_queryset_by_permission(request, self.filter_queryset(self.get_queryset()))
        ids = list(visible.order_by(self.ORDERING_FIELD).values_list("pk", flat=True)[: SELECTION_LIMIT + 1])
        if len(ids) > SELECTION_LIMIT:
            message = self.loader.get("error.batch_selection_limit", "Select up to {limit} resources at a time.")
            return Response({"detail": message.format(limit=SELECTION_LIMIT)}, status=400)
        return Response({"ids": ids})

    def _check_batch_operate_access(self, request, resources, ids, current_team, *, allow_descendants=False):
        denied = PermissionDenied(
            self.loader.get(
                "error.batch_operation_denied", "Some selected resources are unavailable or you do not have permission to operate on them."
            )
        )
        if len(resources) != len(ids) or getattr(request.user, "is_auditor", False):
            raise denied
        if request.user.is_superuser:
            return
        include_children = request.COOKIES.get("include_children") == "1"
        rules = viewset_utils.get_permission_rules(request.user, current_team, self._get_app_name(), self.permission_key, include_children)
        if not isinstance(rules, dict):
            raise denied
        team_grants, instance_grants = rules.get("team", []), rules.get("instance", [])
        if not isinstance(team_grants, list) or not isinstance(instance_grants, list):
            raise denied
        scope = {current_team}
        if include_children:
            scope.update(self.extract_child_group_ids(getattr(request.user, "group_tree", []), current_team))
        granted_teams = normalize_team(team_grants) & scope
        resource_scope = scope if allow_descendants else {current_team}
        if allow_descendants and current_team in granted_teams:
            granted_teams = scope
        operable = {
            str(item["id"])
            for item in instance_grants
            if isinstance(item, dict) and "id" in item and isinstance(item.get("permission"), list) and "Operate" in item["permission"]
        }
        for resource in resources:
            if allow_descendants or not self.normalize_membership_for_edit:
                # 与单条操作的团队 ID 原类型检查一致。
                teams = {member for member in resource.team if type(member) is int} if isinstance(resource.team, list) else set()
            else:
                teams = normalize_team(resource.team)
            if resource_scope.isdisjoint(teams) or not (teams & granted_teams or str(resource.pk) in operable):
                raise denied

    @transaction.atomic
    def perform_organization_adjustment(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = serializer.validated_data
        ids, organization, operation = command["ids"], command["organization"], command["operation"]
        current_team = self._validate_current_team_permission(request)
        self._validate_org_field_permission(request, [organization])
        applying = "preview_token" in command
        organizations = Group.objects.filter(pk=organization, is_delete=False)
        resources = self.get_queryset().filter(pk__in=ids).only(*self.organization_preview_fields).order_by("pk")
        if applying:
            organizations = organizations.select_for_update()
            resources = resources.select_for_update()
        if not organizations.exists():
            return Response({"detail": self.loader.get("error.batch_organization_missing", "This organization is unavailable.")}, status=400)
        resources = list(resources)
        self._check_batch_operate_access(request, resources, ids, current_team)
        changed, preview = plan_organizations(
            resources,
            resource_kind=self.queryset.model._meta.model_name,
            operation=operation,
            organization=organization,
            actor=(request.user.username, request.user.domain, current_team),
        )
        self.validate_changed_organizations(changed, operation, organization)
        if not applying:
            return Response(preview)
        if not constant_time_compare(preview["preview_token"], command["preview_token"]):
            message = self.loader.get("error.batch_preview_changed", "Resource organizations have changed. Refresh the preview.")
            return Response({"detail": message}, status=409)
        if preview["blocked"] and not command["exclude_blocked"]:
            message = self.loader.get("error.batch_exclude_required", "Exclude resources that would lose their last organization.")
            return Response({"detail": message}, status=400)
        if changed:
            self.write_changed_organizations(changed, operation, organization, request.user)
            log_operation(
                request,
                "update",
                "job",
                f"批量调整{self.batch_delete_log_label}组织（共{len(changed)}个）",
                target_type=self.queryset.model._meta.model_name,
                detail={
                    "operation": operation,
                    "organization": organization,
                    f"{self.queryset.model._meta.model_name}_ids": [resource.pk for resource in changed],
                },
            )
        return Response(preview)

    def get_batch_delete_queryset(self, ids):
        request = self.request
        current_team = None if request.user.is_superuser else self._validate_current_team_permission(request)
        resources = super().get_batch_delete_queryset(ids).only(*self.batch_delete_fields).order_by("pk").select_for_update()
        selected = list(resources)
        if not selected and request.user.is_superuser:
            return resources.none()
        self._check_batch_operate_access(request, selected, ids, current_team, allow_descendants=True)
        return resources

    @transaction.atomic
    def perform_batch_delete(self, request):
        return super().perform_batch_delete(request)
