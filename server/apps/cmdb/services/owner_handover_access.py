from django.db.models import Q

from apps.cmdb.constants.constants import OPERATE, PERMISSION_INSTANCES
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.system_mgmt.models import User as DirectoryUser
from apps.system_mgmt.models.user import EmploymentStatus


class OwnerHandoverRejected(Exception):
    def __init__(self, code, message, status=400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def user_label(person):
    if not person:
        return ""
    display_name = str(person.get("display_name") or "").strip()
    username = str(person.get("username") or "")
    if display_name:
        return f"{display_name}({username})"
    return username


def as_user_ids(value):
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str) and value.isdigit():
        return [int(value)]
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, int):
            result.append(item)
        elif isinstance(item, str) and item.isdigit():
            result.append(int(item))
    return result


def replace_user_ids(current, from_user_id, to_user_id):
    ids = as_user_ids(current)
    if from_user_id not in ids:
        return None
    replaced = []
    seen = set()
    for item in ids:
        value = to_user_id if item == from_user_id else item
        if value in seen:
            continue
        seen.add(value)
        replaced.append(value)
    return replaced


def organization_label(instance):
    display = instance.get("organization_display")
    if isinstance(display, str) and display.strip():
        return display
    return ""


def _org_ids(instance):
    return as_user_ids(instance.get("organization"))


def allows_instance(user, team_id, include_children, instance):
    orgs = set(_org_ids(instance))
    if not orgs:
        return False
    team_id = int(team_id)
    if not include_children and team_id not in orgs:
        return False
    allowed = set(CmdbRulesFormatUtil.get_authorized_team_ids(user, team_id, include_children))
    if not (orgs & allowed):
        return False
    if getattr(user, "is_superuser", False):
        return True
    group_ids = set()
    for item in getattr(user, "group_list", []) or []:
        group_id = item.get("id") if isinstance(item, dict) else item
        if group_id is not None:
            group_ids.add(int(group_id))
    if team_id in group_ids and instance.get("_creator") == getattr(user, "username", None):
        if include_children:
            from apps.cmdb.utils.base import get_organization_and_children_ids

            teams = set(
                get_organization_and_children_ids(
                    tree_data=getattr(user, "group_tree", []) or [],
                    target_id=team_id,
                )
            )
            if orgs & teams:
                return True
        elif team_id in orgs:
            return True
    permissions_map = CmdbRulesFormatUtil.format_user_context_permissions(
        user,
        team_id,
        include_children,
        instance.get("model_id") or "",
    )
    return CmdbRulesFormatUtil.has_object_permission(
        PERMISSION_INSTANCES,
        OPERATE,
        instance.get("model_id") or "",
        permissions_map,
        instance,
    )


class UserDirectory:
    def __init__(self, domain):
        self.domain = domain

    def _row(self, person):
        return {
            "id": person.id,
            "username": person.username,
            "display_name": person.display_name,
            "disabled": person.disabled,
            "employment_status": person.employment_status,
        }

    def get(self, user_id):
        person = DirectoryUser.objects.filter(id=user_id, domain=self.domain).first()
        if person is None:
            return None
        return self._row(person)

    def search(self, role, keyword, limit=20):
        queryset = DirectoryUser.objects.filter(domain=self.domain)
        if role == "to":
            queryset = queryset.filter(disabled=False).exclude(employment_status=EmploymentStatus.RESIGNED)
        keyword = str(keyword or "").strip()
        if keyword:
            queryset = queryset.filter(Q(username__icontains=keyword) | Q(display_name__icontains=keyword))
        people = queryset.order_by("display_name", "id")[:limit]
        rows = []
        for person in people:
            row = self._row(person)
            row["label"] = user_label(row)
            rows.append(row)
        return rows
