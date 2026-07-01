import pytest
from unittest.mock import patch
from apps.alerts.action.target_resolver import resolve_node_target
from apps.alerts.action.exceptions import TargetError


def _nodes(*ips):
    return {"nodes": [{"id": f"n-{ip}", "name": "h", "ip": ip,
                       "operating_system": "linux", "cloud_region": 1} for ip in ips]}


def test_exact_ip_match_one():
    with patch("apps.alerts.action.target_resolver.NodeMgmt") as M:
        M.return_value.node_list.return_value = _nodes("10.0.0.5", "10.0.0.50")
        target = resolve_node_target("10.0.0.5", team=[1])
    assert target == {"node_id": "n-10.0.0.5", "name": "h", "ip": "10.0.0.5",
                      "os": "linux", "cloud_region_id": 1}


def test_zero_match_raises_not_managed():
    with patch("apps.alerts.action.target_resolver.NodeMgmt") as M:
        M.return_value.node_list.return_value = _nodes("10.0.0.50")
        with pytest.raises(TargetError, match="未纳管"):
            resolve_node_target("10.0.0.5", team=[1])


def test_ambiguous_after_team_filter_raises():
    with patch("apps.alerts.action.target_resolver.NodeMgmt") as M:
        M.return_value.node_list.return_value = {"nodes": [
            {"id": "a", "name": "h", "ip": "10.0.0.5", "operating_system": "linux", "cloud_region": 1},
            {"id": "b", "name": "h", "ip": "10.0.0.5", "operating_system": "linux", "cloud_region": 2},
        ]}
        with pytest.raises(TargetError, match="不唯一"):
            resolve_node_target("10.0.0.5", team=[1])


def test_empty_host_raises():
    with pytest.raises(TargetError, match="缺失"):
        resolve_node_target("", team=[1])
