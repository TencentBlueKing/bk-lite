import json

import pytest
from django.core.cache import cache

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorInstance, MonitorObject


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_token_cache(settings):
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    cache.clear()


@pytest.fixture
def k3s_objects():
    cluster = MonitorObject.objects.create(
        name="K3SCluster",
        level="base",
        instance_id_keys=["instance_id"],
    )
    node = MonitorObject.objects.create(
        name="K3SNode",
        level="derivative",
        parent=cluster,
        instance_id_keys=["instance_id", "node"],
    )
    return cluster, node


def test_create_instance_only_accepts_k3s_cluster(k3s_objects):
    from apps.monitor.services.k3s_onboarding import K3SOnboardingService

    cluster, node = k3s_objects
    created = K3SOnboardingService.create_instance(
        monitor_object_id=cluster.id,
        instance_id="edge-1",
        name="边缘 K3S",
        organizations=[10, 20],
    )

    instance = MonitorInstance.objects.get(id=created["instance_id"])
    assert instance.monitor_object == cluster
    assert instance.auto is False
    assert set(instance.monitorinstanceorganization_set.values_list("organization", flat=True)) == {10, 20}

    with pytest.raises(BaseAppException, match="K3SCluster"):
        K3SOnboardingService.create_instance(
            monitor_object_id=node.id,
            instance_id="node-1",
            name="错误对象",
            organizations=[],
        )


def test_generate_commands_are_bounded_and_match_private_ca_install_convention(
    k3s_objects, mocker
):
    from apps.monitor.services.k3s_onboarding import K3SOnboardingService

    cluster, _ = k3s_objects
    instance = MonitorInstance.objects.create(
        id=str(("edge-1",)),
        name="边缘 K3S",
        monitor_object=cluster,
        cloud_region_id=7,
    )
    mocker.patch(
        "apps.monitor.services.k3s_onboarding.NodeMgmt"
    ).return_value.get_cloud_region_envconfig.return_value = {
        "NODE_SERVER_URL": "https://bk-lite.example/base",
    }

    result = K3SOnboardingService.generate_install_commands(
        instance_id=instance.id,
        cloud_region_id=7,
    )

    assert "curl -sSLk --fail" in result["install_command"]
    assert "/open_api/k3s_onboarding/render/" in result["install_command"]
    assert "| kubectl apply -f -" in result["install_command"]
    assert "| kubectl delete --ignore-not-found=true -f -" in result["uninstall_command"]
    assert result["expires_in"] == 300
    assert result["install_command"] != result["uninstall_command"]


def test_render_manifest_uses_independent_token_and_webhook_path(k3s_objects, mocker):
    from apps.monitor.services.k3s_onboarding import K3SOnboardingService

    cluster, _ = k3s_objects
    instance = MonitorInstance.objects.create(
        id=str(("edge-1",)),
        name="边缘 K3S",
        monitor_object=cluster,
    )
    token = K3SOnboardingService.issue_render_token(
        instance=instance,
        cloud_region_id=7,
    )
    mocker.patch(
        "apps.monitor.services.k3s_onboarding.NodeMgmt"
    ).return_value.get_cloud_region_envconfig.return_value = {
        "NATS_USERNAME": "user",
        "NATS_PASSWORD": "password",
        "NATS_SERVERS": "tls://nats.example:4222",
        "NATS_TLS_CA": "certificate",
        "WEBHOOK_SERVER_URL": "https://webhook.example/base",
    }
    response = mocker.Mock(status_code=200)
    response.json.return_value = {"status": "success", "yaml": "kind: Namespace"}
    post = mocker.patch(
        "apps.monitor.services.k3s_onboarding.requests.post",
        return_value=response,
    )
    mocker.patch(
        "apps.monitor.services.k3s_onboarding.get_webhook_tls_verify",
        return_value="/ca.pem",
    )

    rendered = K3SOnboardingService.render_manifest(token)

    assert rendered == {"yaml": "kind: Namespace", "remaining_usage": 4}
    url = post.call_args.args[0]
    request = post.call_args.kwargs
    assert url == "https://webhook.example/base/infra/k3s"
    assert request["verify"] == "/ca.pem"
    assert request["json"] == {
        "cluster_name": "edge-1",
        "nats_url": "tls://nats.example:4222",
        "nats_username": "user",
        "nats_password": "password",
        "nats_ca": "certificate",
    }
    assert not {"type", "config_type", "distribution"} & request["json"].keys()


def test_render_token_has_k3s_prefix_and_rejects_sixth_use(k3s_objects):
    from apps.monitor.services.k3s_onboarding import K3SOnboardingService

    cluster, _ = k3s_objects
    instance = MonitorInstance.objects.create(
        id=str(("edge-1",)),
        name="边缘 K3S",
        monitor_object=cluster,
    )
    token = K3SOnboardingService.issue_render_token(
        instance=instance,
        cloud_region_id=7,
    )

    assert token.startswith("k3s_infra_install_token:")
    for remaining in range(4, -1, -1):
        _, actual_remaining = K3SOnboardingService._consume_render_token(token)
        assert actual_remaining == remaining
    with pytest.raises(BaseAppException, match="maximum usage"):
        K3SOnboardingService._consume_render_token(token)
    with pytest.raises(BaseAppException, match="required"):
        K3SOnboardingService._consume_render_token("foreign-token")


def test_verify_reporting_returns_three_independent_k3s_signals(k3s_objects, mocker):
    from apps.monitor.services.k3s_onboarding import K3SOnboardingService

    cluster, _ = k3s_objects
    instance = MonitorInstance.objects.create(
        id=str(("edge-1",)),
        name="边缘 K3S",
        monitor_object=cluster,
    )
    query = mocker.patch(
        "apps.monitor.services.k3s_onboarding.VictoriaMetricsAPI.query",
        side_effect=[
            {"data": {"result": [{"metric": {}}]}},
            {"data": {"result": [{"metric": {}}]}},
            {"data": {"result": []}},
        ],
    )

    result = K3SOnboardingService.verify_reporting(instance.id)

    assert result["status"] == "partial"
    assert result["signals"] == {
        "cluster": {"status": "success", "metric": "kube_node_info"},
        "container": {
            "status": "success",
            "metric": "container_cpu_usage_seconds_total",
        },
        "node": {"status": "pending", "metric": "system_load1"},
    }
    queries = [call.args[0] for call in query.call_args_list]
    assert len(queries) == 3
    assert all('instance_type="k3s"' in item for item in queries)
    assert all(f"instance_id={json.dumps('edge-1')}" in item for item in queries)
    assert queries[0].startswith("prometheus_remote_write_kube_node_info{")
    assert queries[1].startswith(
        "prometheus_remote_write_container_cpu_usage_seconds_total{"
    )
    assert queries[2].startswith("system_load1{")
