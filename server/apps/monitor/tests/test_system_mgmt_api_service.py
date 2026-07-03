"""SystemMgmtUtils 测试 — 权限规则归并纯逻辑 + RPC 边界 mock 后的入参/取值契约。"""
from unittest.mock import patch

import pytest

from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils

pytestmark = pytest.mark.unit


# --------------------------- format_rules (v1) --------------------------- #
def _rules_v1(items):
    return {"monitor": {"normal": {"Host": {"grp": {"instance": items}}}}}


def test_format_rules_merges_and_dedups_permissions():
    rules = _rules_v1([
        {"id": "i1", "permission": ["view"]},
        {"id": "i1", "permission": ["view", "edit"]},
    ])
    out = SystemMgmtUtils.format_rules("Host", "instance", rules)
    assert set(out["i1"]) == {"view", "edit"}


def test_format_rules_wildcard_zero_returns_none():
    rules = _rules_v1([{"id": "0", "permission": ["view"]}])
    assert SystemMgmtUtils.format_rules("Host", "instance", rules) is None


def test_format_rules_wildcard_minus_one_returns_none():
    rules = _rules_v1([{"id": "-1", "permission": ["view"]}])
    assert SystemMgmtUtils.format_rules("Host", "instance", rules) is None


def test_format_rules_empty_returns_none():
    assert SystemMgmtUtils.format_rules("Host", "instance", {"monitor": {}}) is None


def test_format_rules_guest_child_key_overwrites_normal_same_key():
    # format_rules 用 combined_map.update(**j),j 的键是 child_module 名("instance"),
    # 因此 guest 的同名 child_module 会覆盖 normal 的同名条目(真实行为)。
    rules = {
        "monitor": {
            "normal": {"Host": {"g1": {"instance": [{"id": "i1", "permission": ["view"]}]}}},
            "guest": {"Host": {"g2": {"instance": [{"id": "i2", "permission": ["view"]}]}}},
        }
    }
    out = SystemMgmtUtils.format_rules("Host", "instance", rules)
    assert set(out) == {"i2"}


def test_format_rules_normal_and_guest_different_child_keys_both_kept():
    # 不同 child_module 名不会互相覆盖
    rules = {
        "monitor": {
            "normal": {"Host": {"g1": {"instance": [{"id": "i1", "permission": ["view"]}]}}},
            "guest": {"Host": {"g2": {"other": [{"id": "i2", "permission": ["view"]}]}}},
        }
    }
    out = SystemMgmtUtils.format_rules("Host", "instance", rules)
    assert set(out) == {"i1"}


# --------------------------- format_rules_v2 --------------------------- #
def test_format_rules_v2_separates_wildcard_and_instances():
    rules = {
        "monitor": {
            "normal": {
                "Host": {
                    "grp": {
                        "Host": [
                            {"id": "0", "permission": ["view"]},
                            {"id": "i1", "permission": ["view", "edit", "view"]},
                        ]
                    }
                }
            }
        }
    }
    all_objs, inst_map = SystemMgmtUtils.format_rules_v2("Host", rules)
    assert all_objs == {"Host"}
    assert set(inst_map["i1"]) == {"view", "edit"}


def test_format_rules_v2_empty():
    all_objs, inst_map = SystemMgmtUtils.format_rules_v2("Host", {"monitor": {}})
    assert all_objs == set()
    assert inst_map == {}


# --------------------------- RPC boundary --------------------------- #
def test_get_user_all_scoped_when_actor_context_present():
    with patch("apps.monitor.utils.system_mgmt_api.SystemMgmt") as MockSM:
        inst = MockSM.return_value
        inst.get_group_users_scoped.return_value = {"data": ["u1"]}
        out = SystemMgmtUtils.get_user_all(actor_context={"uid": 1}, group="g", include_children=True)
    inst.get_group_users_scoped.assert_called_once_with({"uid": 1}, group="g", include_children=True)
    inst.get_group_users.assert_not_called()
    assert out == ["u1"]


def test_get_user_all_unscoped_when_no_actor_context():
    with patch("apps.monitor.utils.system_mgmt_api.SystemMgmt") as MockSM:
        inst = MockSM.return_value
        inst.get_group_users.return_value = {"data": ["u2"]}
        out = SystemMgmtUtils.get_user_all(actor_context=None, group="g")
    inst.get_group_users.assert_called_once_with(group="g", include_children=False)
    inst.get_group_users_scoped.assert_not_called()
    assert out == ["u2"]


def test_search_channel_list_scoped():
    with patch("apps.monitor.utils.system_mgmt_api.SystemMgmt") as MockSM:
        inst = MockSM.return_value
        inst.search_channel_list_scoped.return_value = {"data": [{"id": 1}]}
        out = SystemMgmtUtils.search_channel_list({"uid": 1}, channel_type="email", teams=[1])
    inst.search_channel_list_scoped.assert_called_once_with(
        {"uid": 1}, channel_type="email", teams=[1], include_children=False
    )
    assert out == [{"id": 1}]


def test_send_msg_with_channel_passthrough_returns_full_result():
    with patch("apps.monitor.utils.system_mgmt_api.SystemMgmt") as MockSM:
        inst = MockSM.return_value
        inst.send_msg_with_channel.return_value = {"result": True}
        out = SystemMgmtUtils.send_msg_with_channel(7, "t", "c", ["r"])
    inst.send_msg_with_channel.assert_called_once_with(7, "t", "c", ["r"])
    assert out == {"result": True}
