"""NATS 用户规则查询：按组织拆分 guest/normal 规则。"""
import pytest

from apps.system_mgmt import nats_api
from apps.system_mgmt.models import Group, GroupDataRule, UserRule

pytestmark = pytest.mark.django_db


def test_get_user_rules_empty_and_guest_vs_normal():
    assert nats_api.get_user_rules(1, "nobody") == {}

    group = Group.objects.create(name="rules-team", parent_id=0)
    guest = Group.objects.create(name="OpsPilotGuest", parent_id=0)
    normal_rule = GroupDataRule.objects.create(
        name="bot-normal",
        app="opspilot",
        group_id=group.id,
        group_name=group.name,
        rules={"bot": [{"id": 3}]},
    )
    guest_rule = GroupDataRule.objects.create(
        name="bot-guest",
        app="opspilot",
        group_id=guest.id,
        group_name="OpsPilotGuest",
        rules={"bot": [{"id": 9}]},
    )
    UserRule.objects.create(username="rules-u", domain="domain.com", group_rule=normal_rule)
    UserRule.objects.create(username="rules-u", domain="domain.com", group_rule=guest_rule)

    out = nats_api.get_user_rules(group.id, "rules-u")
    assert out["opspilot"]["normal"] == {"bot": [{"id": 3}]}
    assert out["opspilot"]["guest"] == {"bot": [{"id": 9}]}
