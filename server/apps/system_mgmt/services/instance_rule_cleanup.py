"""实例移出组织时，清理该组织在指定模块下的实例级授权。"""

from django.db import transaction

from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.system_mgmt.models import GroupDataRule, UserRule


@transaction.atomic
def remove_organization_instance_rules(*, app, module, organization, instance_ids):
    removed = {str(pk) for pk in instance_ids}
    rules = GroupDataRule.objects.select_for_update().filter(app=app, group_id=organization, rules__has_key=module).order_by("pk")
    changed = []
    for rule in rules:
        entries = rule.rules[module]
        if not isinstance(entries, list):
            continue
        retained = [entry for entry in entries if not isinstance(entry, dict) or str(entry.get("id")) not in removed]
        if len(entries) != len(retained):
            # 空列表代表全部实例；删掉最后一条显式授权后用既有的“无实例”标识。
            rule.rules[module] = retained or [{"id": "-1", "name": "specific", "permission": []}]
            changed.append(rule)
    if changed:
        GroupDataRule.objects.bulk_update(changed, ["rules"], batch_size=100)
        users = UserRule.objects.filter(group_rule__in=changed).values("username", "domain").distinct()
        clear_users_permission_cache(list(users))
