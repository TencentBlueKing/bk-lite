"""Sidecar 服务真实行为测试：ETag、404 辅助、组织绑定/同步、签名/防抖、CPU 架构回退/优先级。

仅 mock cache 与 converge celery.delay 边界。断言真实返回值与 DB 副作用。
"""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.models.sidecar import (
    CollectorConfiguration,
    NodeCollectorConfiguration,
    NodeOrganization,
)
from apps.node_mgmt.services.sidecar import Sidecar


@pytest.fixture
def node(db):
    region = CloudRegion.objects.create(name="cr-sidecar-svc")
    return Node.objects.create(
        id="node-sc-svc", name="n", ip="10.3.3.3", operating_system="linux",
        cpu_architecture="x86_64", collector_configuration_directory="/etc",
        cloud_region=region,
    )


def _request(headers=None, meta=None):
    req = MagicMock()
    req.headers = headers or {}
    req.META = meta or {}
    return req


# --------------------------------------------------------------------------- #
# generate_etag / generate_response_etag
# --------------------------------------------------------------------------- #
def test_generate_etag_deterministic():
    a = Sidecar.generate_etag("hello")
    b = Sidecar.generate_etag("hello")
    assert a == b
    assert a != Sidecar.generate_etag("world")


def test_generate_response_etag_plain_json():
    req = _request(meta={})
    etag = Sidecar.generate_response_etag({"a": 1}, req)
    assert isinstance(etag, str) and len(etag) == 32


def test_generate_response_etag_with_encryption():
    req = _request(meta={"HTTP_X_ENCRYPTION_KEY": "k"})
    with patch(
        "apps.node_mgmt.utils.crypto_helper.encrypt_response_data",
        return_value="encrypted-blob",
    ):
        etag = Sidecar.generate_response_etag({"a": 1}, req)
    assert etag == Sidecar.generate_etag("encrypted-blob")


def test_generate_response_etag_encryption_failure_falls_back():
    req = _request(meta={"HTTP_X_ENCRYPTION_KEY": "k"})
    with patch(
        "apps.node_mgmt.utils.crypto_helper.encrypt_response_data",
        side_effect=ValueError("boom"),
    ):
        etag = Sidecar.generate_response_etag({"a": 1}, req)
    assert isinstance(etag, str) and len(etag) == 32


# --------------------------------------------------------------------------- #
# get_node_or_404
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_get_node_or_404_found(node):
    req = _request()
    found, err = Sidecar.get_node_or_404(req, node.id)
    assert found.id == node.id
    assert err is None


@pytest.mark.django_db
def test_get_node_or_404_missing():
    req = _request()
    found, err = Sidecar.get_node_or_404(req, "no-node")
    assert found is None
    assert err.status_code == 404


# --------------------------------------------------------------------------- #
# configuration_bound_to_node / get_bound_*
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_configuration_bound_to_node(node):
    collector = Collector.objects.create(
        id="c-bound", name="C", service_type="svc", node_operating_system="linux",
        executable_path="/bin", execute_parameters="-c",
    )
    config = CollectorConfiguration.objects.create(
        name="cfg-bound", collector=collector, cloud_region=node.cloud_region
    )
    config.nodes.add(node)
    assert Sidecar.configuration_bound_to_node(node.id, config.id) is True
    assert Sidecar.configuration_bound_to_node(node.id, "other") is False


@pytest.mark.django_db
def test_get_bound_assignment_found(node):
    collector = Collector.objects.create(
        id="c-assign", name="C", service_type="svc", node_operating_system="linux",
        executable_path="/bin", execute_parameters="-c",
    )
    config = CollectorConfiguration.objects.create(
        name="cfg-assign", collector=collector, cloud_region=node.cloud_region
    )
    config.nodes.add(node)
    req = _request()
    assignment, err = Sidecar.get_bound_assignment_or_404(req, node.id, config.id)
    assert assignment is not None
    assert err is None


@pytest.mark.django_db
def test_get_bound_assignment_config_not_found_returns_404(node):
    req = _request()
    assignment, err = Sidecar.get_bound_assignment_or_404(req, node.id, "missing-config")
    assert assignment is None
    assert err.status_code == 404


@pytest.mark.django_db
def test_get_bound_assignment_node_missing_returns_node_404():
    req = _request()
    assignment, err = Sidecar.get_bound_assignment_or_404(req, "no-such-node", "cfg")
    assert assignment is None
    assert err.status_code == 404


@pytest.mark.django_db
def test_get_bound_configuration_found(node):
    collector = Collector.objects.create(
        id="c-getcfg", name="C", service_type="svc", node_operating_system="linux",
        executable_path="/bin", execute_parameters="-c",
    )
    config = CollectorConfiguration.objects.create(
        name="cfg-getcfg", collector=collector, cloud_region=node.cloud_region
    )
    config.nodes.add(node)
    req = _request()
    found, err = Sidecar.get_bound_configuration_or_404(req, node.id, config.id, include_collector=True)
    assert found.id == config.id
    assert err is None


@pytest.mark.django_db
def test_get_bound_configuration_not_found(node):
    req = _request()
    found, err = Sidecar.get_bound_configuration_or_404(req, node.id, "nope")
    assert found is None
    assert err.status_code == 404


# --------------------------------------------------------------------------- #
# get_version / get_collectors
# --------------------------------------------------------------------------- #
def test_get_version_returns_payload():
    req = _request()
    resp = Sidecar.get_version(req)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_get_collectors_returns_list_and_etag(node):
    Collector.objects.create(
        id="c-list", name="C", service_type="svc", node_operating_system="linux",
        executable_path="/bin", execute_parameters="-c", default_template="tpl",
    )
    req = _request(headers={})
    with patch("apps.node_mgmt.services.sidecar.cache") as cache_mock:
        cache_mock.get.return_value = None
        resp = Sidecar.get_collectors(req)
    assert resp.status_code == 200
    assert "ETag" in resp


@pytest.mark.django_db
def test_get_collectors_returns_304_when_etag_matches(node):
    req = _request(headers={"If-None-Match": '"cached-etag"'})
    with patch("apps.node_mgmt.services.sidecar.cache") as cache_mock:
        cache_mock.get.return_value = "cached-etag"
        resp = Sidecar.get_collectors(req)
    assert resp.status_code == 304


# --------------------------------------------------------------------------- #
# asso_groups / sync_groups
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_asso_groups_creates_associations(node):
    Sidecar.asso_groups(node.id, [1, 2, 3])
    orgs = set(NodeOrganization.objects.filter(node_id=node.id).values_list("organization", flat=True))
    assert orgs == {1, 2, 3}


@pytest.mark.django_db
def test_asso_groups_empty_noop(node):
    Sidecar.asso_groups(node.id, [])
    assert NodeOrganization.objects.filter(node_id=node.id).count() == 0


@pytest.mark.django_db
def test_sync_groups_adds_and_removes(node):
    NodeOrganization.objects.create(node=node, organization=1)
    NodeOrganization.objects.create(node=node, organization=2)
    Sidecar.sync_groups(node.id, [2, 3])
    orgs = set(NodeOrganization.objects.filter(node_id=node.id).values_list("organization", flat=True))
    assert orgs == {2, 3}


@pytest.mark.django_db
def test_sync_groups_empty_removes_all(node):
    NodeOrganization.objects.create(node=node, organization=1)
    Sidecar.sync_groups(node.id, [])
    assert NodeOrganization.objects.filter(node_id=node.id).count() == 0


# --------------------------------------------------------------------------- #
# _collector_status_signature
# --------------------------------------------------------------------------- #
def test_collector_status_signature_stable_regardless_order():
    s1 = Sidecar._collector_status_signature(
        {"collectors": [{"collector_id": "a", "status": 0}, {"collector_id": "b", "status": 2}]}
    )
    s2 = Sidecar._collector_status_signature(
        {"collectors": [{"collector_id": "b", "status": 2}, {"collector_id": "a", "status": 0}]}
    )
    assert s1 == s2


def test_collector_status_signature_handles_non_list():
    sig = Sidecar._collector_status_signature({"collectors": "notalist"})
    assert isinstance(sig, str)


# --------------------------------------------------------------------------- #
# _is_debounce_elapsed
# --------------------------------------------------------------------------- #
def test_is_debounce_elapsed_first_time_true():
    with patch("apps.node_mgmt.services.sidecar.cache") as cache_mock:
        cache_mock.get.return_value = None
        assert Sidecar._is_debounce_elapsed("k") is True
        cache_mock.set.assert_called_once()


def test_is_debounce_elapsed_recent_false():
    import time

    with patch("apps.node_mgmt.services.sidecar.cache") as cache_mock:
        cache_mock.get.return_value = int(time.time())
        assert Sidecar._is_debounce_elapsed("k") is False


# --------------------------------------------------------------------------- #
# _default_collector_priority
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "collector_arch,node_arch,expected",
    [
        ("arm64", "arm64", 2),
        ("x86_64", "arm64", 0),
        ("x86_64", "x86_64", 2),
        ("", "x86_64", 1),
        ("arm64", "x86_64", 0),
        ("", "", 2),
        ("x86_64", "", 1),
        ("arm64", "", 0),
    ],
)
def test_default_collector_priority(collector_arch, node_arch, expected):
    assert Sidecar._default_collector_priority(collector_arch, node_arch) == expected


# --------------------------------------------------------------------------- #
# _fallback_cpu_architecture
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_fallback_cpu_arch_from_request_field():
    arch = Sidecar._fallback_cpu_architecture("nid", {"cpu_architecture": "amd64"})
    assert arch == NodeConstants.X86_64_ARCH


@pytest.mark.django_db
def test_fallback_cpu_arch_from_architecture_field():
    arch = Sidecar._fallback_cpu_architecture("nid", {"architecture": "aarch64"})
    assert arch == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_fallback_cpu_arch_from_install_task():
    region = CloudRegion.objects.create(name="cr-fallback")
    task = ControllerTask.objects.create(
        cloud_region=region, type="install", status="waiting", package_version_id=1
    )
    ControllerTaskNode.objects.create(
        task=task, ip="10.9.9.9", os="linux", cpu_architecture="arm64",
        port=22, username="root", password="x", status="running",
    )
    arch = Sidecar._fallback_cpu_architecture(
        "nid", {"ip": "10.9.9.9", "operating_system": "Linux"}
    )
    assert arch == NodeConstants.ARM64_ARCH


@pytest.mark.django_db
def test_fallback_cpu_arch_no_data_returns_empty():
    assert Sidecar._fallback_cpu_architecture("nid", {}) == ""


# --------------------------------------------------------------------------- #
# trigger_converge_tasks_if_needed
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_trigger_converge_no_running_tasks_returns(node):
    # 无 running 任务时直接返回，不触发 celery
    with patch(
        "apps.node_mgmt.services.sidecar.converge_collector_action_task_for_node"
    ) as conv:
        Sidecar.trigger_converge_tasks_if_needed(node.id, node.ip, {"collectors": []})
    conv.delay.assert_not_called()
