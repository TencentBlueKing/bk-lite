from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from apps.opspilot.models import WikiKnowledgeBase


def _normalized_team_ids(values):
    if isinstance(values, (dict, int, str)):
        values = [values]
    normalized = set()
    for value in values or []:
        if isinstance(value, dict):
            value = value.get("id")
        if isinstance(value, bool):
            continue
        try:
            normalized.add(int(value))
        except (TypeError, ValueError):
            continue
    return normalized


def accessible_wiki_knowledge_base_ids(user):
    """Return accessible KB ids without backend-specific JSON lookups.

    ``None`` means unrestricted (superuser). A normal user with no valid groups
    receives an empty set, so permission data always fails closed.
    """
    if getattr(user, "is_superuser", False):
        return None
    user_group_ids = _normalized_team_ids(getattr(user, "group_list", []) or [])
    if not user_group_ids:
        return set()

    accessible_ids = set()
    knowledge_bases = WikiKnowledgeBase.objects.values_list("id", "team").iterator(chunk_size=500)
    for knowledge_base_id, team in knowledge_bases:
        if _normalized_team_ids(team) & user_group_ids:
            accessible_ids.add(knowledge_base_id)
    return accessible_ids


class WikiTeamScopeMixin:
    """Apply one team boundary to all Wiki resources and custom actions."""

    team_scope_field = "knowledge_base_id"
    team_permission_message = "无权访问该团队数据"

    def _accessible_knowledge_base_ids(self):
        if not hasattr(self, "_wiki_accessible_knowledge_base_ids"):
            self._wiki_accessible_knowledge_base_ids = accessible_wiki_knowledge_base_ids(self.request.user)
        return self._wiki_accessible_knowledge_base_ids

    def scope_team_queryset(self, queryset, *, field=None):
        accessible_ids = self._accessible_knowledge_base_ids()
        if accessible_ids is None:
            return queryset
        lookup = field or self.team_scope_field
        return queryset.filter(**{f"{lookup}__in": accessible_ids})

    def get_queryset(self):
        return self.scope_team_queryset(super().get_queryset())

    def _object_knowledge_base_id(self, instance):
        if self.team_scope_field == "id":
            return instance.pk
        return getattr(instance, self.team_scope_field)

    def ensure_object_team_access(self, instance):
        accessible_ids = self._accessible_knowledge_base_ids()
        if accessible_ids is None:
            return
        if self._object_knowledge_base_id(instance) not in accessible_ids:
            raise PermissionDenied(self.team_permission_message)

    def get_object(self):
        """Return 403 for a real cross-team id while keeping list queries scoped."""
        queryset = self.filter_queryset(super().get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert lookup_url_kwarg in self.kwargs, (
            f"Expected view {self.__class__.__name__} to be called with a URL keyword " f'argument named "{lookup_url_kwarg}".'
        )
        instance = get_object_or_404(
            queryset,
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]},
        )
        self.ensure_object_team_access(instance)
        self.check_object_permissions(self.request, instance)
        return instance

    def accessible_knowledge_base_or_none(self, raw_id):
        try:
            knowledge_base_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        queryset = self.scope_team_queryset(
            WikiKnowledgeBase.objects.all(),
            field="id",
        )
        knowledge_base = queryset.filter(pk=knowledge_base_id).first()
        if knowledge_base is not None:
            return knowledge_base
        if WikiKnowledgeBase.objects.filter(pk=knowledge_base_id).exists():
            raise PermissionDenied(self.team_permission_message)
        return None

    def ensure_team_accessible_ids(self, queryset, object_ids, *, field=None):
        """Reject a mixed-team batch before any item is changed.

        Missing ids retain existing endpoint semantics (usually skipped); only
        existing objects outside the caller's accessible KB ids are rejected.
        """
        accessible_ids = self._accessible_knowledge_base_ids()
        if accessible_ids is None:
            return
        lookup = field or self.team_scope_field
        has_foreign_object = queryset.filter(pk__in=object_ids).exclude(**{f"{lookup}__in": accessible_ids}).exists()
        if has_foreign_object:
            raise PermissionDenied(self.team_permission_message)

    def ensure_knowledge_base_ids_accessible(self, knowledge_base_ids):
        self.ensure_team_accessible_ids(
            WikiKnowledgeBase.objects.all(),
            knowledge_base_ids,
            field="id",
        )

    def validate_team_assignment(self, team):
        if getattr(self.request.user, "is_superuser", False):
            return
        requested_team_ids = _normalized_team_ids(team)
        user_group_ids = _normalized_team_ids(getattr(self.request.user, "group_list", []) or [])
        if not requested_team_ids or not requested_team_ids.issubset(user_group_ids):
            raise PermissionDenied(self.team_permission_message)
