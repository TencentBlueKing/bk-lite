"""同一份资源归属快照驱动预览与提交。"""

import json
from collections import Counter

from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.core.models.maintainer_info import maintainer_kwargs
from apps.core.utils.user_group import normalize_user_group_ids

SELECTION_LIMIT = 1000


def organization_ids(value):
    return list(dict.fromkeys(normalize_user_group_ids(value if isinstance(value, list) else [value])))


def plan_organizations(resources, *, resource_kind, operation, organization, actor):
    snapshot = []
    combinations = Counter()
    blocked = []
    changed = []
    unchanged = 0
    for resource in resources:
        before = set(organization_ids(resource.team))
        after = before | {organization} if operation == "add" else before - {organization}
        old_ids = tuple(sorted(before))
        new_ids = tuple(sorted(after))
        snapshot.append((resource.pk, old_ids))
        combinations[(old_ids, new_ids)] += 1
        if before == after:
            unchanged += 1
        elif not after:
            blocked.append({"id": resource.pk, "name": resource.name})
        else:
            # 部分存量归属以对象保存。将无关成员改写为整数会改变列表的标量授权匹配结果。
            members = resource.team
            if not isinstance(members, list):
                members = [] if members is None else [members]
            if operation == "add":
                resource.team = [*members, organization]
            else:
                resource.team = [member for member in members if organization not in normalize_user_group_ids([member])]
            changed.append(resource)

    payload = json.dumps([actor, operation, organization, snapshot], separators=(",", ":"))
    token = salted_hmac(f"job.{resource_kind}.adjust_organizations", payload, algorithm="sha256").hexdigest()
    return changed, {
        "changed": len(changed),
        "unchanged": unchanged,
        "blocked": blocked,
        "preview_token": token,
        "groups": [{"before": list(before), "after": list(after), "count": count} for (before, after), count in combinations.items()],
    }


def write_organizations(resources, *, model, user):
    now = timezone.now()
    actor = maintainer_kwargs(operator=user.username, domain=user.domain, include_created=False)
    for resource in resources:
        resource.updated_at = now
        resource.updated_by = actor["updated_by"]
        resource.updated_by_domain = actor["updated_by_domain"]
    model.objects.bulk_update(resources, ["team", "updated_at", "updated_by", "updated_by_domain"], batch_size=100)
