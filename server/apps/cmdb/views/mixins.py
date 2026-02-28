"""
CMDB Permission Mixin

Consolidates repetitive permission checking logic used across CMDB ViewSets.
This mixin provides unified methods for:
- Extracting user organizations from objects
- Checking object-level permissions
- Validating creator + organization access

Usage:
    class InstanceViewSet(CmdbPermissionMixin, viewsets.ViewSet):
        ...
"""

from typing import Optional

from rest_framework import status

from apps.cmdb.constants.constants import (
    OPERATE,
    PERMISSION_INSTANCES,
    PERMISSION_MODEL,
    VIEW,
)
from apps.cmdb.utils.base import get_organization_and_children_ids, get_current_team_from_request
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.utils.web_utils import WebUtils


class CmdbPermissionMixin:
    """
    Mixin providing common permission checking methods for CMDB ViewSets.

    Consolidates duplicate permission logic from InstanceViewSet and ModelViewSet
    into a single, reusable implementation.
    """

    # Override in subclass if using different field name (e.g., "group" for models)
    organization_field = "organization"

    @staticmethod
    def get_user_organizations(request, obj, org_field: str = "organization") -> list:
        """
        Get the intersection of user's groups and object's organizations.

        Args:
            request: The HTTP request object with user info
            obj: The object (instance or model) with organization/group data
            org_field: Field name containing organization IDs (default: "organization")

        Returns:
            List of organization IDs the user has access to for this object
        """
        user_groups = {i["id"] for i in request.user.group_list}
        obj_orgs = obj.get(org_field, [])
        return list(set(obj_orgs) & user_groups)

    @staticmethod
    def is_creator_with_org_access(request, instance) -> bool:
        """
        Check if the current user is the creator AND has organization access.

        This is a fast-path check: if the user created the object and is in one
        of its organizations, they have full access without further permission checks.

        Args:
            request: The HTTP request object
            instance: The instance object with 'organization' and '_creator' fields

        Returns:
            True if user is creator with org access, False otherwise
        """
        organizations = instance.get("organization", [])
        current_team = get_current_team_from_request(request, required=False)
        include_children = request.COOKIES.get("include_children") == "1"

        if include_children:
            user_teams = get_organization_and_children_ids(
                tree_data=request.user.group_tree, target_id=current_team
            )
            if not set(organizations) & set(user_teams):
                return False
        else:
            if current_team not in organizations:
                return False

        return instance.get("_creator") == request.user.username

    def check_instance_permission(
        self,
        request,
        instance: dict,
        operator: str = VIEW,
    ) -> bool:
        """
        Check if user has permission to perform an operation on an instance.

        Args:
            request: The HTTP request object
            instance: The instance dict with 'organization' and 'model_id'
            operator: The operation type (VIEW or OPERATE)

        Returns:
            True if user has permission, False otherwise
        """
        user_groups = {i["id"] for i in request.user.group_list}
        include_children = request.COOKIES.get("include_children") == "1"
        if include_children:
            current_team = get_current_team_from_request(request, required=False)
            if current_team:
                child_groups = get_organization_and_children_ids(
                    tree_data=request.user.group_tree, target_id=current_team
                )
                if child_groups:
                    user_groups = set(child_groups)
                else:
                    user_groups = {current_team}
        organizations = list(set(instance.get("organization", [])) & user_groups)
        if not organizations:
            return False

        model_id = instance["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id
        )

        return CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_INSTANCES,
            operator=operator,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=instance,
        )

    def check_model_permission(
        self,
        request,
        model_info: dict,
        operator: str = VIEW,
        default_group_id: Optional[int] = None,
    ) -> bool:
        """
        Check if user has permission to perform an operation on a model.

        Args:
            request: The HTTP request object
            model_info: The model dict with 'group' and 'model_id'
            operator: The operation type (VIEW or OPERATE)
            default_group_id: The default group ID for special VIEW handling

        Returns:
            True if user has permission, False otherwise
        """
        user_groups = {i["id"] for i in request.user.group_list}
        organizations = list(set(model_info.get("group", [])) & user_groups)
        if not organizations:
            return False

        model_id = model_info["model_id"]
        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request, model_id=model_id, permission_type=PERMISSION_MODEL
        )

        return CmdbRulesFormatUtil.has_object_permission(
            obj_type=PERMISSION_MODEL,
            operator=operator,
            model_id=model_id,
            permission_instances_map=permissions_map,
            instance=model_info,
            default_group_id=default_group_id,
        )

    def require_instance_permission(
        self,
        request,
        instance: dict,
        operator: str = VIEW,
        error_message: Optional[str] = None,
    ):
        """
        Check instance permission and return error response if denied.

        Args:
            request: The HTTP request object
            instance: The instance dict
            operator: The operation type (VIEW or OPERATE)
            error_message: Custom error message (optional)

        Returns:
            None if permission granted, or WebUtils.response_error if denied
        """
        # Fast path: creator with org access has full permission
        if self.is_creator_with_org_access(request, instance):
            return None

        organizations = self.get_user_organizations(request, instance, "organization")
        if not organizations:
            return WebUtils.response_error(
                error_message or "抱歉！您没有此实例的权限",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not self.check_instance_permission(request, instance, operator):
            return WebUtils.response_error(
                error_message or "抱歉！您没有此实例的权限",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return None

    def require_model_permission(
        self,
        request,
        model_info: dict,
        operator: str = VIEW,
        default_group_id: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """
        Check model permission and return error response if denied.

        Args:
            request: The HTTP request object
            model_info: The model dict
            operator: The operation type (VIEW or OPERATE)
            default_group_id: The default group ID for special VIEW handling
            error_message: Custom error message (optional)

        Returns:
            None if permission granted, or WebUtils.response_error if denied
        """
        organizations = self.get_user_organizations(request, model_info, "group")
        if not organizations:
            return WebUtils.response_error(
                error_message or "抱歉！您没有此模型的权限",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if not self.check_model_permission(
            request, model_info, operator, default_group_id
        ):
            return WebUtils.response_error(
                error_message or "抱歉！您没有此模型的权限",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return None
