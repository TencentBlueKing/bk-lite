import pytest

from apps.cmdb.services.network_collection_asset_policy import NETWORK_COLLECTION_ASSET_MODELS, validate_network_collection_assets

SWITCH_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
ROUTER_UUID = "4c6643d2-4dc5-4a2a-8f24-3af72f33f7bc"
FIREWALL_UUID = "7f1d3c20-0b11-4a8c-9e3a-21d4b6c8e901"
LOADBALANCE_UUID = "a2b3c4d5-e6f7-4890-abcd-1234567890ab"


def test_allowed_models_are_the_four_network_device_types():
    assert NETWORK_COLLECTION_ASSET_MODELS == frozenset({"switch", "router", "firewall", "loadbalance"})


@pytest.mark.parametrize("model_id", ["switch", "router", "firewall", "loadbalance"])
def test_each_allowed_model_passes(model_id):
    validate_network_collection_assets(
        [
            {
                "inst_uuid": SWITCH_UUID,
                "model_id": model_id,
                "ip_addr": "10.0.0.1",
            }
        ]
    )


def test_mixed_switch_and_router_assets_pass():
    validate_network_collection_assets(
        [
            {"inst_uuid": SWITCH_UUID, "model_id": "switch", "ip_addr": "10.0.0.1"},
            {"inst_uuid": ROUTER_UUID, "model_id": "router", "ip_addr": "10.0.0.2"},
        ]
    )


def test_host_model_is_rejected():
    with pytest.raises(ValueError, match="交换机、路由器、防火墙、负载均衡"):
        validate_network_collection_assets([{"inst_uuid": SWITCH_UUID, "model_id": "host", "ip_addr": "10.0.0.1"}])


def test_missing_manage_ip_is_rejected():
    with pytest.raises(ValueError, match="管理IP"):
        validate_network_collection_assets([{"inst_uuid": SWITCH_UUID, "model_id": "switch", "inst_name": "core-sw"}])


def test_duplicate_manage_ip_is_rejected():
    with pytest.raises(ValueError, match="10.0.0.1"):
        validate_network_collection_assets(
            [
                {"inst_uuid": SWITCH_UUID, "model_id": "switch", "ip_addr": "10.0.0.1"},
                {"inst_uuid": ROUTER_UUID, "model_id": "router", "ip_addr": " 10.0.0.1 "},
            ]
        )


def test_empty_instances_are_skipped():
    validate_network_collection_assets([])


def test_four_allowed_models_together_pass():
    validate_network_collection_assets(
        [
            {"inst_uuid": SWITCH_UUID, "model_id": "switch", "ip_addr": "10.0.0.1"},
            {"inst_uuid": ROUTER_UUID, "model_id": "router", "ip_addr": "10.0.0.2"},
            {"inst_uuid": FIREWALL_UUID, "model_id": "firewall", "ip_addr": "10.0.0.3"},
            {"inst_uuid": LOADBALANCE_UUID, "model_id": "loadbalance", "ip_addr": "10.0.0.4"},
        ]
    )
