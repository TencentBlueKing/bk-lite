from unittest.mock import Mock

import pytest

from apps.log.services.cloud_region_receiver import CloudRegionReceiverService


def _node_mgmt(proxy_address="", env_config=None):
    client = Mock()
    client.get_cloud_region_proxy_address.return_value = proxy_address
    client.node_list.return_value = {"nodes": [{"id": "node-1"}]}
    client.get_cloud_region_envconfig.return_value = env_config
    return client


def test_resolve_prefers_explicit_proxy_address():
    client = _node_mgmt(
        proxy_address="proxy.example.com",
        env_config={"NODE_SERVER_URL": "https://derived.example.com:8011"},
    )

    result = CloudRegionReceiverService.resolve(client, 42, [1])

    assert result == "proxy.example.com"
    client.get_cloud_region_proxy_address.assert_called_once_with(42, [1])
    client.get_cloud_region_envconfig.assert_not_called()


@pytest.mark.parametrize(
    ("node_server_url", "expected"),
    [
        ("https://logs.example.com:8011/api/v1", "logs.example.com"),
        ("http://10.0.0.8:8011", "10.0.0.8"),
        ("https://[2001:db8::8]:8011", "2001:db8::8"),
        ("logs.example.com:8011", ""),
        ("http://[broken", ""),
    ],
)
def test_resolve_falls_back_to_node_server_url_hostname(node_server_url, expected):
    client = _node_mgmt(env_config={"NODE_SERVER_URL": node_server_url})

    assert CloudRegionReceiverService.resolve(client, 42, [1]) == expected


@pytest.mark.parametrize("env_config", [None, {}, {"NODE_SERVER_URL": ""}])
def test_resolve_returns_empty_when_no_receiver_address(env_config):
    client = _node_mgmt(env_config=env_config)

    assert CloudRegionReceiverService.resolve(client, 42, [1]) == ""


def test_resolve_does_not_fall_back_when_cloud_region_is_not_accessible():
    client = _node_mgmt(env_config={"NODE_SERVER_URL": "https://private.example.com:8011"})
    client.node_list.return_value = {"nodes": []}

    result = CloudRegionReceiverService.resolve(client, 42, [1])

    assert result == ""
    client.get_cloud_region_envconfig.assert_not_called()


def test_resolve_returns_empty_for_user_without_organizations():
    client = _node_mgmt(proxy_address="private.example.com")

    result = CloudRegionReceiverService.resolve(client, 42, [])

    assert result == ""
    client.get_cloud_region_proxy_address.assert_not_called()
